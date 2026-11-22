"""The port the UI depends on for everything stored.

Renderers receive a :class:`PhotoLibrary` instead of reaching for global
services, so tests can hand them an in-memory fake. It only reads, except
for favorites, which the photo details set.
"""

from pathlib import Path
from typing import Protocol

from raw_and_order.schemas import FailureRecord, PhotoRecord
from raw_and_order.schemas.query import (
    FilterOptions,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
    SimilarPhoto,
)
from raw_and_order.schemas.tags import TagGraph


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

    def similar_photos(self, path: Path) -> list[SimilarPhoto]:
        """Return photos that look like the one at ``path``, closest first."""
        ...

    def copies_of(self, path: Path) -> list[Path]:
        """Return the exact copies found of the photo at ``path``."""
        ...

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes | None:
        """Return a small JPEG of a preview, or ``None`` if it is missing."""
        ...

    def preview_size(self, preview_path: Path) -> tuple[int, int] | None:
        """Return a preview's width and height, or ``None`` if it is missing."""
        ...

    def is_favorite(self, path: Path) -> bool:
        """Return True if the photo at ``path`` is a favorite."""
        ...

    def set_favorite(self, path: Path, favorite: bool) -> None:
        """Mark (``favorite=True``) or unmark the photo at ``path`` as a favorite."""
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
