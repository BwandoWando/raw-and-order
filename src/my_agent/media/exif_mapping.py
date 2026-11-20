"""Pure functions that map raw exiftool tags to :class:`ExifData`.

Exiftool is called with ``-G -n``, so keys look like ``"EXIF:Make"`` and
numeric values are returned as numbers rather than formatted strings.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from my_agent.schemas.exif import ExifData, GpsCoordinate

EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

_MAKE = ("EXIF:Make", "MakerNotes:Make")
_MODEL = ("EXIF:Model", "MakerNotes:Model")
_LENS = ("Composite:LensID", "EXIF:LensModel", "MakerNotes:LensModel")
_ISO = ("EXIF:ISO", "Composite:ISO", "MakerNotes:ISO")
_EXPOSURE = ("EXIF:ExposureTime", "Composite:ShutterSpeed")
_F_NUMBER = ("EXIF:FNumber", "Composite:Aperture")
_FOCAL = ("EXIF:FocalLength",)
_CAPTURED = ("EXIF:DateTimeOriginal", "EXIF:CreateDate")
_WIDTH = ("File:ImageWidth", "EXIF:ExifImageWidth", "EXIF:ImageWidth")
_HEIGHT = ("File:ImageHeight", "EXIF:ExifImageHeight", "EXIF:ImageHeight")
_LAT = ("Composite:GPSLatitude",)
_LON = ("Composite:GPSLongitude",)
_ALT = ("Composite:GPSAltitude",)


def map_exif(tags: Mapping[str, Any]) -> ExifData:
    """Build :class:`ExifData` from an exiftool tag dictionary."""
    return ExifData(
        make=_as_str(_first(tags, _MAKE)),
        model=_as_str(_first(tags, _MODEL)),
        lens_model=_as_str(_first(tags, _LENS)),
        iso=_as_int(_first(tags, _ISO)),
        exposure_time_s=_as_float(_first(tags, _EXPOSURE)),
        f_number=_as_float(_first(tags, _F_NUMBER)),
        focal_length_mm=_as_float(_first(tags, _FOCAL)),
        captured_at=parse_exif_datetime(_first(tags, _CAPTURED)),
        width_px=_as_int(_first(tags, _WIDTH)),
        height_px=_as_int(_first(tags, _HEIGHT)),
        gps=map_gps(tags),
    )


def map_gps(tags: Mapping[str, Any]) -> GpsCoordinate | None:
    """Return the GPS position, or ``None`` if absent or out of range."""
    latitude = _as_float(_first(tags, _LAT))
    longitude = _as_float(_first(tags, _LON))
    if latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return GpsCoordinate(
        latitude=latitude,
        longitude=longitude,
        altitude_m=_as_float(_first(tags, _ALT)),
    )


def parse_exif_datetime(value: Any) -> datetime | None:
    """Parse an EXIF ``YYYY:MM:DD HH:MM:SS`` timestamp, ignoring junk values."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip()[:19], EXIF_DATETIME_FORMAT)
    except ValueError:
        return None


def _first(tags: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    return next((tags[key] for key in keys if tags.get(key) not in (None, "")), None)


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value).strip() or None


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)
