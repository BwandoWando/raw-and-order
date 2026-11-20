"""White balance: the mode and the colour temperature in kelvin.

Cameras rarely store the kelvin value of an Auto white balance shot. Many
(e.g. Sony) do store the red/blue correction they applied (``WB_RGGBLevels``)
plus calibration levels for known temperatures (``WB_RGBLevels3200K`` ...).
The as-shot temperature is estimated by interpolating the red/blue ratio
between those calibration points, in mireds (1e6 / K), the scale colour
temperature is normally interpolated on.
"""

import itertools
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from my_agent.schemas.exif import WhiteBalanceSource

MODE_KEYS = ("MakerNotes:WhiteBalance", "EXIF:WhiteBalance", "XMP:WhiteBalance")
CAMERA_KELVIN_KEYS = ("MakerNotes:ColorTempAsShot", "MakerNotes:ColorTemperature")
# Lightroom/ACR absolute temperature (XMP-crs). JPEG edits use the relative
# IncrementalTemperature instead, which is deliberately not read.
EDITED_KELVIN_KEYS = ("XMP:ColorTemperature",)
AS_SHOT_LEVEL_KEYS = (
    "MakerNotes:WB_RGGBLevelsAsShot",
    "MakerNotes:WB_RGGBLevels",
    "EXIF:WB_RGGBLevels",
    "MakerNotes:WB_RGBLevels",
)
# Exiftool tag patterns to request (numeric values, so "#").
LEVEL_TAG_PATTERNS = (
    "WB_RGGBLevelsAsShot#",
    "WB_RGGBLevels#",
    "WB_RGBLevels#",
    "WB_RGB*Levels*K#",
)

CALIBRATION_KEY = re.compile(r":WB_RGG?BLevels(\d{4,5})K$")
PLAUSIBLE_KELVIN = (1500, 15000)
ROUND_TO_K = 50
MIN_CALIBRATION_POINTS = 2
RGB_CHANNELS = 3
RGGB_CHANNELS = 4


@dataclass(frozen=True)
class WhiteBalance:
    """Resolved white balance mode and temperature."""

    mode: str | None
    kelvin: int | None
    source: WhiteBalanceSource | None


def resolve_white_balance(tags: Mapping[str, Any]) -> WhiteBalance:
    """Return the white balance from exiftool tags.

    Tries, in order: the camera's recorded kelvin, an estimate from the
    camera's WB calibration, then an editor's (XMP) value.
    """
    mode = _first_text(tags, MODE_KEYS)
    for kelvin, source in (
        (_first_kelvin(tags, CAMERA_KELVIN_KEYS), WhiteBalanceSource.CAMERA),
        (estimate_from_tags(tags), WhiteBalanceSource.ESTIMATED),
        (_first_kelvin(tags, EDITED_KELVIN_KEYS), WhiteBalanceSource.EDITED),
    ):
        if kelvin is not None:
            return WhiteBalance(mode=mode, kelvin=round_kelvin(kelvin), source=source)
    return WhiteBalance(mode=mode, kelvin=None, source=None)


def estimate_from_tags(tags: Mapping[str, Any]) -> float | None:
    """Estimate the as-shot kelvin from WB levels, or ``None`` if impossible."""
    as_shot = next(
        (r for key in AS_SHOT_LEVEL_KEYS if (r := red_blue_ratio(tags.get(key)))),
        None,
    )
    if as_shot is None:
        return None
    return estimate_kelvin(as_shot, calibration_points(tags))


def calibration_points(tags: Mapping[str, Any]) -> list[tuple[int, float]]:
    """Return ``(kelvin, red/blue ratio)`` calibration points, sorted by kelvin."""
    points: dict[int, float] = {}
    for key, value in tags.items():
        match = CALIBRATION_KEY.search(key)
        ratio = red_blue_ratio(value) if match else None
        if match and ratio:
            points[int(match.group(1))] = ratio
    return sorted(points.items())


def estimate_kelvin(ratio: float, points: list[tuple[int, float]]) -> float | None:
    """Interpolate the kelvin whose calibration red/blue ratio matches ``ratio``.

    The red/blue ratio rises with colour temperature. Interpolation is linear
    in mireds against log(ratio). Ratios outside the calibrated range return
    ``None`` rather than a guess.
    """
    if len(points) < MIN_CALIBRATION_POINTS or ratio <= 0:
        return None
    target = math.log(ratio)
    for (k_low, r_low), (k_high, r_high) in itertools.pairwise(points):
        low, high = math.log(r_low), math.log(r_high)
        if min(low, high) <= target <= max(low, high) and low != high:
            share = (target - low) / (high - low)
            mired = 1e6 / k_low + share * (1e6 / k_high - 1e6 / k_low)
            return 1e6 / mired
    return None


def red_blue_ratio(value: Any) -> float | None:
    """Return red/blue from ``"R G B"`` or ``"R G G B"`` levels."""
    if not isinstance(value, str | list | tuple):
        return None
    parts = value.split() if isinstance(value, str) else list(value)
    try:
        numbers = [float(part) for part in parts]
    except (TypeError, ValueError):
        return None
    if len(numbers) == RGB_CHANNELS:
        red, blue = numbers[0], numbers[2]
    elif len(numbers) == RGGB_CHANNELS:
        red, blue = numbers[0], numbers[3]
    else:
        return None
    return red / blue if red > 0 and blue > 0 else None


def round_kelvin(kelvin: float) -> int:
    """Round to the nearest 50 K; finer precision would be false accuracy."""
    return int(round(kelvin / ROUND_TO_K) * ROUND_TO_K)


def _first_kelvin(tags: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    low, high = PLAUSIBLE_KELVIN
    for key in keys:
        try:
            value = float(tags[key])
        except (KeyError, TypeError, ValueError):
            continue
        if low <= value <= high:  # 0 means "not recorded"
            return value
    return None


def _first_text(tags: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None
