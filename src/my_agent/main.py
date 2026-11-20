"""Command-line entry point."""

import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from my_agent.bootstrap import Application, check_model
from my_agent.config import MAX_PHOTOS_HARD_LIMIT, Settings, load_settings
from my_agent.exceptions import BatchLimitExceededError, MyAgentError
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
                "Stop without processing if more photos than this need work. "
                f"Default: MAX_PHOTOS_PER_RUN (500). Max {MAX_PHOTOS_HARD_LIMIT}."
            ),
        ),
    ] = None,
) -> None:
    """Process every new or changed photo in SOURCE_DIR."""
    settings = _startup()
    limit = max_photos if max_photos is not None else settings.max_photos_per_run
    try:
        if not skip_model_check:
            check_model(settings.llm)
        summary = _run(settings, source_dir, reprocess, limit)
    except BatchLimitExceededError as exc:
        _stop_over_limit(exc)
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
    settings: Settings, source_dir: Path, reprocess: bool, max_photos: int
) -> RunSummary:
    with Application(settings) as application:
        if application.pipeline is None:
            raise RuntimeError("Application did not build a pipeline")
        return application.pipeline.run(
            source_dir, reprocess=reprocess, max_photos=max_photos
        )


def _print_summary(summary: RunSummary) -> None:
    typer.echo(
        f"Run {summary.run_id}: {summary.discovered} found, "
        f"{summary.skipped_pairs} skipped (RAW+JPEG pairs), "
        f"{summary.unchanged} unchanged, "
        f"{summary.saved} saved, {len(summary.failed)} failed."
    )
    for failed in summary.failed:
        typer.echo(
            f"  FAILED [{failed.error.stage}] {failed.path}: {failed.error.message}"
        )


def _stop_over_limit(exc: BatchLimitExceededError) -> NoReturn:
    typer.echo(f"Stopped: {exc}", err=True)
    if exc.limit < MAX_PHOTOS_HARD_LIMIT:
        typer.echo(
            "Process a smaller folder, or raise the limit with "
            f"--max-photos N (up to {MAX_PHOTOS_HARD_LIMIT}) "
            "or MAX_PHOTOS_PER_RUN in .env.",
            err=True,
        )
    else:
        typer.echo(
            f"{MAX_PHOTOS_HARD_LIMIT} is the maximum per run; "
            "split the folder into smaller ones.",
            err=True,
        )
    raise typer.Exit(code=1) from exc


def _fail(exc: MyAgentError) -> NoReturn:
    logger.error("%s", exc)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
