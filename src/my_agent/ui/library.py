"""The read-only port the UI depends on.

Renderers receive a :class:`PhotoLibrary` instead of reaching for global
services, so tests can hand them an in-memory fake.
"""

from pathlib import Path
from typing import Protocol

from my_agent.schemas import FailureRecord, PhotoRecord
from my_agent.schemas.query import (
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
)
from my_agent.schemas.tags import TagGraph


class PhotoLibrary(Protocol):
    """Everything the UI reads about stored photos and failures."""

    def export_records(self, query: PhotoQuery) -> list[PhotoRecord]:
        """Return every photo matching ``query``'s filters (not cached)."""
        ...

    def search(self, query: PhotoQuery) -> PhotoPage:
        """Return one page of photos matching ``query``."""
        ...

    def filter_options(self) -> FilterOptions:
        """Return the values available for each sidebar filter."""
        ...

    def photo(self, path: Path) -> PhotoRecord | None:
        """Return one photo by path, or ``None`` if it is not stored."""
        ...

    def near_duplicates(self, path: Path) -> list[NearDuplicate]:
        """Return photos that look like the one at ``path``, closest first."""
        ...

    def copies_of(self, path: Path) -> list[Path]:
        """Return the exact copies found of the photo at ``path``."""
        ...

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes | None:
        """Return a small JPEG of a preview, or ``None`` if it is missing."""
        ...

    def stats(self) -> PhotoStats:
        """Return totals and breakdowns."""
        ...

    def tag_graph(
        self, filters: PhotoQuery, top_n: int, min_strength: float
    ) -> TagGraph:
        """Return the network of the ``top_n`` most-used tags under ``filters``."""
        ...

    def failures(self) -> list[FailureRecord]:
        """Return every logged failure."""
        ...

    def refresh(self) -> None:
        """Forget cached results so the next read sees fresh data."""
        ...
