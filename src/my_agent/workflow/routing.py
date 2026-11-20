"""Decisions the workflow runner makes between steps."""

from my_agent.workflow.state import WorkflowState


def has_pending_items(state: WorkflowState) -> bool:
    """True if at least one file in the current chunk has not failed."""
    return any(item.is_ok for item in state.items)


def has_queued_photos(state: WorkflowState) -> bool:
    """True if photos are still waiting for a chunk."""
    return bool(state.queue)
