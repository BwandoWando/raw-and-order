"""Conditional edges: stop early when no file is left to process."""

from collections.abc import Callable

from langgraph.graph import END

from my_agent.graph.state import GraphState

Router = Callable[[GraphState], str]


def has_pending_items(state: GraphState) -> bool:
    """True if at least one file has not failed."""
    return any(item.is_ok for item in state.items)


def continue_or_end(next_node: str) -> Router:
    """Return a router that goes to ``next_node`` or ends the run."""

    def route(state: GraphState) -> str:
        return next_node if has_pending_items(state) else END

    return route
