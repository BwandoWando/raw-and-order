"""Recompute the perceptual hash of stored photos (``my-agent rehash``).

Needed after the dHash changes (e.g. its size), so similar-photo search
compares like with like. Each hash comes from the saved preview: no raw
decoding and no LLM calls; annotations and EXIF stay.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from my_agent.db.repository import PerceptualHashStore
from my_agent.exceptions import MediaError
from my_agent.media.protocols import PerceptualHasher, PreviewReader

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 500


class FailedRehash(BaseModel):
    """A stored photo whose preview could not be hashed."""

    path: Path
    message: str


class RehashSummary(BaseModel):
    """Outcome of recomputing perceptual hashes."""

    checked: int = 0
    updated: int = Field(default=0, description="Rows whose dHash changed.")
    unchanged: int = 0
    missing_previews: list[Path] = Field(default_factory=list)
    failed: list[FailedRehash] = Field(default_factory=list)


class PerceptualRehasher:
    """Recomputes every stored photo's dHash from its preview.

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
        logger.info("Recomputing the dHash of %d stored photo(s)", len(stored))
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
            summary.failed.append(FailedRehash(path=path, message=str(exc)))
            return
        if new == old:
            summary.unchanged += 1
            return
        self._store.update_dhash(path, new)
        summary.updated += 1
