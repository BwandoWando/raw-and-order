"""Copy log repository: files that are exact copies of catalogued photos."""

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.errors import database_errors
from raw_and_order.db.models import CopyRow
from raw_and_order.schemas import PhotoCopy

DELETE_BATCH = 500  # stay well under SQLite's bound-parameter limit


class CopyRepository(Protocol):
    """Stores which files are copies of which catalogued photo."""

    def record(self, copies: Iterable[PhotoCopy], when: datetime) -> None:
        """Insert or update each copy, marking it seen at ``when``."""
        ...

    def remove(self, paths: Iterable[Path]) -> None:
        """Forget ``paths``; unknown paths are ignored."""
        ...

    def copies_under(self, folder: Path) -> list[Path]:
        """Return the recorded copies inside ``folder``."""
        ...


class SqlAlchemyCopyRepository:
    """:class:`CopyRepository` backed by SQLAlchemy.

    Args:
        session_factory: Creates a new session per operation.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, copies: Iterable[PhotoCopy], when: datetime) -> None:
        """Insert or update each copy, marking it seen at ``when``.

        Raises:
            PersistenceError: If the database write fails.
        """
        with database_errors("record copies"), self._session_factory.begin() as session:
            for copy in copies:
                row = session.scalars(
                    select(CopyRow).where(CopyRow.path == str(copy.path))
                ).one_or_none()
                if row is None:
                    row = CopyRow(path=str(copy.path))
                    session.add(row)
                row.sha256 = copy.sha256
                row.original_path = str(copy.original)
                row.last_seen_at = when

    def remove(self, paths: Iterable[Path]) -> None:
        """Forget ``paths``; unknown paths are ignored.

        Raises:
            PersistenceError: If the database write fails.
        """
        names = [str(path) for path in paths]
        with database_errors("remove copies"), self._session_factory.begin() as session:
            for batch in _batches(names, DELETE_BATCH):
                session.execute(delete(CopyRow).where(CopyRow.path.in_(batch)))

    def copies_under(self, folder: Path) -> list[Path]:
        """Return the recorded copies inside ``folder``, sorted by path.

        Raises:
            PersistenceError: If the query fails.
        """
        with database_errors("list copies"), self._session_factory() as session:
            paths = [Path(p) for p in session.scalars(select(CopyRow.path))]
        return sorted(p for p in paths if p.is_relative_to(folder))


def _batches(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
