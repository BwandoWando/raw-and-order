"""A :class:`~my_agent.ui.library.PhotoLibrary` cached with Streamlit.

Results are shared across browser sessions and expire after
:data:`CACHE_TTL_S`, so photos saved by a running pipeline show up on their
own. The cached functions take the data sources as underscore-prefixed
arguments (Streamlit does not hash those) plus a hashed ``cache_key``, so two
databases never share cached results.
"""

from pathlib import Path

import streamlit as st

from my_agent.analysis.tag_graph import build_tag_graph
from my_agent.db.catalog import PhotoCatalog
from my_agent.db.failure_repository import FailureRepository
from my_agent.exceptions import PreviewError
from my_agent.media.protocols import Thumbnailer
from my_agent.schemas import FailureRecord, PhotoRecord
from my_agent.schemas.query import (
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
)
from my_agent.schemas.tags import TagGraph

CACHE_TTL_S = 30  # pick up photos saved by a running pipeline
THUMBNAIL_CACHE_ENTRIES = 3000  # about 30 full pages of 99
PAGING_FIELDS = {"page", "page_size", "sort"}


class CachedPhotoLibrary:
    """Reads from a catalog and a failure log, caching each answer briefly.

    Args:
        catalog: Read-only photo queries.
        failures: The processing-failure log.
        thumbnailer: Shrinks previews for the gallery grid.
        cache_key: Identifies the data source (e.g. the database URL).
    """

    def __init__(
        self,
        catalog: PhotoCatalog,
        failures: FailureRepository,
        thumbnailer: Thumbnailer,
        cache_key: str,
    ) -> None:
        self._catalog = catalog
        self._failures = failures
        self._thumbnailer = thumbnailer
        self._key = cache_key

    def search(self, query: PhotoQuery) -> PhotoPage:
        """Return one page of photos matching ``query``."""
        return _search(self._catalog, self._key, query.model_dump_json())

    def filter_options(self) -> FilterOptions:
        """Return the values available for each sidebar filter."""
        return _filter_options(self._catalog, self._key)

    def photo(self, path: Path) -> PhotoRecord | None:
        """Return one photo by path, or ``None`` if it is not stored."""
        return _photo(self._catalog, self._key, str(path))

    def near_duplicates(self, path: Path) -> list[NearDuplicate]:
        """Return photos that look like the one at ``path``, closest first."""
        return _near_duplicates(self._catalog, self._key, str(path))

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

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        return _stats(self._catalog, self._key)

    def tag_graph(
        self, filters: PhotoQuery, top_n: int, min_strength: float
    ) -> TagGraph:
        """Return the network of the ``top_n`` most-used tags under ``filters``."""
        # Paging and sort do not change the graph; reset them for more cache hits.
        filters_only = PhotoQuery(**filters.model_dump(exclude=PAGING_FIELDS))
        return _tag_graph(
            self._catalog,
            self._key,
            filters_only.model_dump_json(),
            top_n,
            min_strength,
        )

    def failures(self) -> list[FailureRecord]:
        """Return every logged failure."""
        return _failures(self._failures, self._key)

    def refresh(self) -> None:
        """Forget cached results so the next read sees fresh data."""
        st.cache_data.clear()


# The query travels as JSON so it hashes reliably as a cache key.
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
def _near_duplicates(
    _catalog: PhotoCatalog, key: str, path: str
) -> list[NearDuplicate]:
    record = _catalog.get(Path(path))
    return _catalog.near_duplicates(record) if record else []


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _copies_of(_catalog: PhotoCatalog, key: str, path: str) -> list[str]:
    return [str(p) for p in _catalog.copies_of(Path(path))]


@st.cache_data(max_entries=THUMBNAIL_CACHE_ENTRIES, show_spinner=False)
def _thumbnail(
    _thumbnailer: Thumbnailer, preview_path: str, max_px: int, version: int
) -> bytes:
    return _thumbnailer.thumbnail(Path(preview_path), max_px)


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
def _failures(_failures: FailureRepository, key: str) -> list[FailureRecord]:
    return _failures.all_failures()
