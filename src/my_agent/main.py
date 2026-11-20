"""Command-line entry point."""

import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from my_agent.bootstrap import Application, check_model
from my_agent.config import MAX_PHOTOS_HARD_LIMIT, Settings, load_settings
from my_agent.exceptions import MyAgentError
from my_agent.logging_config import configure_logging
from my_agent.pipeline import RunSummary

logger = logging.getLogger(__name__)

app = typer.Typer(help="Extract EXIF from camera raw files and annotate them.")


@app.command()
def process(
    source_dir: Annotated[Path, typer.Argument(help="Folder with raw files.")],
    reprocess: Annotated[
        bool, typer.Option(help="Also process files already in the database.")
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
    settings = _startup()
    limit = max_photos if max_photos is not None else settings.max_photos_per_run
    chunk = chunk_size if chunk_size is not None else settings.chunk_size
    try:
        if not skip_model_check:
            check_model(settings.llm)
        summary = _run(settings, source_dir, reprocess, limit, chunk)
    except MyAgentError as exc:
        _fail(exc)
    _print_summary(summary)


@app.command()
def check() -> None:
    """Validate configuration and that the LLM can read images."""
    settings = _startup()
    try:
        check_model(settings.llm)
    except MyAgentError as exc:
        _fail(exc)
    typer.echo(f"OK: {settings.llm.label} is reachable and supports images.")


def _startup() -> Settings:
    try:
        settings = load_settings()
    except MyAgentError as exc:
        configure_logging("INFO")
        _fail(exc)
    configure_logging(settings.log_level)
    return settings


def _run(
    settings: Settings,
    source_dir: Path,
    reprocess: bool,
    max_photos: int,
    chunk_size: int,
) -> RunSummary:
    with Application(settings) as application:
        if application.pipeline is None:
            raise RuntimeError("Application did not build a pipeline")
        return application.pipeline.run(
            source_dir,
            reprocess=reprocess,
            max_photos=max_photos,
            chunk_size=chunk_size,
        )


def _print_summary(summary: RunSummary) -> None:
    typer.echo(
        f"Run {summary.run_id}: {summary.selected} processed in "
        f"{summary.chunks} chunk(s) ({summary.saved} saved, "
        f"{len(summary.failed)} failed), {summary.unchanged} unchanged, "
        f"{summary.skipped_pairs} skipped (RAW+JPEG pairs), "
        f"{summary.deferred} remaining."
    )
    for failed in summary.failed:
        typer.echo(
            f"  FAILED [{failed.error.stage}] {failed.path}: {failed.error.message}"
        )
    if summary.deferred:
        typer.echo(f"{summary.deferred} photos are left; run again to continue.")


def _fail(exc: MyAgentError) -> NoReturn:
    logger.error("%s", exc)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
