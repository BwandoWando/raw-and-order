"""Read-side models: photo search filters, results, filter options and stats."""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from raw_and_order.schemas.photo import PhotoRecord

PAGE_SIZES = (24, 48, 72, 99)
# PhotoStats conventions shared by the catalog (which fills it) and the UI.
UNKNOWN_LABEL = "Unknown"  # label of the count for photos without the value
KELVIN_BAND_K = 500  # width of a white balance band in by_white_balance


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
    only_favorites: bool = Field(
        default=False, description="Only photos starred in the photo details."
    )
    kelvin_min: int | None = Field(default=None, description="White balance, K.")
    kelvin_max: int | None = None
    annotated_by: tuple[str, ...] = ()
    sort: SortOrder = SortOrder.CAPTURED_NEWEST
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=PAGE_SIZES[0], ge=1)

    def filters_only(self) -> "PhotoQuery":
        """This query with the default sort and first page: just its filters.

        For answers that do not depend on order or paging (a count, the tag
        network, an export), so equal filters compare and cache as equal.
        """
        return self.model_copy(update=_PAGING_DEFAULTS)

    def has_filters(self) -> bool:
        """True if any filter narrows the photos (sort and paging aside)."""
        return self.filters_only() != PhotoQuery()


_PAGING_DEFAULTS = {
    name: PhotoQuery.model_fields[name].get_default(call_default_factory=True)
    for name in ("sort", "page", "page_size")
}


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
    tag_counts: dict[str, int] = Field(
        default_factory=dict, description="Photos per tag."
    )
    cameras: list[str]
    lenses: list[str]
    annotated_by: list[str]
    earliest: date | None
    latest: date | None
    kelvin_min: int | None = None
    kelvin_max: int | None = None


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
    by_white_balance: list[CountRow] = Field(
        default_factory=list,
        description="KELVIN_BAND_K-wide bands, lowest kelvin (warmest light) first.",
    )
    copies: int = Field(default=0, description="Exact copies skipped as duplicates.")


class SimilarPhoto(BaseModel):
    """A visually similar photo and its pHash distance (0 = identical)."""

    record: PhotoRecord
    distance: int
