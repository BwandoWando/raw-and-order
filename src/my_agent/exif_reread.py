"""Re-read EXIF for photos already in the database (``--reread-exif``).

Updates only the EXIF columns, so new EXIF fields (or fixes to how EXIF is
read) reach existing photos without new LLM annotations.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from my_agent.db.repository import ExifStore
from my_agent.exceptions import MediaError
from my_agent.media.protocols import ExifReader
from my_agent.schemas import ExifData

logger = logging.getLogger(__name__)

PROGRESS_EVERY = 100


class FailedReread(BaseModel):
    """A stored photo whose EXIF could not be read again."""

    path: Path
    message: str


class RereadSummary(BaseModel):
    """Outcome of an EXIF re-read."""

    checked: int = 0
    updated: int = Field(default=0, description="Rows whose EXIF changed.")
    unchanged: int = 0
    missing: list[Path] = Field(default_factory=list)
    failed: list[FailedReread] = Field(default_factory=list)


class ExifRereader:
    """Re-reads EXIF for stored photos under a folder and saves what changed.

    Args:
        store: Reads and updates stored EXIF.
        reader: Reads EXIF from a file.
    """

    def __init__(self, store: ExifStore, reader: ExifReader) -> None:
        self._store = store
        self._reader = reader

    def run(self, folder: Path) -> RereadSummary:
        """Re-read every stored photo inside ``folder``.

        Missing files are skipped; files whose EXIF cannot be read are listed
        and left unchanged.

        Raises:
            PersistenceError: If the database cannot be read or written.
        """
        stored = self._store.stored_exif_under(folder)
        summary = RereadSummary()
        logger.info("Re-reading EXIF for %d stored photo(s) in %s", len(stored), folder)
        for number, (path, old_exif) in enumerate(stored.items(), start=1):
            self._reread_one(path, old_exif, summary)
            if number % PROGRESS_EVERY == 0:
                logger.info(
                    "%d/%d checked (%d updated)", number, len(stored), summary.updated
                )
        return summary

    def _reread_one(
        self, path: Path, old_exif: ExifData, summary: RereadSummary
    ) -> None:
        summary.checked += 1
        if not path.is_file():
            summary.missing.append(path)
            return
        try:
            new_exif = self._reader.read(path)
        except MediaError as exc:
            summary.failed.append(FailedReread(path=path, message=str(exc)))
            return
        if new_exif == old_exif:
            summary.unchanged += 1
            return
        self._store.update_exif(path, new_exif)
        summary.updated += 1
