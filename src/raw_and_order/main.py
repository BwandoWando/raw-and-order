"""Command-line entry point."""

import logging
import subprocess
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from raw_and_order.bootstrap import (
    check_model,
    open_exif_rereader,
    open_pipeline,
    open_rehasher,
)
from raw_and_order.config import MAX_PHOTOS_HARD_LIMIT, Settings, load_settings
from raw_and_order.exceptions import (
    ModelUnavailableError,
    RawAndOrderError,
    RunAbortedError,
)
from raw_and_order.logging_config import configure_logging
from raw_and_order.maintenance.exif_reread import RereadSummary
from raw_and_order.maintenance.rehash import RehashSummary
from raw_and_order.maintenance.report import ProblemPhoto
from raw_and_order.pipeline import RunSummary
from raw_and_order.ui.launcher import streamlit_command

MAX_COPIES_LISTED = 5  # the rest are summarised as a count

logger = logging.getLogger(__name__)

app = typer.Typer(help="Extract EXIF from camera raw files and annotate them.")


@app.command()
def process(
    source_dir: Annotated[Path, typer.Argument(help="Folder with raw files.")],
    reprocess: Annotated[
        bool, typer.Option(help="Also process files already in the database.")
    ] = False,
    reprocess_failed: Annotated[
        bool,
        typer.Option(
            "--reprocess-failed",
            help="Retry only the photos logged as failed in SOURCE_DIR.",
        ),
    ] = False,
    reread_exif: Annotated[
        bool,
        typer.Option(
            "--reread-exif",
            help=(
                "Only re-read EXIF for photos already stored from SOURCE_DIR and "
                "update those fields. No LLM calls; annotations stay."
            ),
        ),
    ] = False,
    skip_model_check: Annotated[
        bool, typer.Option(help="Skip the startup check of the LLM.")
    ] = False,
    max_photos: Annotated[
        int | None,
        typer.Option(
            "--max-photos",
            min=1,
            max=MAX_PHOTOS_HARD_LIMIT,
            help=(
                "Process at most this many photos (first by path); the rest "
                "wait for the next run. Default: MAX_PHOTOS_PER_RUN (500). "
                f"Max {MAX_PHOTOS_HARD_LIMIT}."
            ),
        ),
    ] = None,
    chunk_size: Annotated[
        int | None,
        typer.Option(
            "--chunk-size",
            min=1,
            max=MAX_PHOTOS_HARD_LIMIT,
            help=(
                "Photos processed and saved together; an interruption loses at "
                "most one chunk. Default: CHUNK_SIZE (25)."
            ),
        ),
    ] = None,
) -> None:
    """Process new or changed photos in SOURCE_DIR, in chunks."""
    if reprocess and reprocess_failed:
        raise typer.BadParameter(
            "use either --reprocess (everything) or --reprocess-failed (only "
            "logged failures), not both",
            param_hint="--reprocess-failed",
        )
    if reread_exif and (reprocess or reprocess_failed):
        raise typer.BadParameter(
            "--reread-exif only updates EXIF of stored photos; it cannot be "
            "combined with --reprocess or --reprocess-failed",
            param_hint="--reread-exif",
        )
    settings = _startup()
    if reread_exif:
        _reread(settings, source_dir)
        return
    limit = max_photos if max_photos is not None else settings.max_photos_per_run
    chunk = chunk_size if chunk_size is not None else settings.chunk_size
    try:
        if not skip_model_check:
            check_model(settings.llm)
        summary = _run(settings, source_dir, reprocess, reprocess_failed, limit, chunk)
    except RunAbortedError as exc:
        _stop_aborted(exc, settings)
    except RawAndOrderError as exc:
        _fail(exc)
    _print_summary(summary)


@app.command()
def check() -> None:
    """Validate configuration and that the LLM can read images."""
    settings = _startup()
    try:
        check_model(settings.llm)
    except RawAndOrderError as exc:
        _fail(exc)
    typer.echo(f"OK: {settings.llm.label} is reachable and supports images.")


@app.command()
def rehash() -> None:
    """Recompute every stored photo's perceptual hash from its preview.

    Run after upgrading the similar-photo fingerprint. No LLM calls;
    annotations and EXIF stay.
    """
    settings = _startup()
    try:
        with open_rehasher(settings) as rehasher:
            summary = rehasher.run()
    except RawAndOrderError as exc:
        _fail(exc)
    _print_rehash_summary(summary)


@app.command()
def ui(
    port: Annotated[int, typer.Option(min=1024, max=65535, help="Local port.")] = 8501,
    open_browser: Annotated[
        bool, typer.Option(help="Open the UI in your browser.")
    ] = True,
) -> None:
    """Open the photo browser (Streamlit) on http://localhost:PORT."""
    configure_logging("INFO")
    try:
        command = streamlit_command(port, open_browser=open_browser)
    except RawAndOrderError as exc:
        _fail(exc)
    typer.echo(
        f"Starting the photo browser on http://localhost:{port} (Ctrl+C to stop)"
    )
    raise typer.Exit(code=subprocess.call(command))


def _startup() -> Settings:
    try:
        settings = load_settings()
    except RawAndOrderError as exc:
        configure_logging("INFO")
        _fail(exc)
    configure_logging(settings.log_level)
    return settings


def _run(
    settings: Settings,
    source_dir: Path,
    reprocess: bool,
    reprocess_failed: bool,
    max_photos: int,
    chunk_size: int,
) -> RunSummary:
    with open_pipeline(settings) as pipeline:
        return pipeline.run(
            source_dir,
            reprocess=reprocess,
            reprocess_failed=reprocess_failed,
            max_photos=max_photos,
            chunk_size=chunk_size,
        )


def _reread(settings: Settings, source_dir: Path) -> None:
    try:
        with open_exif_rereader(settings) as rereader:
            summary = rereader.run(source_dir)
    except RawAndOrderError as exc:
        _fail(exc)
    _print_reread_summary(summary)


def _print_reread_summary(summary: RereadSummary) -> None:
    typer.echo(
        f"EXIF re-read: {summary.checked} stored photo(s) checked, "
        f"{summary.updated} updated, {summary.unchanged} unchanged, "
        f"{len(summary.missing)} missing, {len(summary.failed)} failed."
    )
    for path in summary.missing:
        typer.echo(f"  MISSING {path}")
    _echo_problems(summary.failed)
    if summary.checked == 0:
        typer.echo(
            "No stored photos in that folder; run it without --reread-exif first."
        )


def _print_rehash_summary(summary: RehashSummary) -> None:
    typer.echo(
        f"Rehash: {summary.checked} stored photo(s) checked, "
        f"{summary.updated} updated, {summary.unchanged} unchanged, "
        f"{len(summary.missing_previews)} missing previews, "
        f"{len(summary.failed)} failed."
    )
    for path in summary.missing_previews:
        typer.echo(f"  MISSING PREVIEW {path}")
    _echo_problems(summary.failed)


def _echo_problems(problems: list[ProblemPhoto]) -> None:
    """One ``FAILED`` line per photo a maintenance command could not handle."""
    for problem in problems:
        typer.echo(f"  FAILED {problem.path}: {problem.message}")


def _print_summary(summary: RunSummary) -> None:
    typer.echo(
        f"Run {summary.run_id}: {summary.selected} processed in "
        f"{summary.chunks} chunk(s) ({summary.saved} saved, "
        f"{len(summary.failed)} failed), {summary.unchanged} unchanged, "
        f"{summary.previously_failed} previously failed (skipped), "
        f"{summary.skipped_pairs} skipped (RAW+JPEG pairs), "
        f"{len(summary.copies)} skipped (copies of photos stored elsewhere), "
        f"{summary.deferred} remaining."
    )
    for failed in summary.failed:
        typer.echo(
            f"  FAILED [{failed.error.stage}] {failed.path}: {failed.error.message}"
        )
    for copy in summary.copies[:MAX_COPIES_LISTED]:
        typer.echo(f"  COPY {copy.path} (same as {copy.original})")
    if len(summary.copies) > MAX_COPIES_LISTED:
        typer.echo(f"  ... and {len(summary.copies) - MAX_COPIES_LISTED} more copies")
    for path in summary.missing:
        typer.echo(f"  MISSING (removed from failure log) {path}")
    if summary.deferred:
        typer.echo(f"{summary.deferred} photos are left; run again to continue.")
    if summary.previously_failed:
        typer.echo("Retry previously failed photos with --reprocess-failed.")


def _stop_aborted(exc: RunAbortedError, settings: Settings) -> NoReturn:
    typer.echo(f"Stopped: {exc}", err=True)
    saved = "Photos" if exc.saved is None else f"{exc.saved} photo(s)"
    typer.echo(
        f"{saved} saved before this are kept; nothing from the interrupted "
        "chunk was logged as failed.",
        err=True,
    )
    if isinstance(exc.cause, ModelUnavailableError):
        hint = (
            f"`ollama list` / `ollama pull {settings.llm.model}`"
            if settings.llm.provider == "ollama"
            else "your API key, model name and provider status"
        )
        typer.echo(f"Check {hint}, then `raw-and-order check`.", err=True)
    typer.echo("Run the same command again to continue.", err=True)
    raise typer.Exit(code=1) from exc


def _fail(exc: RawAndOrderError) -> NoReturn:
    logger.error("%s", exc)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
