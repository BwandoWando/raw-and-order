"""Step: keep the failure log in sync with the current items."""

from collections.abc import Callable
from datetime import datetime

from raw_and_order.db.failure_repository import FailureRepository
from raw_and_order.workflow.state import StateUpdate, WorkflowState
from raw_and_order.workflow.steps.persist import utc_now


class SyncFailureLogStep:
    """Logs failed items and clears the log for items that were saved.

    Runs at the end of every chunk (also when the chunk stopped early because
    every photo failed), and once after ``select_batch`` (as
    ``sync_planning_failures``) for files that failed before any chunk, e.g.
    could not be hashed.

    Args:
        failures: The failure log.
        clock: Returns the current time; injectable for tests.
    """

    def __init__(
        self, failures: FailureRepository, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._failures = failures
        self._clock = clock

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Write failures and resolutions for ``items``; the state is unchanged.

        Raises:
            PersistenceError: If the failure log cannot be written; this is
                not recorded per photo, so it ends the run.
        """
        now = self._clock()
        for item in state.items:
            if item.error is not None:
                self._failures.record(
                    item.path,
                    item.sha256,
                    item.error.stage.value,
                    item.error.error_type,
                    item.error.message,
                    now,
                )
        self._failures.resolve(item.path for item in state.items if item.saved)
        return {}
