"""Favorites: photos starred in the photo details.

The UI reads and sets them through its ``PhotoLibrary``; the catalog's
``only_favorites`` filter reads the same ``favorites`` table.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.errors import database_errors
from raw_and_order.db.models import FavoriteRow, PhotoRow
from raw_and_order.exceptions import PersistenceError


class FavoriteStore(Protocol):
    """Marks stored photos as favorites and says which ones are."""

    def is_favorite(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is a favorite."""
        ...

    def set_favorite(self, path: Path, favorite: bool, when: datetime) -> None:
        """Mark (``favorite=True``) or unmark the photo at ``path``.

        ``when`` is the local time it was marked; unmarking ignores it.
        """
        ...

    def favorites_among(self, paths: Sequence[Path]) -> set[Path]:
        """Return those of ``paths`` that are favorites, in one query."""
        ...


class SqlAlchemyFavoriteRepository:
    """:class:`FavoriteStore` backed by the ``favorites`` table.

    Args:
        session_factory: Opens database sessions.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def is_favorite(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is a favorite.

        Raises:
            PersistenceError: If the query fails.
        """
        query = (
            select(FavoriteRow.id)
            .join(PhotoRow, FavoriteRow.photo_id == PhotoRow.id)
            .where(PhotoRow.path == str(path))
        )
        with database_errors("read favorites"), self._session_factory() as session:
            return session.scalar(query) is not None

    def set_favorite(self, path: Path, favorite: bool, when: datetime) -> None:
        """Mark or unmark the photo at ``path``; repeating either does nothing.

        Raises:
            PersistenceError: If the photo is not stored or the write fails.
        """
        with (
            database_errors(f"update the favorite of {path}"),
            self._session_factory.begin() as session,
        ):
            photo_id = session.scalar(
                select(PhotoRow.id).where(PhotoRow.path == str(path))
            )
            if photo_id is None:
                raise PersistenceError(f"{path} is not in the database")
            if favorite:
                _add(session, photo_id, when)
            else:
                _remove(session, photo_id)

    def favorites_among(self, paths: Sequence[Path]) -> set[Path]:
        """Return those of ``paths`` that are favorites, in one query.

        For a page of gallery tiles: one query, not one per photo.

        Raises:
            PersistenceError: If the query fails.
        """
        if not paths:
            return set()
        query = (
            select(PhotoRow.path)
            .join(FavoriteRow, FavoriteRow.photo_id == PhotoRow.id)
            .where(PhotoRow.path.in_([str(p) for p in paths]))
        )
        with database_errors("read favorites"), self._session_factory() as session:
            return {Path(p) for p in session.scalars(query)}


def _add(session: Session, photo_id: int, when: datetime) -> None:
    """Insert the favorite unless the photo already is one (keeps its time)."""
    query = select(FavoriteRow.id).where(FavoriteRow.photo_id == photo_id)
    if session.scalar(query) is None:
        session.add(FavoriteRow(photo_id=photo_id, favorited_at=when))


def _remove(session: Session, photo_id: int) -> None:
    """Delete the photo's favorite, if it has one."""
    session.execute(delete(FavoriteRow).where(FavoriteRow.photo_id == photo_id))
