"""Step: drop files that were already handled in an earlier run."""

import logging
from pathlib import Path
from typing import Any

from raw_and_order.db.failure_repository import FailureRepository
from raw_and_order.db.repository import PhotoRepository
from raw_and_order.workflow.state import PhotoItem, WorkflowState

logger = logging.getLogger(__name__)


class SkipKnownStep:
    """Skips unchanged stored photos and logged failures.

    - A stored photo is skipped if its SHA-256 is unchanged.
    - A logged failure is skipped if its SHA-256 is unchanged, or by path if
      it could not be hashed back then. A failed file whose contents changed
      is kept, so it is retried automatically.

    With ``reprocess`` or ``reprocess_failed`` nothing is skipped.

    Args:
        photos: Provides stored fingerprints.
        failures: Provides logged failures.
    """

    def __init__(self, photos: PhotoRepository, failures: FailureRepository) -> None:
        self._photos = photos
        self._failures = failures

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the remaining ``items`` and what was skipped."""
        if state.reprocess or state.reprocess_failed:
            return {"unchanged": [], "previously_failed": []}
        stored = self._photos.known_fingerprints()
        failed = self._failures.known_failures()
        keep: list[PhotoItem] = []
        unchanged: list[Path] = []
        previously_failed: list[Path] = []
        for item in state.items:
            if _matches(item, stored):
                unchanged.append(item.path)
            elif _still_failing(item, failed):
                previously_failed.append(item.path)
            else:
                keep.append(item)
        logger.info(
            "%d unchanged, %d previously failed (skipped)",
            len(unchanged),
            len(previously_failed),
        )
        return {
            "items": keep,
            "unchanged": unchanged,
            "previously_failed": previously_failed,
        }


def _matches(item: PhotoItem, stored: dict[Path, str | None]) -> bool:
    return item.sha256 is not None and stored.get(item.path) == item.sha256


def _still_failing(item: PhotoItem, failed: dict[Path, str | None]) -> bool:
    if item.path not in failed:
        return False
    logged_sha = failed[item.path]
    return logged_sha is None or logged_sha == item.sha256
