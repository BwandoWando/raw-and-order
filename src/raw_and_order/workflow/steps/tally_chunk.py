"""Step: fold a finished chunk into the run totals."""

import logging
from typing import Any

from raw_and_order.workflow.state import FileFailure, WorkflowState

logger = logging.getLogger(__name__)


class TallyChunkStep:
    """Adds the chunk's saved count and failures to the totals, then clears it.

    By the time this runs, the chunk's photos are already in the database.
    """

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the updated totals and an empty ``items``."""
        saved = sum(item.saved for item in state.items)
        failed = [
            FileFailure(path=i.path, error=i.error) for i in state.items if i.error
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
