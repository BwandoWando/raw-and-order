"""Flatten a stored photo into one export row (pure, no I/O)."""

from collections.abc import Callable
from datetime import datetime

from raw_and_order.schemas import PhotoRecord

Value = str | int | float | bool | datetime | list[str] | None
Column = tuple[str, Callable[[PhotoRecord], Value]]


def _gps(record: PhotoRecord, field: str) -> float | None:
    """One GPS coordinate, or ``None`` for photos without GPS."""
    gps = record.exif.gps
    return getattr(gps, field) if gps else None


# The export's columns in order, each with how to read it from a photo. The
# one place a column is defined: COLUMNS and every row come from here.
_COLUMN_SPECS: tuple[Column, ...] = (
    ("file_name", lambda r: r.path.name),
    ("folder", lambda r: str(r.path.parent)),
    ("path", lambda r: str(r.path)),
    ("taken_at", lambda r: r.exif.captured_at),
    ("date_source", lambda r: r.exif.date_source.value if r.exif.date_source else None),
    ("camera_make", lambda r: r.exif.make),
    ("camera_model", lambda r: r.exif.model),
    ("lens", lambda r: r.exif.lens_model),
    ("lens_make", lambda r: r.exif.lens_make),
    ("lens_range", lambda r: r.exif.lens_spec),
    ("focal_length_mm", lambda r: r.exif.focal_length_mm),
    ("aperture_f", lambda r: r.exif.f_number),
    ("shutter_s", lambda r: r.exif.exposure_time_s),
    ("iso", lambda r: r.exif.iso),
    ("white_balance", lambda r: r.exif.white_balance),
    ("white_balance_k", lambda r: r.exif.white_balance_k),
    ("width_px", lambda r: r.exif.width_px),
    ("height_px", lambda r: r.exif.height_px),
    ("latitude", lambda r: _gps(r, "latitude")),
    ("longitude", lambda r: _gps(r, "longitude")),
    ("altitude_m", lambda r: _gps(r, "altitude_m")),
    ("description", lambda r: r.annotation.description),
    ("tags", lambda r: list(r.annotation.tags)),
    ("scene", lambda r: r.annotation.scene.value),
    ("contains_people", lambda r: r.annotation.contains_people),
    ("annotated_by", lambda r: r.annotated_by),
    ("processed_at_utc", lambda r: r.processed_at),
    ("sha256", lambda r: r.sha256),
    ("phash", lambda r: r.phash),
    ("preview_path", lambda r: str(r.preview_path)),
)
COLUMNS = tuple(name for name, _ in _COLUMN_SPECS)


def photo_row(record: PhotoRecord) -> dict[str, Value]:
    """One row with every :data:`COLUMNS` key, in order; missing values are ``None``.

    ``tags`` stays a list; each format decides how to write it.
    """
    return {name: read(record) for name, read in _COLUMN_SPECS}
