"""Map exiftool tags to :class:`ExifData`.

Exiftool is called with ``-G`` and an explicit tag list (:data:`REQUESTED_TAGS`).
Numeric fields are requested with a ``#`` suffix so they come back as numbers;
text fields such as the lens name come back human-readable. Output keys never
include the ``#``.
"""

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from raw_and_order.media.capture_date import (
    CREATE_DATE_KEYS,
    DATE_TIME_ORIGINAL_KEYS,
    XMP_DATE_KEYS,
    CaptureDateResolver,
)
from raw_and_order.media.white_balance import (
    CAMERA_KELVIN_KEYS,
    EDITED_KELVIN_KEYS,
    LEVEL_TAG_PATTERNS,
    MODE_KEYS,
    resolve_white_balance,
)
from raw_and_order.schemas.exif import DateSource, ExifData, GpsCoordinate

# Text fields (human-readable values)
MAKE_KEYS = ("EXIF:Make", "MakerNotes:Make")
MODEL_KEYS = ("EXIF:Model", "MakerNotes:Model")
LENS_MODEL_KEYS = (
    "Composite:LensID",  # best: exiftool's lens database lookup
    "EXIF:LensModel",
    "MakerNotes:LensModel",
    "MakerNotes:Lens",
    "XMP:Lens",  # Lightroom exports (XMP-aux)
    "XMP:LensModel",  # XMP-exifEX
)
LENS_MAKE_KEYS = ("EXIF:LensMake", "XMP:LensMake")
LENS_SPEC_KEYS = ("Composite:LensSpec", "EXIF:LensInfo", "XMP:LensInfo")

# Numeric fields (requested with "#")
ISO_KEYS = ("EXIF:ISO", "Composite:ISO", "MakerNotes:ISO")
EXPOSURE_KEYS = ("EXIF:ExposureTime", "Composite:ShutterSpeed")
F_NUMBER_KEYS = ("EXIF:FNumber", "Composite:Aperture")
FOCAL_KEYS = ("EXIF:FocalLength",)
WIDTH_KEYS = ("File:ImageWidth", "EXIF:ExifImageWidth", "EXIF:ImageWidth")
HEIGHT_KEYS = ("File:ImageHeight", "EXIF:ExifImageHeight", "EXIF:ImageHeight")
LAT_KEYS = ("Composite:GPSLatitude",)
LON_KEYS = ("Composite:GPSLongitude",)
ALT_KEYS = ("Composite:GPSAltitude", "EXIF:GPSAltitude")

_TEXT_KEYS = (
    *MAKE_KEYS,
    *MODEL_KEYS,
    *LENS_MODEL_KEYS,
    *LENS_MAKE_KEYS,
    *LENS_SPEC_KEYS,
    *DATE_TIME_ORIGINAL_KEYS,
    *XMP_DATE_KEYS,
    *CREATE_DATE_KEYS,
    *MODE_KEYS,
)
_NUMERIC_KEYS = (
    *ISO_KEYS,
    *EXPOSURE_KEYS,
    *F_NUMBER_KEYS,
    *FOCAL_KEYS,
    *WIDTH_KEYS,
    *HEIGHT_KEYS,
    *LAT_KEYS,
    *LON_KEYS,
    *ALT_KEYS,
    *CAMERA_KELVIN_KEYS,
    *EDITED_KELVIN_KEYS,
)
REQUESTED_TAGS: tuple[str, ...] = (
    *_TEXT_KEYS,
    *(f"{k}#" for k in _NUMERIC_KEYS),
    *LEVEL_TAG_PATTERNS,  # white balance levels and calibration (wildcards)
)

_JUNK_TEXT = re.compile(r"^(?:[-\s]*|n/?a|none|unknown.*|\d+(?:\.\d+)?)$", re.I)


class ExifMapper:
    """Builds :class:`ExifData` from exiftool tags.

    Args:
        date_resolver: Picks the capture date from tags and the file name.
    """

    def __init__(self, date_resolver: CaptureDateResolver) -> None:
        self._date_resolver = date_resolver

    def map(self, tags: Mapping[str, Any], path: Path) -> ExifData:
        """Return the metadata of ``path`` from its exiftool ``tags``."""
        capture = self._date_resolver.resolve(tags, path)
        white_balance = resolve_white_balance(tags)
        return ExifData(
            make=_as_text(_first(tags, MAKE_KEYS)),
            model=_as_text(_first(tags, MODEL_KEYS)),
            lens_model=first_meaningful_text(tags, LENS_MODEL_KEYS),
            lens_make=first_meaningful_text(tags, LENS_MAKE_KEYS),
            lens_spec=first_meaningful_text(tags, LENS_SPEC_KEYS),
            iso=_as_int(_first(tags, ISO_KEYS)),
            exposure_time_s=_as_float(_first(tags, EXPOSURE_KEYS)),
            f_number=_as_float(_first(tags, F_NUMBER_KEYS)),
            focal_length_mm=_as_float(_first(tags, FOCAL_KEYS)),
            captured_at=capture.value if capture else None,
            date_source=capture.source if capture else DateSource.NONE,
            white_balance=white_balance.mode,
            white_balance_k=white_balance.kelvin,
            white_balance_k_source=white_balance.source,
            width_px=_as_int(_first(tags, WIDTH_KEYS)),
            height_px=_as_int(_first(tags, HEIGHT_KEYS)),
            gps=map_gps(tags),
        )


def first_meaningful_text(tags: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first value that is real text, skipping codes and placeholders.

    Skips values such as ``""``, ``"----"``, ``"0"``, ``"61"`` (an unconverted
    lens code) and ``"Unknown (61)"``.
    """
    for key in keys:
        text = _as_text(tags.get(key))
        if text is not None and not _JUNK_TEXT.match(text):
            return text
    return None


def map_gps(tags: Mapping[str, Any]) -> GpsCoordinate | None:
    """Return the GPS position, or ``None`` if absent or out of range."""
    latitude = _as_float(_first(tags, LAT_KEYS))
    longitude = _as_float(_first(tags, LON_KEYS))
    if latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return GpsCoordinate(
        latitude=latitude,
        longitude=longitude,
        altitude_m=_as_float(_first(tags, ALT_KEYS)),
    )


def _first(tags: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    return next((tags[key] for key in keys if tags.get(key) not in (None, "")), None)


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value).strip() or None


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)
