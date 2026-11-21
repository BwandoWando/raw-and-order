"""Read-only queries over stored photos, for the UI.

Kept separate from :mod:`my_agent.db.repository`, which writes. Everything
here only reads, so it is safe to use while a processing run is writing
(SQLite runs in WAL mode).
"""

import json
from collections import Counter
from datetime import datetime, time
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from my_agent.db.mappers import to_record
from my_agent.db.models import PhotoRow
from my_agent.exceptions import PersistenceError
from my_agent.media.hashing import hamming_distance
from my_agent.schemas import PhotoRecord
from my_agent.schemas.query import (
    CountRow,
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
    SortOrder,
)

LIKE_ESCAPE = "\\"
KELVIN_BUCKET = 500
NEAR_DUPLICATE_DISTANCE = 10
UNKNOWN_LABEL = "Unknown"


class PhotoCatalog(Protocol):
    """Searches and summarises stored photos."""

    def search(self, query: PhotoQuery) -> PhotoPage:
        """Return one page of photos matching ``query``."""
        ...

    def filter_options(self) -> FilterOptions:
        """Return the values available for each filter."""
        ...

    def get(self, path: Path) -> PhotoRecord | None:
        """Return one photo by path."""
        ...

    def near_duplicates(
        self, record: PhotoRecord, max_distance: int = NEAR_DUPLICATE_DISTANCE
    ) -> list[NearDuplicate]:
        """Return photos that look like ``record``, closest first."""
        ...

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        ...

    def tag_lists(self, query: PhotoQuery) -> list[list[str]]:
        """Return the tags of every photo matching ``query``'s filters."""
        ...


class SqlAlchemyPhotoCatalog:
    """:class:`PhotoCatalog` backed by SQLAlchemy.

    Args:
        session_factory: Creates a new session per query.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def search(self, query: PhotoQuery) -> PhotoPage:
        """Return one page of photos matching ``query``.

        Raises:
            PersistenceError: If the query fails.
        """
        filtered = apply_filters(select(PhotoRow), query)
        count_query = select(func.count()).select_from(filtered.subquery())
        page_query = (
            apply_sort(filtered, query.sort)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        with self._read() as session:
            total = session.scalar(count_query) or 0
            rows = session.scalars(page_query).all()
            items = [to_record(row) for row in rows]
        return PhotoPage(
            items=items, total=total, page=query.page, page_size=query.page_size
        )

    def filter_options(self) -> FilterOptions:
        """Return the values available for each filter.

        Raises:
            PersistenceError: If the query fails.
        """
        with self._read() as session:
            tags = Counter(
                tag for row in session.scalars(select(PhotoRow.tags)) for tag in row
            )
            earliest, latest = session.execute(
                select(func.min(PhotoRow.captured_at), func.max(PhotoRow.captured_at))
            ).one()
            kelvin_min, kelvin_max = session.execute(
                select(
                    func.min(PhotoRow.white_balance_k),
                    func.max(PhotoRow.white_balance_k),
                )
            ).one()
            return FilterOptions(
                scenes=self._distinct(session, PhotoRow.scene),
                tags=[tag for tag, _ in tags.most_common()],
                cameras=self._distinct(session, PhotoRow.model),
                lenses=self._distinct(session, PhotoRow.lens_model),
                annotated_by=self._distinct(session, PhotoRow.annotated_by),
                earliest=earliest.date() if earliest else None,
                latest=latest.date() if latest else None,
                kelvin_min=kelvin_min,
                kelvin_max=kelvin_max,
            )

    def tag_lists(self, query: PhotoQuery) -> list[list[str]]:
        """Return the tags of every photo matching ``query``'s filters.

        Raises:
            PersistenceError: If the query fails.
        """
        statement = apply_filters(select(PhotoRow.tags), query)
        with self._read() as session:
            return [list(tags) for tags in session.scalars(statement)]

    def get(self, path: Path) -> PhotoRecord | None:
        """Return one photo by path.

        Raises:
            PersistenceError: If the query fails.
        """
        with self._read() as session:
            row = session.scalars(
                select(PhotoRow).where(PhotoRow.path == str(path))
            ).one_or_none()
            return to_record(row) if row else None

    def near_duplicates(
        self, record: PhotoRecord, max_distance: int = NEAR_DUPLICATE_DISTANCE
    ) -> list[NearDuplicate]:
        """Return other photos within ``max_distance`` dHash bits, closest first.

        Raises:
            PersistenceError: If the query fails.
        """
        if record.dhash is None:
            return []
        with self._read() as session:
            candidates = session.execute(
                select(PhotoRow.path, PhotoRow.dhash).where(
                    PhotoRow.dhash.is_not(None), PhotoRow.path != str(record.path)
                )
            ).all()
            target = record.dhash
            close = sorted(
                (hamming_distance(target, dhash), path)
                for path, dhash in candidates
                if dhash is not None and len(dhash) == len(target)
            )
            matches = [(d, p) for d, p in close if d <= max_distance]
            rows = {
                row.path: row
                for row in session.scalars(
                    select(PhotoRow).where(PhotoRow.path.in_([p for _, p in matches]))
                )
            }
            return [
                NearDuplicate(record=to_record(rows[path]), distance=distance)
                for distance, path in matches
                if path in rows
            ]

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns.

        Raises:
            PersistenceError: If the query fails.
        """
        month = func.strftime("%Y-%m", PhotoRow.captured_at)
        with self._read() as session:
            return PhotoStats(
                total=session.scalar(select(func.count(PhotoRow.id))) or 0,
                with_gps=session.scalar(
                    select(func.count(PhotoRow.id)).where(
                        PhotoRow.gps_latitude.is_not(None)
                    )
                )
                or 0,
                with_people=session.scalar(
                    select(func.count(PhotoRow.id)).where(PhotoRow.contains_people)
                )
                or 0,
                by_scene=self._counts(session, PhotoRow.scene),
                by_lens=self._counts(session, PhotoRow.lens_model),
                by_camera=self._counts(session, PhotoRow.model),
                by_month=sorted(self._counts(session, month), key=lambda r: r.label),
                by_white_balance=self._kelvin_buckets(session),
            )

    def _read(self) -> "_ReadSession":
        return _ReadSession(self._session_factory)

    @staticmethod
    def _distinct(session: Session, column: Any) -> list[str]:
        query = select(column).where(column.is_not(None)).distinct().order_by(column)
        return [str(value) for value in session.scalars(query)]

    @staticmethod
    def _kelvin_buckets(session: Session) -> list[CountRow]:
        """Photos per 500 K band, labelled by the band's start (e.g. 5000)."""
        # ``//`` is integer division (SQLAlchemy 2's ``/`` is true division).
        bucket = (PhotoRow.white_balance_k // KELVIN_BUCKET) * KELVIN_BUCKET
        query = (
            select(bucket, func.count(PhotoRow.id))
            .where(PhotoRow.white_balance_k.is_not(None))
            .group_by(bucket)
            .order_by(bucket)
        )
        counts = {
            int(start): n for start, n in session.execute(query) if start is not None
        }
        if not counts:
            return []
        # Include empty bands between the coolest and warmest, so gaps show.
        bands = range(min(counts), max(counts) + KELVIN_BUCKET, KELVIN_BUCKET)
        return [CountRow(label=str(band), count=counts.get(band, 0)) for band in bands]

    @staticmethod
    def _counts(session: Session, column: Any) -> list[CountRow]:
        query = (
            select(column, func.count(PhotoRow.id))
            .group_by(column)
            .order_by(func.count(PhotoRow.id).desc())
        )
        return [
            CountRow(label=str(label) if label is not None else UNKNOWN_LABEL, count=n)
            for label, n in session.execute(query)
        ]


class _ReadSession:
    """Opens a session and turns database errors into :class:`PersistenceError`."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Session:
        self._session = self._session_factory()
        return self._session

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        if self._session is not None:
            self._session.close()
        if isinstance(exc, SQLAlchemyError):
            raise PersistenceError(f"Photo query failed: {exc}") from exc


def apply_filters(statement: Select[Any], query: PhotoQuery) -> Select[Any]:
    """Add a ``WHERE`` clause for every filter set in ``query``."""
    conditions: list[Any] = []
    if query.text and query.text.strip():
        pattern = f"%{escape_like(query.text.strip())}%"
        conditions.append(
            or_(
                PhotoRow.description.ilike(pattern, escape=LIKE_ESCAPE),
                cast(PhotoRow.tags, Text).ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    conditions.extend(_tag_condition(tag) for tag in query.tags)
    if query.scenes:
        conditions.append(PhotoRow.scene.in_(query.scenes))
    if query.contains_people is not None:
        conditions.append(PhotoRow.contains_people.is_(query.contains_people))
    if query.cameras:
        conditions.append(PhotoRow.model.in_(query.cameras))
    if query.lenses:
        conditions.append(PhotoRow.lens_model.in_(query.lenses))
    if query.annotated_by:
        conditions.append(PhotoRow.annotated_by.in_(query.annotated_by))
    if query.date_from:
        conditions.append(
            PhotoRow.captured_at >= datetime.combine(query.date_from, time.min)
        )
    if query.date_to:
        conditions.append(
            PhotoRow.captured_at <= datetime.combine(query.date_to, time.max)
        )
    if query.only_with_gps:
        conditions.append(PhotoRow.gps_latitude.is_not(None))
    if query.kelvin_min is not None:
        conditions.append(PhotoRow.white_balance_k >= query.kelvin_min)
    if query.kelvin_max is not None:
        conditions.append(PhotoRow.white_balance_k <= query.kelvin_max)
    return statement.where(*conditions)


def apply_sort(statement: Select[Any], sort: SortOrder) -> Select[Any]:
    """Order results; photos without a capture date sort last."""
    if sort is SortOrder.PROCESSED_NEWEST:
        return statement.order_by(PhotoRow.processed_at.desc(), PhotoRow.path)
    captured = (
        PhotoRow.captured_at.asc()
        if sort is SortOrder.CAPTURED_OLDEST
        else PhotoRow.captured_at.desc()
    )
    return statement.order_by(captured.nulls_last(), PhotoRow.path)


def escape_like(text: str) -> str:
    """Escape ``%``, ``_`` and the escape character for a ``LIKE`` pattern."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def _tag_condition(tag: str) -> Any:
    """Exact match of one element in the JSON ``tags`` array."""
    element = json.dumps(tag)  # '"sunset"' - quotes make it an exact element
    pattern = f"%{escape_like(element)}%"
    return cast(PhotoRow.tags, Text).like(pattern, escape=LIKE_ESCAPE)
