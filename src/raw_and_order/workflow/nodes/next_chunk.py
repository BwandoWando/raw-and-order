"""Node: take the next chunk of photos from the queue."""

from typing import Any

from raw_and_order.workflow.state import WorkflowState


class NextChunkNode:
    """Moves up to ``chunk_size`` photos from ``queue`` into ``items``."""

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the new chunk, the shorter queue and the chunk number."""
        size = state.chunk_size or len(state.queue)
        return {
            "items": state.queue[:size],
            "queue": state.queue[size:],
            "chunk_index": state.chunk_index + 1,
        }
