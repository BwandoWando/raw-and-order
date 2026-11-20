"""Node: keep the failure log in sync with the current items."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from my_agent.db.failure_repository import FailureRepository
from my_agent.graph.nodes.persist import utc_now
from my_agent.graph.state import GraphState


class LogFailuresNode:
    """Logs failed items and clears the log for items that were saved.

    Runs after ``persist`` in every chunk, and once after ``select_batch``
    for files that failed before any chunk (e.g. could not be hashed).

    Args:
        failures: The failure log.
        clock: Returns the current time; injectable for tests.
    """

    def __init__(
        self, failures: FailureRepository, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._failures = failures
        self._clock = clock

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Write failures and resolutions; the state is not changed."""
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
