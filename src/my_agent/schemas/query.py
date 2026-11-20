"""Read-side models: photo search filters, results, filter options and stats."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from my_agent.schemas.photo import PhotoRecord

PAGE_SIZES = (24, 48, 72, 96)


class SortOrder(StrEnum):
    """How search results are ordered."""

    CAPTURED_NEWEST = "captured_newest"
    CAPTURED_OLDEST = "captured_oldest"
    PROCESSED_NEWEST = "processed_newest"


class PhotoQuery(BaseModel):
    """Filters, sort and page for a photo search. Empty filters match all."""

    model_config = ConfigDict(frozen=True)

    text: str | None = Field(default=None, description="Matches description or tags.")
    scenes: tuple[str, ...] = ()
    tags: tuple[str, ...] = Field(default=(), description="Photo must have all.")
    contains_people: bool | None = None
    cameras: tuple[str, ...] = ()
    lenses: tuple[str, ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    only_with_gps: bool = False
    annotated_by: tuple[str, ...] = ()
    sort: SortOrder = SortOrder.CAPTURED_NEWEST
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=PAGE_SIZES[0], ge=1)


class PhotoPage(BaseModel):
    """One page of search results."""

    items: list[PhotoRecord]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        """Number of pages (at least 1)."""
        return max(1, -(-self.total // self.page_size))


class FilterOptions(BaseModel):
    """Values available for each filter, from the stored photos."""

    scenes: list[str]
    tags: list[str] = Field(description="Most frequent first.")
    cameras: list[str]
    lenses: list[str]
    annotated_by: list[str]
    earliest: date | None
    latest: date | None


class CountRow(BaseModel):
    """A label and how many photos have it."""

    label: str
    count: int


class PhotoStats(BaseModel):
    """Totals and breakdowns for the Stats tab."""

    total: int
    with_gps: int
    with_people: int
    by_scene: list[CountRow]
    by_lens: list[CountRow]
    by_camera: list[CountRow]
    by_month: list[CountRow] = Field(description="YYYY-MM, oldest first.")


class NearDuplicate(BaseModel):
    """A visually similar photo and its dHash distance (0 = identical)."""

    record: PhotoRecord
    distance: int
