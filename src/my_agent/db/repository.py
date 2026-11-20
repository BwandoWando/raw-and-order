"""Photo repository: the only code that talks to the database."""

from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from my_agent.db.mappers import apply_record, to_record
from my_agent.db.models import PhotoRow
from my_agent.exceptions import PersistenceError
from my_agent.schemas import PhotoRecord


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

    @staticmethod
    def _find_row(session: Session, path: Path) -> PhotoRow | None:
        query = select(PhotoRow).where(PhotoRow.path == str(path))
        return session.scalars(query).one_or_none()
