"""Node: keep the copy log in sync with what this run found."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from raw_and_order.db.copy_repository import CopyRepository
from raw_and_order.workflow.nodes.persist import utc_now
from raw_and_order.workflow.state import WorkflowState


class RecordCopiesNode:
    """Logs the copies found and forgets ones that are no longer copies.

    After a full scan, every logged copy under the folder that was not found
    again (deleted, moved, or changed so it is no longer identical) is
    removed. With ``--reprocess-failed`` only the retried files are checked.

    Args:
        copies: The copy log.
        clock: Returns the current time; injectable for tests.
    """

    def __init__(
        self, copies: CopyRepository, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._copies = copies
        self._clock = clock

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Write the copy log; the state is not changed."""
        self._copies.record(state.copies, self._clock())
        found = {copy.path for copy in state.copies}
        if state.reprocess_failed:
            stale = [item.path for item in state.items]
        else:
            logged = self._copies.copies_under(state.source_dir)
            stale = [path for path in logged if path not in found]
        self._copies.remove(stale)
        return {}
