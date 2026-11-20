"""Run the compiled graph for one directory and summarise the outcome."""

import uuid
from collections.abc import Callable
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from my_agent.graph.builder import PhotoGraph
from my_agent.graph.state import FileError, GraphState


class FailedFile(BaseModel):
    """A file that could not be processed, and why."""

    path: Path
    error: FileError


class RunSummary(BaseModel):
    """Outcome of one pipeline run."""

    run_id: str
    discovered: int
    skipped_pairs: int
    unchanged: int
    saved: int
    failed: list[FailedFile]


def summarise(run_id: str, state: GraphState) -> RunSummary:
    """Build a :class:`RunSummary` from the final graph state."""
    return RunSummary(
        run_id=run_id,
        discovered=len(state.items),
        skipped_pairs=len(state.skipped_pairs),
        unchanged=len(state.unchanged),
        saved=sum(item.saved for item in state.items),
        failed=[
            FailedFile(path=item.path, error=item.error)
            for item in state.items
            if item.error is not None
        ],
    )


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
    ) -> RunSummary:
        """Process every new or changed photo in ``source_dir``.

        Raises:
            BatchLimitExceededError: If more than ``max_photos`` need processing.
        """
        run_id = self._run_id_factory()
        config: RunnableConfig = {"configurable": {"thread_id": run_id}}
        initial = GraphState(
            source_dir=source_dir, reprocess=reprocess, max_photos=max_photos
        )
        result = self._graph.invoke(initial, config)
        return summarise(run_id, GraphState.model_validate(result))
