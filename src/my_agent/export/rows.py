"""Flatten a stored photo into one export row (pure, no I/O)."""

from datetime import datetime
from typing import Any

from my_agent.schemas import PhotoRecord

COLUMNS = (
    "file_name",
    "folder",
    "path",
    "taken_at",
    "date_source",
    "camera_make",
    "camera_model",
    "lens",
    "lens_make",
    "lens_range",
    "focal_length_mm",
    "aperture_f",
    "shutter_s",
    "iso",
    "white_balance",
    "white_balance_k",
    "width_px",
    "height_px",
    "latitude",
    "longitude",
    "altitude_m",
    "description",
    "tags",
    "scene",
    "contains_people",
    "annotated_by",
    "processed_at_utc",
    "sha256",
    "phash",
    "preview_path",
)

Value = str | int | float | bool | datetime | list[str] | None


def photo_row(record: PhotoRecord) -> dict[str, Value]:
    """One row with every :data:`COLUMNS` key; missing values are ``None``.

    ``tags`` stays a list; each format decides how to write it.
    """
    exif, note, gps = record.exif, record.annotation, record.exif.gps
    row: dict[str, Any] = {
        "file_name": record.path.name,
        "folder": str(record.path.parent),
        "path": str(record.path),
        "taken_at": exif.captured_at,
        "date_source": exif.date_source.value if exif.date_source else None,
        "camera_make": exif.make,
        "camera_model": exif.model,
        "lens": exif.lens_model,
        "lens_make": exif.lens_make,
        "lens_range": exif.lens_spec,
        "focal_length_mm": exif.focal_length_mm,
        "aperture_f": exif.f_number,
        "shutter_s": exif.exposure_time_s,
        "iso": exif.iso,
        "white_balance": exif.white_balance,
        "white_balance_k": exif.white_balance_k,
        "width_px": exif.width_px,
        "height_px": exif.height_px,
        "latitude": gps.latitude if gps else None,
        "longitude": gps.longitude if gps else None,
        "altitude_m": gps.altitude_m if gps else None,
        "description": note.description,
        "tags": list(note.tags),
        "scene": note.scene.value,
        "contains_people": note.contains_people,
        "annotated_by": record.annotated_by,
        "processed_at_utc": record.processed_at,
        "sha256": record.sha256,
        "phash": record.phash,
        "preview_path": str(record.preview_path),
    }
    return {column: row[column] for column in COLUMNS}
