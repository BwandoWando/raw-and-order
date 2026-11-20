"""Run the compiled graph for one directory and summarise the outcome."""

import math
import uuid
from collections.abc import Callable
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from my_agent.config import MAX_PHOTOS_HARD_LIMIT
from my_agent.graph.builder import PhotoGraph, planning_steps, steps_per_chunk
from my_agent.graph.state import FileFailure, GraphState

RECURSION_MARGIN = 10


class RunSummary(BaseModel):
    """Outcome of one pipeline run."""

    run_id: str
    selected: int
    skipped_pairs: int
    unchanged: int
    previously_failed: int
    missing: list[Path]
    deferred: int
    chunks: int
    saved: int
    failed: list[FileFailure]


def summarise(run_id: str, state: GraphState) -> RunSummary:
    """Build a :class:`RunSummary` from the final graph state."""
    return RunSummary(
        run_id=run_id,
        selected=state.selected,
        skipped_pairs=len(state.skipped_pairs),
        unchanged=len(state.unchanged),
        previously_failed=len(state.previously_failed),
        missing=state.missing,
        deferred=state.deferred,
        chunks=state.chunk_index,
        saved=state.saved_count,
        failed=state.failures,
    )


def recursion_limit(max_photos: int | None, chunk_size: int | None) -> int:
    """Graph steps needed for the worst case, so LangGraph never stops early.

    LangGraph aborts after 25 steps by default; the chunk loop needs about
    ``steps_per_chunk()`` steps per chunk.
    """
    photos = max_photos or MAX_PHOTOS_HARD_LIMIT
    chunks = 1 if chunk_size is None else math.ceil(photos / chunk_size)
    return planning_steps() + chunks * steps_per_chunk() + RECURSION_MARGIN


def new_run_id() -> str:
    """Return a unique id used as the LangGraph thread id."""
    return f"run-{uuid.uuid4().hex[:12]}"


class PhotoPipeline:
    """Runs the photo graph.

    Args:
        graph: The compiled LangGraph pipeline.
        run_id_factory: Creates the thread id for each run.
    """

    def __init__(
        self, graph: PhotoGraph, run_id_factory: Callable[[], str] = new_run_id
    ) -> None:
        self._graph = graph
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
        """
        run_id = self._run_id_factory()
        config: RunnableConfig = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": recursion_limit(max_photos, chunk_size),
        }
        initial = GraphState(
            source_dir=source_dir,
            reprocess=reprocess,
            reprocess_failed=reprocess_failed,
            max_photos=max_photos,
            chunk_size=chunk_size,
        )
        result = self._graph.invoke(initial, config)
        return summarise(run_id, GraphState.model_validate(result))
