"""A :class:`~my_agent.ui.library.PhotoLibrary` cached with Streamlit.

Results are shared across browser sessions and expire after
:data:`CACHE_TTL_S`, so photos saved by a running pipeline show up on their
own. The cached functions take the data sources as underscore-prefixed
arguments (Streamlit does not hash those) plus a hashed ``cache_key``, so two
databases never share cached results.
"""

from pathlib import Path

import streamlit as st

from my_agent.db.catalog import PhotoCatalog
from my_agent.db.failure_repository import FailureRepository
from my_agent.schemas import FailureRecord, PhotoRecord
from my_agent.schemas.query import (
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
)

CACHE_TTL_S = 30  # pick up photos saved by a running pipeline


class CachedPhotoLibrary:
    """Reads from a catalog and a failure log, caching each answer briefly.

    Args:
        catalog: Read-only photo queries.
        failures: The processing-failure log.
        cache_key: Identifies the data source (e.g. the database URL).
    """

    def __init__(
        self, catalog: PhotoCatalog, failures: FailureRepository, cache_key: str
    ) -> None:
        self._catalog = catalog
        self._failures = failures
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

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        return _stats(self._catalog, self._key)

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
def _stats(_catalog: PhotoCatalog, key: str) -> PhotoStats:
    return _catalog.stats()


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _failures(_failures: FailureRepository, key: str) -> list[FailureRecord]:
    return _failures.all_failures()
