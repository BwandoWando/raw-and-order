"""Step: in --reprocess-failed runs, start from the failure log."""

import logging

from raw_and_order.db.failure_repository import FailureRepository
from raw_and_order.workflow.state import PhotoItem, StateUpdate, WorkflowState

logger = logging.getLogger(__name__)


class LoadFailuresStep:
    """Lists logged failures under ``source_dir`` whose file still exists.

    Entries whose file is gone are removed from the log and reported as
    ``missing``, since they can never be retried. Used instead of
    ``discover``, so no RAW+JPEG pairing is done for these files.

    Args:
        failures: The failure log.
    """

    def __init__(self, failures: FailureRepository) -> None:
        self._failures = failures

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return the failures to retry as ``items``, and the missing ones."""
        logged = [r.path for r in self._failures.failures_under(state.source_dir)]
        existing = [path for path in logged if path.is_file()]
        missing = [path for path in logged if not path.is_file()]
        self._failures.resolve(missing)
        logger.info(
            "%d logged failure(s) to retry, %d no longer exist (removed from log)",
            len(existing),
            len(missing),
        )
        return {"items": [PhotoItem(path=p) for p in existing], "missing": missing}
