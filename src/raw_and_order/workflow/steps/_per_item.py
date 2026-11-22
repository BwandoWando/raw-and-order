"""Shared helper: run one step over every healthy item, isolating failures."""

import logging
from collections.abc import Callable

from raw_and_order.exceptions import FatalRunError, RawAndOrderError
from raw_and_order.workflow.state import PhotoItem, Stage, StepFailure

logger = logging.getLogger(__name__)

ItemStep = Callable[[PhotoItem], PhotoItem]


def apply_step(items: list[PhotoItem], stage: Stage, step: ItemStep) -> list[PhotoItem]:
    """Apply ``step`` to each healthy item; record domain errors on the item.

    Items that already failed pass through unchanged. Only
    :class:`RawAndOrderError` is caught, so programming errors still surface, and
    :class:`FatalRunError` (e.g. the model is missing) stops the whole run
    instead of being blamed on one photo.
    """
    return [_run_one(item, stage, step) if item.is_ok else item for item in items]


def _run_one(item: PhotoItem, stage: Stage, step: ItemStep) -> PhotoItem:
    try:
        return step(item)
    except FatalRunError:
        raise
    except RawAndOrderError as exc:
        logger.warning("%s failed for %s: %s", stage, item.path, exc)
        error = StepFailure(
            stage=stage, error_type=type(exc).__name__, message=str(exc)
        )
        return item.model_copy(update={"error": error})
