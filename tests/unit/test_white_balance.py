import pytest

from my_agent.media.white_balance import (
    calibration_points,
    estimate_kelvin,
    red_blue_ratio,
    resolve_white_balance,
    round_kelvin,
)
from my_agent.schemas import WhiteBalanceSource

# Calibration levels as written by a Sony ILCE-6400 (from a real ARW file).
SONY_CALIBRATION = {
    "MakerNotes:WB_RGBLevels2500K": "1528 1024 4184",
    "MakerNotes:WB_RGBLevels3200K": "1948 1024 2976",
    "MakerNotes:WB_RGBLevels4500K": "2524 1024 2132",
    "MakerNotes:WB_RGBLevels6000K": "2972 1024 1744",
    "MakerNotes:WB_RGBLevels8500K": "3444 1024 1468",
}


def _sony(as_shot: str, **extra: object) -> dict[str, object]:
    return {
        "MakerNotes:WhiteBalance": "Auto",
        "MakerNotes:ColorTemperature": 0,  # Sony leaves this 0 in Auto WB
        "MakerNotes:WB_RGGBLevels": as_shot,
        **SONY_CALIBRATION,
        **extra,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2964 1024 1024 1972", 2964 / 1972),
        ("744 256 488", 744 / 488),
        ([2964, 1024, 1024, 1972], 2964 / 1972),
        ("1 2", None),
        ("0 1 1 0", None),
        ("a b c", None),
        (None, None),
    ],
)
def test_red_blue_ratio(value: object, expected: float | None) -> None:
    assert red_blue_ratio(value) == expected


def test_calibration_points_sorted_by_kelvin() -> None:
    points = calibration_points(
        {**SONY_CALIBRATION, "MakerNotes:WB_RGBLevelsDaylight": "1 1 1"}
    )

    assert [k for k, _ in points] == [2500, 3200, 4500, 6000, 8500]


@pytest.mark.parametrize(
    ("as_shot", "expected_k"),
    [
        ("2964 1024 1024 1972", 5400),  # real ARW, Auto WB indoors/overcast
        ("2972 1024 1024 1752", 5950),  # real ARW, Auto WB in sunlight
        ("1948 1024 1024 2976", 3200),  # exactly a calibration point
    ],
)
def test_estimates_auto_white_balance(as_shot: str, expected_k: int) -> None:
    wb = resolve_white_balance(_sony(as_shot))

    assert (wb.mode, wb.kelvin, wb.source) == (
        "Auto",
        expected_k,
        WhiteBalanceSource.ESTIMATED,
    )


def test_estimate_stays_monotonic_between_points() -> None:
    points = calibration_points(SONY_CALIBRATION)
    warm, cool = (estimate_kelvin(r, points) for r in (0.8, 2.0))

    assert warm is not None and cool is not None
    assert 3200 < warm < 4500 < 6000 < cool < 8500


def test_outside_calibrated_range_is_not_guessed() -> None:
    assert (
        resolve_white_balance(_sony("100 1024 1024 4000")).kelvin is None
    )  # candlelight
    assert estimate_kelvin(1.0, [(5000, 1.0)]) is None  # one point is not enough


def test_camera_recorded_kelvin_wins() -> None:
    wb = resolve_white_balance(
        _sony("2964 1024 1024 1972", **{"MakerNotes:ColorTemperature": 3100})
    )

    assert (wb.kelvin, wb.source) == (3100, WhiteBalanceSource.CAMERA)


def test_canon_as_shot_temperature() -> None:
    wb = resolve_white_balance(
        {"EXIF:WhiteBalance": "Auto", "MakerNotes:ColorTempAsShot": 4921}
    )

    assert (wb.kelvin, wb.source) == (4900, WhiteBalanceSource.CAMERA)


def test_editor_value_used_last_and_relative_values_ignored() -> None:
    edited = resolve_white_balance(
        {"XMP:ColorTemperature": 5650, "XMP:WhiteBalance": "Custom"}
    )
    relative = resolve_white_balance(
        {"XMP:IncrementalTemperature": -12}
    )  # JPEG edit: relative slider

    assert (edited.mode, edited.kelvin, edited.source) == (
        "Custom",
        5650,
        WhiteBalanceSource.EDITED,
    )
    assert relative.kelvin is None


def test_nothing_available() -> None:
    assert resolve_white_balance({}) == resolve_white_balance({"EXIF:WhiteBalance": ""})
    assert resolve_white_balance({}).kelvin is None


def test_round_kelvin() -> None:
    assert (round_kelvin(5382.4), round_kelvin(5374.9)) == (5400, 5350)


# Pentax-style calibration and DNG neutral, as written by a Ricoh GR IV.
RICOH_CALIBRATION = {
    "MakerNotes:KelvinWB_Daylight": "5205 0 2.499755859375 1.591796875",
    "MakerNotes:KelvinWB_01": "2500 0 1.3848876953125 2.7548828125",
    "MakerNotes:KelvinWB_10": "4550 0 2.322021484375 1.7281494140625",
    "MakerNotes:KelvinWB_11": "5000 0 2.4498291015625 1.62939453125",
    "MakerNotes:KelvinWB_12": "5560 0 2.5802001953125 1.5321044921875",
    "MakerNotes:KelvinWB_16": "10000 0 3.0869140625 1.20068359375",
}


def test_ricoh_dng_auto_white_balance_is_estimated() -> None:
    tags = {
        "MakerNotes:WhiteBalance": "Auto",
        "EXIF:AsShotNeutral": "0.3920367534 1 0.583143508",
        **RICOH_CALIBRATION,
    }

    wb = resolve_white_balance(tags)

    assert (wb.mode, wb.kelvin, wb.source) == (
        "Auto",
        4950,
        WhiteBalanceSource.ESTIMATED,
    )


def test_kelvin_wb_points_include_daylight_and_are_sorted() -> None:
    points = calibration_points(RICOH_CALIBRATION)

    assert [k for k, _ in points] == [2500, 4550, 5000, 5205, 5560, 10000]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0.5 1 0.25", 0.5), ("0 1 1", None), ("1 1", None), (None, None)],
)
def test_neutral_red_blue_ratio(value: object, expected: float | None) -> None:
    from my_agent.media.white_balance import neutral_red_blue_ratio

    assert neutral_red_blue_ratio(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5000 0 2.0 1.0", (5000, 2.0)),
        ("0 0 1 1", None),
        ("5000 0 2", None),
        ("x", None),
    ],
)
def test_kelvin_wb_point(value: str, expected: tuple[int, float] | None) -> None:
    from my_agent.media.white_balance import kelvin_wb_point

    assert kelvin_wb_point(value) == expected


def test_maker_levels_are_preferred_over_dng_neutral() -> None:
    tags = {
        **_sony("2964 1024 1024 1972"),
        "EXIF:AsShotNeutral": "0.1 1 0.9",  # would give a very different ratio
    }

    assert resolve_white_balance(tags).kelvin == 5400
