"""White balance: the mode and the colour temperature in kelvin.

Cameras rarely store the kelvin value of an Auto white balance shot. Many
(e.g. Sony) do store the red/blue correction they applied (``WB_RGGBLevels``)
plus calibration levels for known temperatures (``WB_RGBLevels3200K`` ...).
Pentax-style maker notes (e.g. Ricoh GR) store calibration as
``KelvinWB_NN = "K 0 R B"`` multipliers, and DNG files store the as-shot
white balance as ``AsShotNeutral`` (the inverse of the multipliers).

Every value is reduced to one number, the red/blue multiplier ratio. Warm
light needs little red gain and much blue gain, so the ratio rises with
colour temperature. The as-shot ratio is placed between the two calibration
points whose ratios bracket it, and the kelvin is interpolated linearly in
mireds (1e6 / K, the scale colour temperature is normally interpolated on)
against log(ratio). Ratios outside the calibrated range give no estimate.
"""

import itertools
import math
import re
from dataclasses import dataclass
from typing import Any

from raw_and_order.media.exif_values import ExifTags, as_float, as_text, first_value
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
# Exiftool tag patterns to request (numeric values, so "#"); no group prefix,
# so they match maker notes and EXIF alike. "*" is exiftool's wildcard.
LEVEL_TAG_PATTERNS = (
    "WB_RGGBLevelsAsShot#",
    "WB_RGGBLevels#",
    "WB_RGBLevels#",
    "WB_RGB*Levels*K#",
    "KelvinWB_*#",
    "AsShotNeutral#",
)

# Calibration tags: WB_RGBLevels3200K-style (kelvin in the name) and Pentax
# KelvinWB_01..NN / KelvinWB_Daylight (kelvin in the value).
CALIBRATION_KEY = re.compile(r":WB_RGG?BLevels(\d{4,5})K$")
KELVIN_WB_KEY = re.compile(r":KelvinWB_(?:\d+|Daylight)$")
KELVIN_WB_FIELDS = 4  # kelvin, unused, red multiplier, blue multiplier
PLAUSIBLE_KELVIN = (1500, 15000)  # recorded kelvin outside this is ignored
ROUND_TO_K = 50
MIN_CALIBRATION_POINTS = 2
RGB_CHANNELS = 3
RGGB_CHANNELS = 4


@dataclass(frozen=True)
class WhiteBalance:
    """Resolved white balance mode and temperature.

    ``mode`` is the camera's text (e.g. "Auto", "Daylight"), read independently
    of the kelvin. ``kelvin`` is rounded to 50 K; ``source`` says where it came
    from and is ``None`` exactly when ``kelvin`` is.
    """

    mode: str | None
    kelvin: int | None
    source: WhiteBalanceSource | None


def resolve_white_balance(tags: ExifTags) -> WhiteBalance:
    """Return the white balance from exiftool tags.

    Tries, in order, and stops at the first that gives a kelvin: the camera's
    recorded kelvin (within :data:`PLAUSIBLE_KELVIN`), an estimate from the
    camera's WB levels and calibration (:func:`estimate_kelvin_from_tags`),
    then an editor's (XMP) value. Camera data comes first because it describes
    the shot as taken; an edit's temperature is only a last resort.
    """
    mode = as_text(first_value(tags, MODE_KEYS))
    if (kelvin := _first_kelvin(tags, CAMERA_KELVIN_KEYS)) is not None:
        return _found(mode, kelvin, WhiteBalanceSource.CAMERA)
    if (kelvin := estimate_kelvin_from_tags(tags)) is not None:
        return _found(mode, kelvin, WhiteBalanceSource.ESTIMATED)
    if (kelvin := _first_kelvin(tags, EDITED_KELVIN_KEYS)) is not None:
        return _found(mode, kelvin, WhiteBalanceSource.EDITED)
    return WhiteBalance(mode=mode, kelvin=None, source=None)


def _found(mode: str | None, kelvin: float, source: WhiteBalanceSource) -> WhiteBalance:
    """A white balance with its kelvin rounded to a believable precision."""
    return WhiteBalance(mode=mode, kelvin=round_kelvin(kelvin), source=source)


def estimate_kelvin_from_tags(tags: ExifTags) -> float | None:
    """Estimate the as-shot kelvin from WB levels and calibration points.

    Returns ``None`` if the shot's levels are missing, there are fewer than
    :data:`MIN_CALIBRATION_POINTS` calibration points, or the shot's ratio
    falls outside them.
    """
    as_shot = _as_shot_ratio(tags)
    if as_shot is None:
        return None
    return estimate_kelvin(as_shot, calibration_points(tags))


def _as_shot_ratio(tags: ExifTags) -> float | None:
    """The red/blue ratio the camera applied to this shot, or ``None``.

    Read from the first recorded tag in :data:`AS_SHOT_LEVEL_KEYS`, else
    from the DNG ``AsShotNeutral``.
    """
    for key in AS_SHOT_LEVEL_KEYS:
        ratio = red_blue_ratio(tags.get(key))
        if ratio:  # None or 0: not recorded
            return ratio
    return neutral_red_blue_ratio(tags.get(AS_SHOT_NEUTRAL_KEY))


def calibration_points(tags: ExifTags) -> list[tuple[int, float]]:
    """Return ``(kelvin, red/blue ratio)`` calibration points, sorted by kelvin.

    Scans every tag, since calibration tag names vary by camera. Unparseable
    values are skipped; if two tags give the same kelvin, the later one wins.
    """
    points: dict[int, float] = {}
    for key, value in tags.items():
        match = CALIBRATION_KEY.search(key)
        if match and (ratio := red_blue_ratio(value)):
            points[int(match.group(1))] = ratio
        elif KELVIN_WB_KEY.search(key) and (point := kelvin_wb_point(value)):
            points[point[0]] = point[1]
    return sorted(points.items())


def kelvin_wb_point(value: Any) -> tuple[int, float] | None:
    """Parse a Pentax/Ricoh ``"K 0 R B"`` value into ``(kelvin, red / blue)``.

    ``None`` if it does not have four numbers or any of them is not positive.
    """
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

    The red/blue ratio rises with colour temperature. ``points`` must be
    sorted by kelvin; each neighbouring pair is checked in turn and the first
    whose ratios bracket ``ratio`` is used. Interpolation is linear in mireds
    against log(ratio). Ratios outside the calibrated range return ``None``
    rather than a guess.
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
    """Return red/blue from ``"R G B"`` or ``"R G G B"`` levels.

    ``None`` for any other number of values or a non-positive red or blue.
    """
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
    """Floats from a space-separated string or a list; ``None`` if not numeric.

    Exiftool returns multi-value tags as ``"R G G B"`` text or as a list.
    """
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


def _first_kelvin(tags: ExifTags, keys: tuple[str, ...]) -> float | None:
    """The first plausible kelvin value among ``keys`` (0 means "not recorded")."""
    low, high = PLAUSIBLE_KELVIN
    for key in keys:
        kelvin = as_float(tags.get(key))
        if kelvin is not None and low <= kelvin <= high:
            return kelvin
    return None
