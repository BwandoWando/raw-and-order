"""Node: stop before any heavy work if the batch is too large."""

from typing import Any

from my_agent.exceptions import BatchLimitExceededError
from my_agent.graph.state import GraphState


class BatchLimitNode:
    """Refuses to continue when more photos need processing than allowed.

    Runs after unchanged files have been dropped, so only photos that would
    actually be decoded and annotated count. Files that already failed an
    earlier step are not counted.
    """

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return no update, or raise if the limit is exceeded.

        Raises:
            BatchLimitExceededError: If the pending count exceeds the limit.
        """
        pending = sum(item.is_ok for item in state.items)
        if state.max_photos is not None and pending > state.max_photos:
            raise BatchLimitExceededError(pending, state.max_photos)
        return {}
