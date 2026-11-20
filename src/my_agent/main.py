"""Command-line entry point."""

import logging
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from my_agent.bootstrap import Application, check_model
from my_agent.config import Settings, load_settings
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
) -> None:
    """Process every new raw file in SOURCE_DIR."""
    settings = _startup()
    try:
        if not skip_model_check:
            check_model(settings.llm)
        summary = _run(settings, source_dir, reprocess)
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


def _run(settings: Settings, source_dir: Path, reprocess: bool) -> RunSummary:
    with Application(settings) as application:
        if application.pipeline is None:
            raise RuntimeError("Application did not build a pipeline")
        return application.pipeline.run(source_dir, reprocess=reprocess)


def _print_summary(summary: RunSummary) -> None:
    typer.echo(
        f"Run {summary.run_id}: {summary.discovered} found, "
        f"{summary.skipped_pairs} skipped (RAW+JPEG pairs), "
        f"{summary.saved} saved, {len(summary.failed)} failed."
    )
    for failed in summary.failed:
        typer.echo(
            f"  FAILED [{failed.error.stage}] {failed.path}: {failed.error.message}"
        )


def _fail(exc: MyAgentError) -> NoReturn:
    logger.error("%s", exc)
    raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
