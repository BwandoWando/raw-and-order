"""EXIF metadata models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DateSource(StrEnum):
    """Where a photo's capture date came from."""

    EXIF_ORIGINAL = "exif_original"
    XMP = "xmp"
    EXIF_CREATE = "exif_create"
    FILENAME = "filename"
    NONE = "none"


class GpsCoordinate(BaseModel):
    """A GPS position in signed decimal degrees."""

    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_m: float | None = None


class ExifData(BaseModel):
    """The subset of EXIF metadata the application uses."""

    model_config = ConfigDict(frozen=True)

    make: str | None = None
    model: str | None = None
    lens_model: str | None = None
    lens_make: str | None = None
    lens_spec: str | None = None
    iso: int | None = None
    exposure_time_s: float | None = None
    f_number: float | None = None
    focal_length_mm: float | None = None
    captured_at: datetime | None = None
    date_source: DateSource | None = Field(
        default=None,
        description="Which source captured_at came from; None for legacy rows.",
    )
    width_px: int | None = None
    height_px: int | None = None
    gps: GpsCoordinate | None = None
