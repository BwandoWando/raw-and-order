"""A :class:`~raw_and_order.ui.library.PhotoLibrary` cached with Streamlit.

Results are shared across browser sessions and expire after
:data:`CACHE_TTL_S`, so photos saved by a running pipeline show up on their
own. The cached functions take the data sources as underscore-prefixed
arguments (Streamlit does not hash those) plus a hashed ``cache_key``, so two
databases never share cached results.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import streamlit as st

from raw_and_order.analysis.tag_graph import build_tag_graph
from raw_and_order.analysis.tag_samples import sample_by_tag
from raw_and_order.db.catalog import PhotoCatalog
from raw_and_order.db.failure_repository import FailureRepository
from raw_and_order.db.favorite_repository import FavoriteStore
from raw_and_order.db.trash_repository import TrashStore
from raw_and_order.exceptions import PreviewError
from raw_and_order.media.protocols import Thumbnailer
from raw_and_order.schemas import FailureRecord, PhotoRecord
from raw_and_order.schemas.query import (
    FilterOptions,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
    SimilarPhoto,
)
from raw_and_order.schemas.tags import TagGraph

CACHE_TTL_S = 30  # pick up photos saved by a running pipeline
THUMBNAIL_CACHE_ENTRIES = 3000  # about 30 full pages of 99


class CachedPhotoLibrary:
    """Reads from a catalog and a failure log, caching each answer briefly.

    Favorites and deletion marks are read fresh every time, so a click shows
    the moment it is made.
    Thumbnails, square crops and preview sizes have no expiry; they are keyed
    by the preview's modification time instead.

    Args:
        catalog: Read-only photo queries.
        failures: The processing-failure log.
        favorites: Which photos are favorites (the UI writes these).
        trash: Which photos are marked for deletion (the UI writes these).
        thumbnailer: Shrinks previews for the gallery grid.
        cache_key: Identifies the data source (e.g. the database URL).
    """

    def __init__(
        self,
        catalog: PhotoCatalog,
        failures: FailureRepository,
        favorites: FavoriteStore,
        trash: TrashStore,
        thumbnailer: Thumbnailer,
        cache_key: str,
    ) -> None:
        self._catalog = catalog
        self._failures = failures
        self._favorites = favorites
        self._trash = trash
        self._thumbnailer = thumbnailer
        self._key = cache_key

    def export_records(self, query: PhotoQuery) -> list[PhotoRecord]:
        """Every matching photo, read fresh: exports run rarely and off-script."""
        return self._catalog.matching(query)

    def search(self, query: PhotoQuery) -> PhotoPage:
        """Return one page of photos matching ``query``."""
        return _search(self._catalog, self._key, query.model_dump_json())

    def filter_options(self) -> FilterOptions:
        """Return the values available for each sidebar filter."""
        return _filter_options(self._catalog, self._key)

    def photo(self, path: Path) -> PhotoRecord | None:
        """Return one photo by path, or ``None`` if it is not stored."""
        return _photo(self._catalog, self._key, str(path))

    def similar_photos(self, path: Path, query: PhotoQuery) -> list[SimilarPhoto]:
        """Return photos like the one at ``path`` matching ``query``, closest first."""
        return _similar_photos(
            self._catalog, self._key, str(path), query.model_dump_json()
        )

    def position(self, path: Path, query: PhotoQuery) -> int | None:
        """Return the photo's place (from 1) in ``query``'s results, or ``None``."""
        return _position(self._catalog, self._key, str(path), query.model_dump_json())

    def copies_of(self, path: Path) -> list[Path]:
        """Return the exact copies found of the photo at ``path``."""
        return [Path(p) for p in _copies_of(self._catalog, self._key, str(path))]

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes | None:
        """Return a small JPEG of a preview, or ``None`` if it is missing.

        Cached per file version (modification time), so a re-saved preview
        gets a fresh thumbnail.
        """
        try:
            version = preview_path.stat().st_mtime_ns
            return _thumbnail(self._thumbnailer, str(preview_path), max_px, version)
        except (OSError, PreviewError):
            return None

    def square_thumbnail(self, preview_path: Path, px: int) -> bytes | None:
        """Return the preview's centre as a ``px`` square JPEG, or ``None``.

        ``None`` if the preview is missing; cached per file version, like
        :meth:`thumbnail`.
        """
        try:
            version = preview_path.stat().st_mtime_ns
            return _square(self._thumbnailer, str(preview_path), px, version)
        except (OSError, PreviewError):
            return None

    def preview_size(self, preview_path: Path) -> tuple[int, int] | None:
        """Return a preview's width and height, or ``None`` if it is missing.

        Cached per file version, like :meth:`thumbnail`.
        """
        try:
            version = preview_path.stat().st_mtime_ns
            return _preview_size(self._thumbnailer, str(preview_path), version)
        except (OSError, PreviewError):
            return None

    def is_favorite(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is a favorite (not cached)."""
        return self._favorites.is_favorite(path)

    def set_favorite(self, path: Path, favorite: bool) -> None:
        """Mark or unmark the photo, stamped with this computer's local time.

        Cached results that follow the filters are dropped, since the
        "Favorites only" filter changes what they contain.
        """
        self._favorites.set_favorite(path, favorite, when=datetime.now())
        _forget_filtered_results()

    def is_trashed(self, path: Path) -> bool:
        """Return True if the photo is marked for deletion (not cached)."""
        return self._trash.is_trashed(path)

    def set_trashed(self, path: Path, trashed: bool) -> None:
        """Mark or unmark the photo for deletion, stamped with local time.

        Cached results that follow the filters are dropped, since the
        "Marked for deletion only" filter changes what they contain.
        """
        self._trash.set_trashed(path, trashed, when=datetime.now())
        _forget_filtered_results()

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        return _stats(self._catalog, self._key)

    def tag_graph(
        self, filters: PhotoQuery, top_n: int, min_strength: float
    ) -> TagGraph:
        """Return the network of the ``top_n`` most-used tags under ``filters``.

        See :meth:`PhotoLibrary.tag_graph
        <raw_and_order.ui.library.PhotoLibrary.tag_graph>` for the arguments.
        """
        # Paging and sort do not change the graph; dropping them gets more cache hits.
        return _tag_graph(
            self._catalog,
            self._key,
            filters.filters_only().model_dump_json(),
            top_n,
            min_strength,
        )

    def failures(self) -> list[FailureRecord]:
        """Return every logged failure."""
        return _failures(self._failures, self._key)

    def tag_samples(
        self, filters: PhotoQuery, tags: Sequence[str], per_tag: int, seed: int
    ) -> dict[str, list[Path]]:
        """Return up to ``per_tag`` random previews for each of ``tags``.

        See :meth:`PhotoLibrary.tag_samples
        <raw_and_order.ui.library.PhotoLibrary.tag_samples>` for the arguments.
        """
        samples = _tag_samples(
            self._catalog,
            self._key,
            filters.filters_only().model_dump_json(),
            tuple(tags),
            per_tag,
            seed,
        )
        return {tag: [Path(p) for p in paths] for tag, paths in samples.items()}

    def refresh(self) -> None:
        """Forget cached results so the next read sees fresh data.

        This clears every ``st.cache_data`` cache in the process, thumbnails
        included, for all browser sessions.
        """
        st.cache_data.clear()


def _forget_filtered_results() -> None:
    """Drop every cached answer that depends on the sidebar filters.

    Called after a favorite or deletion mark changes, since the "Favorites
    only" and "Marked for deletion only" filters read those marks.
    """
    for cached in (_search, _tag_graph, _tag_samples, _similar_photos, _position):
        cached.clear()


# The query travels as JSON so it hashes reliably as a cache key. In all the
# cached functions below, ``key`` is unused in the body: it is there only so
# that each database gets its own cache entries.
@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _search(_catalog: PhotoCatalog, key: str, query_json: str) -> PhotoPage:
    return _catalog.search(PhotoQuery.model_validate_json(query_json))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _filter_options(_catalog: PhotoCatalog, key: str) -> FilterOptions:
    return _catalog.filter_options()


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _photo(_catalog: PhotoCatalog, key: str, path: str) -> PhotoRecord | None:
    return _catalog.get(Path(path))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _similar_photos(
    _catalog: PhotoCatalog, key: str, path: str, query_json: str
) -> list[SimilarPhoto]:
    record = _catalog.get(Path(path))
    if record is None:
        return []
    return _catalog.similar_photos(record, PhotoQuery.model_validate_json(query_json))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _position(
    _catalog: PhotoCatalog, key: str, path: str, query_json: str
) -> int | None:
    query = PhotoQuery.model_validate_json(query_json)
    return _catalog.position(Path(path), query)


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _copies_of(_catalog: PhotoCatalog, key: str, path: str) -> list[str]:
    return [str(p) for p in _catalog.copies_of(Path(path))]


@st.cache_data(max_entries=THUMBNAIL_CACHE_ENTRIES, show_spinner=False)
def _thumbnail(
    _thumbnailer: Thumbnailer, preview_path: str, max_px: int, version: int
) -> bytes:
    return _thumbnailer.thumbnail(Path(preview_path), max_px)


@st.cache_data(max_entries=THUMBNAIL_CACHE_ENTRIES, show_spinner=False)
def _square(
    _thumbnailer: Thumbnailer, preview_path: str, px: int, version: int
) -> bytes:
    return _thumbnailer.square(Path(preview_path), px)


@st.cache_data(max_entries=THUMBNAIL_CACHE_ENTRIES, show_spinner=False)
def _preview_size(
    _thumbnailer: Thumbnailer, preview_path: str, version: int
) -> tuple[int, int]:
    return _thumbnailer.size(Path(preview_path))


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _stats(_catalog: PhotoCatalog, key: str) -> PhotoStats:
    return _catalog.stats()


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _tag_graph(
    _catalog: PhotoCatalog,
    key: str,
    filters_json: str,
    top_n: int,
    min_strength: float,
) -> TagGraph:
    tag_lists = _catalog.tag_lists(PhotoQuery.model_validate_json(filters_json))
    return build_tag_graph(tag_lists, top_n, min_strength)


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _tag_samples(
    _catalog: PhotoCatalog,
    key: str,
    filters_json: str,
    tags: tuple[str, ...],
    per_tag: int,
    seed: int,
) -> dict[str, list[str]]:
    photos = _catalog.tagged_previews(PhotoQuery.model_validate_json(filters_json))
    samples = sample_by_tag(photos, tags, per_tag, seed)
    return {tag: [str(p) for p in paths] for tag, paths in samples.items()}


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _failures(_failures: FailureRepository, key: str) -> list[FailureRecord]:
    return _failures.all_failures()
