"""Run the workflow for one directory and summarise the outcome."""

import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from raw_and_order.schemas import PhotoCopy
from raw_and_order.workflow.runner import PhotoWorkflow
from raw_and_order.workflow.state import FileFailure, WorkflowState


class RunSummary(BaseModel):
    """Outcome of one pipeline run."""

    run_id: str
    selected: int
    skipped_pairs: int
    unchanged: int
    copies: list[PhotoCopy]
    previously_failed: int
    missing: list[Path]
    deferred: int
    chunks: int
    saved: int
    failed: list[FileFailure]


def summarise(run_id: str, state: WorkflowState) -> RunSummary:
    """Build a :class:`RunSummary` from the final workflow state."""
    return RunSummary(
        run_id=run_id,
        selected=state.selected,
        skipped_pairs=len(state.skipped_pairs),
        unchanged=len(state.unchanged),
        copies=state.copies,
        previously_failed=len(state.previously_failed),
        missing=state.missing,
        deferred=state.deferred,
        chunks=state.chunk_index,
        saved=state.saved_count,
        failed=state.failures,
    )


def new_run_id() -> str:
    """Return a unique id for log lines and the run summary."""
    return f"run-{uuid.uuid4().hex[:12]}"


class PhotoPipeline:
    """Runs the photo workflow for a folder.

    Args:
        workflow: The configured workflow.
        run_id_factory: Creates the id of each run.
    """

    def __init__(
        self, workflow: PhotoWorkflow, run_id_factory: Callable[[], str] = new_run_id
    ) -> None:
        self._workflow = workflow
        self._run_id_factory = run_id_factory

    def run(
        self,
        source_dir: Path,
        reprocess: bool = False,
        max_photos: int | None = None,
        chunk_size: int | None = None,
        reprocess_failed: bool = False,
    ) -> RunSummary:
        """Process up to ``max_photos`` new or changed photos in ``source_dir``.

        Photos are processed and saved ``chunk_size`` at a time, so an
        interrupted run keeps every finished chunk. With ``reprocess_failed``
        only the logged failures under ``source_dir`` are retried.

        Raises:
            RunAbortedError: If the LLM became unavailable or too many photos
                in a row failed; carries the photos saved so far.
        """
        run_id = self._run_id_factory()
        initial = WorkflowState(
            source_dir=source_dir,
            reprocess=reprocess,
            reprocess_failed=reprocess_failed,
            max_photos=max_photos,
            chunk_size=chunk_size,
        )
        return summarise(run_id, self._workflow.run(initial))
