"""Node: drop exact copies of photos that are catalogued elsewhere."""

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from raw_and_order.db.repository import FingerprintStore
from raw_and_order.schemas import PhotoCopy
from raw_and_order.workflow.state import PhotoItem, WorkflowState

logger = logging.getLogger(__name__)


class SkipCopiesNode:
    """Skips files whose SHA-256 matches a photo stored at another path.

    The original is the stored photo with that SHA-256 that still exists,
    first by path. If none exists, the first file with that SHA-256 in this
    run is the original and later ones are its copies. Copies are not
    annotated again; ``record_copies`` logs them. This applies even with
    ``--reprocess``. Files that could not be hashed are kept (they fail
    later with a clear error).

    Args:
        photos: Provides stored fingerprints.
        file_exists: Tells whether a stored original is still on disk.
    """

    def __init__(
        self, photos: FingerprintStore, file_exists: Callable[[Path], bool]
    ) -> None:
        self._photos = photos
        self._file_exists = file_exists

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the remaining ``items`` and the ``copies`` found."""
        stored = _paths_by_sha(self._photos.known_fingerprints().items())
        first_in_run: dict[str, Path] = {}
        keep: list[PhotoItem] = []
        copies: list[PhotoCopy] = []
        for item in state.items:
            sha = item.sha256
            if sha is None:
                keep.append(item)
                continue
            original = self._original(item, sha, stored) or first_in_run.get(sha)
            if original is not None and original != item.path:
                copies.append(PhotoCopy(path=item.path, sha256=sha, original=original))
                continue
            keep.append(item)
            first_in_run.setdefault(sha, item.path)
        logger.info("%d exact copies of other photos (skipped)", len(copies))
        return {"items": keep, "copies": copies}

    def _original(
        self, item: PhotoItem, sha: str, stored: dict[str, list[Path]]
    ) -> Path | None:
        """First stored photo with ``sha`` still on disk, unless it is ``item``."""
        existing = (p for p in stored.get(sha, []) if self._file_exists(p))
        original = next(existing, None)
        return None if original == item.path else original


def _paths_by_sha(
    fingerprints: Iterable[tuple[Path, str | None]],
) -> dict[str, list[Path]]:
    """Stored paths per SHA-256, each list sorted by path."""
    by_sha: dict[str, list[Path]] = {}
    for path, sha in fingerprints:
        if sha is not None:
            by_sha.setdefault(sha, []).append(path)
    return {sha: sorted(paths) for sha, paths in by_sha.items()}
