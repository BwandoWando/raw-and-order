"""Photo repository: the only code that talks to the database."""

from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.mappers import apply_exif, apply_record, to_exif, to_record
from raw_and_order.db.models import PhotoRow
from raw_and_order.exceptions import PersistenceError
from raw_and_order.schemas import ExifData, PhotoRecord


class PhotoRepository(Protocol):
    """Stores and queries processed photos."""

    def upsert(self, record: PhotoRecord) -> None:
        """Insert ``record`` or update the existing row with the same path."""
        ...

    def get_by_path(self, path: Path) -> PhotoRecord | None:
        """Return the record for ``path`` or ``None``."""
        ...

    def known_paths(self) -> set[Path]:
        """Return the paths of all stored photos."""
        ...

    def known_fingerprints(self) -> dict[Path, str | None]:
        """Return each stored photo's path and SHA-256."""
        ...


class FingerprintStore(Protocol):
    """Lists the SHA-256 of every stored photo."""

    def known_fingerprints(self) -> dict[Path, str | None]:
        """Return each stored photo's path and SHA-256."""
        ...


class ExifStore(Protocol):
    """Reads and updates only the EXIF part of stored photos."""

    def stored_exif_under(self, folder: Path) -> dict[Path, ExifData]:
        """Return the stored EXIF of every photo inside ``folder``."""
        ...

    def update_exif(self, path: Path, exif: ExifData) -> None:
        """Replace the EXIF columns of the photo at ``path``."""
        ...


class PerceptualHashStore(Protocol):
    """Reads previews and updates only the perceptual hash of stored photos."""

    def stored_hashes(self) -> dict[Path, tuple[Path, str | None]]:
        """Return ``{photo path: (preview path, pHash)}`` for every photo."""
        ...

    def update_phash(self, path: Path, phash: str) -> None:
        """Replace the pHash of the photo at ``path``."""
        ...


class SqlAlchemyPhotoRepository:
    """:class:`PhotoRepository` backed by SQLAlchemy.

    Args:
        session_factory: Creates a new session per operation.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def upsert(self, record: PhotoRecord) -> None:
        """Insert or update ``record``.

        Raises:
            PersistenceError: If the database write fails.
        """
        try:
            with self._session_factory.begin() as session:
                row = self._find_row(session, record.path) or PhotoRow()
                session.add(apply_record(row, record))
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not save {record.path}: {exc}") from exc

    def get_by_path(self, path: Path) -> PhotoRecord | None:
        """Return the record for ``path`` or ``None``.

        Raises:
            PersistenceError: If the query fails.
        """
        try:
            with self._session_factory() as session:
                row = self._find_row(session, path)
                return to_record(row) if row else None
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not load {path}: {exc}") from exc

    def known_paths(self) -> set[Path]:
        """Return the paths of all stored photos.

        Raises:
            PersistenceError: If the query fails.
        """
        try:
            with self._session_factory() as session:
                return {Path(p) for p in session.scalars(select(PhotoRow.path))}
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list stored photos: {exc}") from exc

    def known_fingerprints(self) -> dict[Path, str | None]:
        """Return each stored photo's path and SHA-256.

        Raises:
            PersistenceError: If the query fails.
        """
        query = select(PhotoRow.path, PhotoRow.sha256)
        try:
            with self._session_factory() as session:
                return {Path(path): sha for path, sha in session.execute(query)}
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list fingerprints: {exc}") from exc

    def stored_exif_under(self, folder: Path) -> dict[Path, ExifData]:
        """Return the stored EXIF of every photo inside ``folder``, by path.

        Raises:
            PersistenceError: If the query fails.
        """
        try:
            with self._session_factory() as session:
                rows = session.scalars(select(PhotoRow).order_by(PhotoRow.path))
                stored = {Path(row.path): to_exif(row) for row in rows}
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list stored photos: {exc}") from exc
        return {
            path: exif for path, exif in stored.items() if path.is_relative_to(folder)
        }

    def update_exif(self, path: Path, exif: ExifData) -> None:
        """Replace only the EXIF columns; annotation, preview and hashes stay.

        Raises:
            PersistenceError: If the photo is not stored or the write fails.
        """
        try:
            with self._session_factory.begin() as session:
                row = self._find_row(session, path)
                if row is None:
                    raise PersistenceError(f"{path} is not in the database")
                apply_exif(row, exif)
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not update {path}: {exc}") from exc

    def stored_hashes(self) -> dict[Path, tuple[Path, str | None]]:
        """Return ``{photo path: (preview path, pHash)}``, ordered by path.

        Raises:
            PersistenceError: If the query fails.
        """
        query = select(PhotoRow.path, PhotoRow.preview_path, PhotoRow.phash)
        try:
            with self._session_factory() as session:
                rows = session.execute(query.order_by(PhotoRow.path))
                return {Path(p): (Path(preview), phash) for p, preview, phash in rows}
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list stored hashes: {exc}") from exc

    def update_phash(self, path: Path, phash: str) -> None:
        """Replace only the pHash; everything else stays.

        Raises:
            PersistenceError: If the photo is not stored or the write fails.
        """
        try:
            with self._session_factory.begin() as session:
                row = self._find_row(session, path)
                if row is None:
                    raise PersistenceError(f"{path} is not in the database")
                row.phash = phash
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not update {path}: {exc}") from exc

    @staticmethod
    def _find_row(session: Session, path: Path) -> PhotoRow | None:
        query = select(PhotoRow).where(PhotoRow.path == str(path))
        return session.scalars(query).one_or_none()
