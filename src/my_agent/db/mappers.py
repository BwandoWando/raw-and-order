"""Conversion between Pydantic records and ORM rows."""

from pathlib import Path

from my_agent.db.models import PhotoRow
from my_agent.schemas import (
    Annotation,
    DateSource,
    ExifData,
    GpsCoordinate,
    PhotoRecord,
)


def apply_record(row: PhotoRow, record: PhotoRecord) -> PhotoRow:
    """Copy every field of ``record`` onto ``row`` and return it."""
    exif, annotation, gps = record.exif, record.annotation, record.exif.gps
    row.path = str(record.path)
    row.sha256 = record.sha256
    row.dhash = record.dhash
    row.preview_path = str(record.preview_path)
    row.make = exif.make
    row.model = exif.model
    row.lens_model = exif.lens_model
    row.lens_make = exif.lens_make
    row.lens_spec = exif.lens_spec
    row.iso = exif.iso
    row.exposure_time_s = exif.exposure_time_s
    row.f_number = exif.f_number
    row.focal_length_mm = exif.focal_length_mm
    row.captured_at = exif.captured_at
    row.date_source = exif.date_source.value if exif.date_source else None
    row.width_px = exif.width_px
    row.height_px = exif.height_px
    row.gps_latitude = gps.latitude if gps else None
    row.gps_longitude = gps.longitude if gps else None
    row.gps_altitude_m = gps.altitude_m if gps else None
    row.description = annotation.description
    row.tags = list(annotation.tags)
    row.scene = annotation.scene.value
    row.contains_people = annotation.contains_people
    row.annotated_by = record.annotated_by
    row.processed_at = record.processed_at
    return row


def to_record(row: PhotoRow) -> PhotoRecord:
    """Build a :class:`PhotoRecord` from a database row."""
    return PhotoRecord(
        path=Path(row.path),
        sha256=row.sha256,
        dhash=row.dhash,
        preview_path=Path(row.preview_path),
        exif=_to_exif(row),
        annotation=Annotation(
            description=row.description,
            tags=list(row.tags),
            scene=row.scene,
            contains_people=row.contains_people,
        ),
        annotated_by=row.annotated_by,
        processed_at=row.processed_at,
    )


def _to_exif(row: PhotoRow) -> ExifData:
    return ExifData(
        make=row.make,
        model=row.model,
        lens_model=row.lens_model,
        lens_make=row.lens_make,
        lens_spec=row.lens_spec,
        iso=row.iso,
        exposure_time_s=row.exposure_time_s,
        f_number=row.f_number,
        focal_length_mm=row.focal_length_mm,
        captured_at=row.captured_at,
        date_source=DateSource(row.date_source) if row.date_source else None,
        width_px=row.width_px,
        height_px=row.height_px,
        gps=_to_gps(row),
    )


def _to_gps(row: PhotoRow) -> GpsCoordinate | None:
    if row.gps_latitude is None or row.gps_longitude is None:
        return None
    return GpsCoordinate(
        latitude=row.gps_latitude,
        longitude=row.gps_longitude,
        altitude_m=row.gps_altitude_m,
    )
