"""Shared helper: run one step over every healthy item, isolating failures."""

import logging
from collections.abc import Callable

from my_agent.exceptions import MyAgentError
from my_agent.graph.state import FileError, PhotoItem, Stage

logger = logging.getLogger(__name__)

ItemStep = Callable[[PhotoItem], PhotoItem]


def apply_step(items: list[PhotoItem], stage: Stage, step: ItemStep) -> list[PhotoItem]:
    """Apply ``step`` to each healthy item; record domain errors on the item.

    Items that already failed pass through unchanged. Only
    :class:`MyAgentError` is caught, so programming errors still surface.
    """
    return [_run_one(item, stage, step) if item.is_ok else item for item in items]


def _run_one(item: PhotoItem, stage: Stage, step: ItemStep) -> PhotoItem:
    try:
        return step(item)
    except MyAgentError as exc:
        logger.warning("%s failed for %s: %s", stage, item.path, exc)
        error = FileError(stage=stage, error_type=type(exc).__name__, message=str(exc))
        return item.model_copy(update={"error": error})
