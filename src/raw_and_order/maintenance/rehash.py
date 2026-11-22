"""Recompute the perceptual hash of stored photos (``raw-and-order rehash``).

Needed after the pHash changes (e.g. its size), so similar-photo search
compares like with like. Each hash comes from the saved preview: no raw
decoding and no LLM calls; annotations and EXIF stay.
"""

import logging
from pathlib import Path

from pydantic import Field

from raw_and_order.db.repository import PerceptualHashStore
from raw_and_order.exceptions import MediaError
from raw_and_order.maintenance.report import MaintenanceSummary, ProblemPhoto
from raw_and_order.media.protocols import PerceptualHasher, PreviewReader

logger = logging.getLogger(__name__)

# Hashing a small saved preview is fast, so progress is logged less often
# than for the EXIF re-read.
PROGRESS_EVERY = 500


class RehashSummary(MaintenanceSummary):
    """Outcome of recomputing perceptual hashes."""

    missing_previews: list[Path] = Field(
        default_factory=list, description="Photos whose saved preview is gone."
    )


class PerceptualRehasher:
    """Recomputes every stored photo's pHash from its preview.

    Args:
        store: Lists stored previews and saves hashes.
        hasher: Computes the perceptual hash.
        previews: Loads preview bytes.
    """

    def __init__(
        self,
        store: PerceptualHashStore,
        hasher: PerceptualHasher,
        previews: PreviewReader,
    ) -> None:
        self._store = store
        self._hasher = hasher
        self._previews = previews

    def run(self) -> RehashSummary:
        """Rehash all stored photos; problems are listed, never fatal.

        Raises:
            PersistenceError: If the database cannot be read or written.
        """
        stored = self._store.stored_hashes()
        summary = RehashSummary()
        logger.info("Recomputing the pHash of %d stored photo(s)", len(stored))
        for number, (path, (preview, old)) in enumerate(stored.items(), start=1):
            self._rehash_one(path, preview, old, summary)
            if number % PROGRESS_EVERY == 0:
                logger.info("%d/%d rehashed", number, len(stored))
        return summary

    def _rehash_one(
        self, path: Path, preview: Path, old: str | None, summary: RehashSummary
    ) -> None:
        summary.checked += 1
        if not preview.is_file():
            summary.missing_previews.append(path)
            return
        try:
            new = self._hasher.hash_image_bytes(self._previews.load(preview))
        except MediaError as exc:
            summary.failed.append(ProblemPhoto(path=path, message=str(exc)))
            return
        if new == old:
            summary.unchanged += 1
            return
        self._store.update_phash(path, new)
        summary.updated += 1
