"""Failure log repository: which files failed, where and why."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.models import FailureRow
from raw_and_order.exceptions import PersistenceError
from raw_and_order.schemas import FailureRecord


class FailureRepository(Protocol):
    """Stores and queries logged failures."""

    def record(
        self,
        path: Path,
        sha256: str | None,
        stage: str,
        error_type: str,
        message: str,
        when: datetime,
    ) -> None:
        """Log a failure, or update the existing entry for ``path``."""
        ...

    def resolve(self, paths: Iterable[Path]) -> None:
        """Remove the entries for ``paths`` (they succeeded or are gone)."""
        ...

    def known_failures(self) -> dict[Path, str | None]:
        """Return each logged path and the SHA-256 it had when it failed."""
        ...

    def failures_under(self, folder: Path) -> list[FailureRecord]:
        """Return logged failures inside ``folder``, sorted by path."""
        ...

    def all_failures(self) -> list[FailureRecord]:
        """Return every logged failure, most recent first."""
        ...


class SqlAlchemyFailureRepository:
    """:class:`FailureRepository` backed by SQLAlchemy.

    Args:
        session_factory: Creates a new session per operation.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        path: Path,
        sha256: str | None,
        stage: str,
        error_type: str,
        message: str,
        when: datetime,
    ) -> None:
        """Insert a failure or update it, increasing ``attempts``.

        Raises:
            PersistenceError: If the database write fails.
        """
        try:
            with self._session_factory.begin() as session:
                row = self._find_row(session, path)
                if row is None:
                    row = FailureRow(path=str(path), attempts=0, first_failed_at=when)
                    session.add(row)
                row.sha256 = sha256
                row.stage = stage
                row.error_type = error_type
                row.message = message
                row.attempts += 1
                row.last_failed_at = when
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not log failure of {path}: {exc}") from exc

    def resolve(self, paths: Iterable[Path]) -> None:
        """Delete the entries for ``paths``; unknown paths are ignored.

        Raises:
            PersistenceError: If the database write fails.
        """
        names = [str(path) for path in paths]
        if not names:
            return
        try:
            with self._session_factory.begin() as session:
                session.execute(delete(FailureRow).where(FailureRow.path.in_(names)))
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not clear failures: {exc}") from exc

    def known_failures(self) -> dict[Path, str | None]:
        """Return each logged path and its SHA-256 at the time of failure.

        Raises:
            PersistenceError: If the query fails.
        """
        try:
            with self._session_factory() as session:
                rows = session.execute(select(FailureRow.path, FailureRow.sha256))
                return {Path(path): sha for path, sha in rows}
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list failures: {exc}") from exc

    def failures_under(self, folder: Path) -> list[FailureRecord]:
        """Return logged failures inside ``folder``, sorted by path.

        Raises:
            PersistenceError: If the query fails.
        """
        try:
            with self._session_factory() as session:
                rows = session.scalars(select(FailureRow).order_by(FailureRow.path))
                records = [_to_record(row) for row in rows]
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list failures: {exc}") from exc
        return [r for r in records if r.path.is_relative_to(folder)]

    def all_failures(self) -> list[FailureRecord]:
        """Return every logged failure, most recent first.

        Raises:
            PersistenceError: If the query fails.
        """
        query = select(FailureRow).order_by(FailureRow.last_failed_at.desc())
        try:
            with self._session_factory() as session:
                return [_to_record(row) for row in session.scalars(query)]
        except SQLAlchemyError as exc:
            raise PersistenceError(f"Could not list failures: {exc}") from exc

    @staticmethod
    def _find_row(session: Session, path: Path) -> FailureRow | None:
        query = select(FailureRow).where(FailureRow.path == str(path))
        return session.scalars(query).one_or_none()


def _to_record(row: FailureRow) -> FailureRecord:
    return FailureRecord(
        path=Path(row.path),
        sha256=row.sha256,
        stage=row.stage,
        error_type=row.error_type,
        message=row.message,
        attempts=row.attempts,
        first_failed_at=row.first_failed_at,
        last_failed_at=row.last_failed_at,
    )
