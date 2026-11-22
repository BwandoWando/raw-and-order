"""White balance: the mode and the colour temperature in kelvin.

Cameras rarely store the kelvin value of an Auto white balance shot. Many
(e.g. Sony) do store the red/blue correction they applied (``WB_RGGBLevels``)
plus calibration levels for known temperatures (``WB_RGBLevels3200K`` ...).
Pentax-style maker notes (e.g. Ricoh GR) store calibration as
``KelvinWB_NN = "K 0 R B"`` multipliers, and DNG files store the as-shot
white balance as ``AsShotNeutral`` (the inverse of the multipliers).
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

from raw_and_order.media.exif_values import as_float, as_text, first_value
from raw_and_order.schemas.exif import WhiteBalanceSource

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
AS_SHOT_NEUTRAL_KEY = "EXIF:AsShotNeutral"  # DNG: neutral = 1 / multiplier
# Exiftool tag patterns to request (numeric values, so "#").
LEVEL_TAG_PATTERNS = (
    "WB_RGGBLevelsAsShot#",
    "WB_RGGBLevels#",
    "WB_RGBLevels#",
    "WB_RGB*Levels*K#",
    "KelvinWB_*#",
    "AsShotNeutral#",
)

CALIBRATION_KEY = re.compile(r":WB_RGG?BLevels(\d{4,5})K$")
KELVIN_WB_KEY = re.compile(r":KelvinWB_(?:\d+|Daylight)$")
KELVIN_WB_FIELDS = 4  # kelvin, unused, red multiplier, blue multiplier
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
    mode = as_text(first_value(tags, MODE_KEYS))
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
    ) or neutral_red_blue_ratio(tags.get(AS_SHOT_NEUTRAL_KEY))
    if as_shot is None:
        return None
    return estimate_kelvin(as_shot, calibration_points(tags))


def calibration_points(tags: Mapping[str, Any]) -> list[tuple[int, float]]:
    """Return ``(kelvin, red/blue ratio)`` calibration points, sorted by kelvin."""
    points: dict[int, float] = {}
    for key, value in tags.items():
        match = CALIBRATION_KEY.search(key)
        if match and (ratio := red_blue_ratio(value)):
            points[int(match.group(1))] = ratio
        elif KELVIN_WB_KEY.search(key) and (point := kelvin_wb_point(value)):
            points[point[0]] = point[1]
    return sorted(points.items())


def kelvin_wb_point(value: Any) -> tuple[int, float] | None:
    """Parse a Pentax/Ricoh ``"K 0 R B"`` calibration value."""
    numbers = _numbers(value)
    if numbers is None or len(numbers) != KELVIN_WB_FIELDS:
        return None
    kelvin, _, red, blue = numbers
    if kelvin <= 0 or red <= 0 or blue <= 0:
        return None
    return int(kelvin), red / blue


def neutral_red_blue_ratio(value: Any) -> float | None:
    """Red/blue multiplier ratio from a DNG ``AsShotNeutral`` (``"R G B"``).

    The neutral is the inverse of the multiplier, so the ratio is blue / red.
    """
    numbers = _numbers(value)
    if numbers is None or len(numbers) != RGB_CHANNELS:
        return None
    red, _, blue = numbers
    return blue / red if red > 0 and blue > 0 else None


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
    numbers = _numbers(value)
    if numbers is None:
        return None
    if len(numbers) == RGB_CHANNELS:
        red, blue = numbers[0], numbers[2]
    elif len(numbers) == RGGB_CHANNELS:
        red, blue = numbers[0], numbers[3]
    else:
        return None
    return red / blue if red > 0 and blue > 0 else None


def _numbers(value: Any) -> list[float] | None:
    if not isinstance(value, str | list | tuple):
        return None
    parts = value.split() if isinstance(value, str) else list(value)
    try:
        return [float(part) for part in parts]
    except (TypeError, ValueError):
        return None


def round_kelvin(kelvin: float) -> int:
    """Round to the nearest 50 K; finer precision would be false accuracy."""
    return int(round(kelvin / ROUND_TO_K) * ROUND_TO_K)


def _first_kelvin(tags: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    """The first plausible kelvin value among ``keys`` (0 means "not recorded")."""
    low, high = PLAUSIBLE_KELVIN
    for key in keys:
        kelvin = as_float(tags.get(key))
        if kelvin is not None and low <= kelvin <= high:
            return kelvin
    return None
