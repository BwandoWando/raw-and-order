"""Step: take the next chunk of photos from the queue."""

from raw_and_order.workflow.state import StateUpdate, WorkflowState


class NextChunkStep:
    """Moves up to ``chunk_size`` photos from ``queue`` into ``items``.

    With no ``chunk_size`` the whole queue becomes one chunk. The previous
    ``items`` (already logged) are replaced.
    """

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return the new chunk, the shorter queue and the chunk number."""
        size = state.chunk_size or len(state.queue)
        return {
            "items": state.queue[:size],
            "queue": state.queue[size:],
            "chunk_index": state.chunk_index + 1,
        }
