"""Step: choose which photos this run processes."""

import logging
import math
from typing import Any

from raw_and_order.workflow.state import FileFailure, PhotoItem, WorkflowState

logger = logging.getLogger(__name__)


class SelectBatchStep:
    """Queues the first ``max_photos`` photos (sorted by path) for processing.

    Photos beyond the limit are deferred: a later run picks them up, because
    saved photos are skipped as unchanged. Files that already failed (e.g.
    could not be hashed) are recorded as failures and use no slot.
    """

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the ``queue``, counts, and any early failures."""
        pending = sorted((i for i in state.items if i.is_ok), key=_path_key)
        selected = pending if state.max_photos is None else pending[: state.max_photos]
        deferred = len(pending) - len(selected)
        if deferred:
            logger.info(
                "Processing the first %d of %d photos; %d left for later runs",
                len(selected),
                len(pending),
                deferred,
            )
        early_failures = [item for item in state.items if not item.is_ok]
        return {
            # Early failures stay in ``items`` so log_planning_failures logs them.
            "items": early_failures,
            "queue": selected,
            "selected": len(selected),
            "deferred": deferred,
            "chunk_index": 0,
            "chunk_total": _chunk_count(len(selected), state.chunk_size),
            "failures": [*state.failures, *_failures(state.items)],
        }


def _path_key(item: PhotoItem) -> str:
    return str(item.path)


def _chunk_count(count: int, chunk_size: int | None) -> int:
    if count == 0:
        return 0
    return 1 if chunk_size is None else math.ceil(count / chunk_size)


def _failures(items: list[PhotoItem]) -> list[FileFailure]:
    return [FileFailure(path=i.path, error=i.error) for i in items if i.error]
