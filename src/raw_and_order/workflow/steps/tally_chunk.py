"""Step: fold a finished chunk into the run totals."""

import logging

from raw_and_order.workflow.state import FailedPhoto, StateUpdate, WorkflowState

logger = logging.getLogger(__name__)


class TallyChunkStep:
    """Adds the chunk's saved count and failures to the totals, then clears it.

    By the time this runs, the chunk's photos are already in the database
    and its failures in the failure log, so only counts are kept.
    """

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return the updated totals and an empty ``items``."""
        saved = sum(item.saved for item in state.items)
        failed = [
            FailedPhoto(path=i.path, error=i.error) for i in state.items if i.error
        ]
        done = state.selected - len(state.queue)
        logger.info(
            "Chunk %d/%d: %d saved, %d failed (%d/%d done)",
            state.chunk_index,
            state.chunk_total,
            saved,
            len(failed),
            done,
            state.selected,
        )
        return {
            "items": [],
            "saved_count": state.saved_count + saved,
            "failures": [*state.failures, *failed],
        }
