"""Trash: photos marked for deletion in the photo details.

Only marks are kept here; nothing deletes the files or their rows. The UI
reads and sets them through its ``PhotoLibrary``; the catalog's
``only_trashed`` filter ("Marked for deletion only") reads the same table.
"""

from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.errors import database_errors
from raw_and_order.db.models import PhotoRow, TrashRow
from raw_and_order.exceptions import PersistenceError


class TrashStore(Protocol):
    """Marks stored photos for deletion and says which ones are marked."""

    def is_trashed(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is marked for deletion."""
        ...

    def set_trashed(self, path: Path, trashed: bool, when: datetime) -> None:
        """Mark (``trashed=True``) or unmark the photo at ``path``.

        ``when`` is the local time it was marked; unmarking ignores it.
        """
        ...


class SqlAlchemyTrashRepository:
    """:class:`TrashStore` backed by the ``trash`` table.

    Args:
        session_factory: Opens database sessions.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def is_trashed(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is marked for deletion.

        Raises:
            PersistenceError: If the query fails.
        """
        query = (
            select(TrashRow.id)
            .join(PhotoRow, TrashRow.photo_id == PhotoRow.id)
            .where(PhotoRow.path == str(path))
        )
        with database_errors("read the trash"), self._session_factory() as session:
            return session.scalar(query) is not None

    def set_trashed(self, path: Path, trashed: bool, when: datetime) -> None:
        """Mark or unmark the photo at ``path``; repeating either does nothing.

        Raises:
            PersistenceError: If the photo is not stored or the write fails.
        """
        with (
            database_errors(f"update the deletion mark of {path}"),
            self._session_factory.begin() as session,
        ):
            photo_id = session.scalar(
                select(PhotoRow.id).where(PhotoRow.path == str(path))
            )
            if photo_id is None:
                raise PersistenceError(f"{path} is not in the database")
            if trashed:
                _add(session, photo_id, when)
            else:
                _remove(session, photo_id)


def _add(session: Session, photo_id: int, when: datetime) -> None:
    """Insert the mark unless the photo already has one (keeps its time)."""
    query = select(TrashRow.id).where(TrashRow.photo_id == photo_id)
    if session.scalar(query) is None:
        session.add(TrashRow(photo_id=photo_id, trashed_at=when))


def _remove(session: Session, photo_id: int) -> None:
    """Delete the photo's mark, if it has one."""
    session.execute(delete(TrashRow).where(TrashRow.photo_id == photo_id))
