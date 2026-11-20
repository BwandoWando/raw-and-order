"""Conditional edges for the planning steps and the chunk loop."""

from collections.abc import Callable

from my_agent.graph.state import GraphState

Router = Callable[[GraphState], str]


def has_pending_items(state: GraphState) -> bool:
    """True if at least one file in the current chunk has not failed."""
    return any(item.is_ok for item in state.items)


def has_queued_photos(state: GraphState) -> bool:
    """True if photos are still waiting for a chunk."""
    return bool(state.queue)


def continue_or(next_node: str, fallback: str) -> Router:
    """Go to ``next_node`` while the chunk has healthy files, else ``fallback``."""

    def route(state: GraphState) -> str:
        return next_node if has_pending_items(state) else fallback

    return route


def next_chunk_or(next_chunk: str, done: str) -> Router:
    """Start another chunk while photos are queued, else go to ``done``."""

    def route(state: GraphState) -> str:
        return next_chunk if has_queued_photos(state) else done

    return route
