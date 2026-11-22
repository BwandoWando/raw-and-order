"""Read-only queries over stored photos, for the UI.

Kept separate from :mod:`raw_and_order.db.repository`, which writes. Everything
here only reads, so it is safe to use while a processing run is writing
(SQLite runs in WAL mode).
"""

import json
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, time
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.analysis.similarity import SIMILAR_MAX_DISTANCE, shares_tags
from raw_and_order.db.errors import database_errors
from raw_and_order.db.mappers import to_record
from raw_and_order.db.models import CopyRow, PhotoRow
from raw_and_order.media.hashing import hamming_distance
from raw_and_order.schemas import PhotoRecord
from raw_and_order.schemas.query import (
    KELVIN_BAND_K,
    UNKNOWN_LABEL,
    CountRow,
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
    SortOrder,
)

LIKE_ESCAPE = "\\"


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
        self, record: PhotoRecord, max_distance: int = SIMILAR_MAX_DISTANCE
    ) -> list[NearDuplicate]:
        """Return similar photos (close pHash and shared tags), closest first."""
        ...

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        ...

    def tag_lists(self, query: PhotoQuery) -> list[list[str]]:
        """Return the tags of every photo matching ``query``'s filters."""
        ...

    def matching(self, query: PhotoQuery) -> list[PhotoRecord]:
        """Return every photo matching ``query``'s filters, in its sort order."""
        ...

    def copies_of(self, path: Path) -> list[Path]:
        """Return the exact copies found of the photo at ``path``."""
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

    def matching(self, query: PhotoQuery) -> list[PhotoRecord]:
        """Return every photo matching ``query``'s filters, unpaged.

        Raises:
            PersistenceError: If the query fails.
        """
        statement = apply_sort(apply_filters(select(PhotoRow), query), query.sort)
        with self._read() as session:
            return [to_record(row) for row in session.scalars(statement)]

    def filter_options(self) -> FilterOptions:
        """Return the values available for each filter.

        Raises:
            PersistenceError: If the query fails.
        """
        with self._read() as session:
            tags = Counter(  # each photo counts once per tag
                tag
                for row in session.scalars(select(PhotoRow.tags))
                for tag in set(row)
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
                tag_counts=dict(tags),
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

    def copies_of(self, path: Path) -> list[Path]:
        """Return the exact copies found of the photo at ``path``, sorted.

        Raises:
            PersistenceError: If the query fails.
        """
        statement = (
            select(CopyRow.path)
            .where(CopyRow.original_path == str(path))
            .order_by(CopyRow.path)
        )
        with self._read() as session:
            return [Path(p) for p in session.scalars(statement)]

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
        self, record: PhotoRecord, max_distance: int = SIMILAR_MAX_DISTANCE
    ) -> list[NearDuplicate]:
        """Return similar photos, closest first.

        Similar means within ``max_distance`` pHash bits *and* sharing enough
        tags (:func:`~raw_and_order.analysis.similarity.shares_tags`).

        Raises:
            PersistenceError: If the query fails.
        """
        if record.phash is None:
            return []
        with self._read() as session:
            close = self._close_by_phash(session, record, max_distance)
            rows = {
                row.path: row
                for row in session.scalars(
                    select(PhotoRow).where(PhotoRow.path.in_([p for _, p in close]))
                )
            }
            matches = [
                NearDuplicate(record=to_record(rows[path]), distance=distance)
                for distance, path in close
                if path in rows
            ]
        tags = record.annotation.tags
        return [m for m in matches if shares_tags(tags, m.record.annotation.tags)]

    @staticmethod
    def _close_by_phash(
        session: Session, record: PhotoRecord, max_distance: int
    ) -> list[tuple[int, str]]:
        """``(distance, path)`` of other photos within ``max_distance`` bits."""
        candidates = session.execute(
            select(PhotoRow.path, PhotoRow.phash).where(
                PhotoRow.phash.is_not(None), PhotoRow.path != str(record.path)
            )
        ).all()
        target = record.phash or ""
        close = sorted(
            (hamming_distance(target, phash), path)
            for path, phash in candidates
            if phash is not None and len(phash) == len(target)
        )
        return [(d, p) for d, p in close if d <= max_distance]

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
                copies=session.scalar(select(func.count(CopyRow.id))) or 0,
            )

    @contextmanager
    def _read(self) -> Iterator[Session]:
        """A read session; database errors become :class:`PersistenceError`."""
        with database_errors("query photos"), self._session_factory() as session:
            yield session

    @staticmethod
    def _distinct(session: Session, column: Any) -> list[str]:
        query = select(column).where(column.is_not(None)).distinct().order_by(column)
        return [str(value) for value in session.scalars(query)]

    @staticmethod
    def _kelvin_buckets(session: Session) -> list[CountRow]:
        """Photos per white balance band, labelled by its start (e.g. 5000)."""
        # ``//`` is integer division (SQLAlchemy 2's ``/`` is true division).
        bucket = (PhotoRow.white_balance_k // KELVIN_BAND_K) * KELVIN_BAND_K
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
        # Include empty bands between the lowest and highest, so gaps show.
        bands = range(min(counts), max(counts) + KELVIN_BAND_K, KELVIN_BAND_K)
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
