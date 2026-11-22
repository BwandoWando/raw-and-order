from datetime import datetime, timedelta
from pathlib import Path

import pytest

from raw_and_order.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    ExifTagDate,
    FilenameDate,
    build_date_sources,
    parse_exif_datetime,
)
from raw_and_order.schemas import DateSource

NOW = datetime(2026, 11, 20, 12, 0)
ALL_SOURCES = [
    DateSource.EXIF_ORIGINAL,
    DateSource.XMP,
    DateSource.EXIF_CREATE,
    DateSource.FILENAME,
]


def _resolver(order: list[DateSource] = ALL_SOURCES) -> CaptureDateResolver:
    return CaptureDateResolver(build_date_sources(order), DateValidator(lambda: NOW))


# --- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024:01:02 03:04:05", datetime(2024, 1, 2, 3, 4, 5)),
        ("2024:01:02 03:04:05+02:00", datetime(2024, 1, 2, 3, 4, 5)),  # tz kept local
        ("2024:01:02 03:04:05.123", datetime(2024, 1, 2, 3, 4, 5)),
        ("2024:01:02", datetime(2024, 1, 2)),
        ("0000:00:00 00:00:00", None),
        ("2024:02:30 10:00:00", None),  # invalid day
        ("garbage", None),
        (None, None),
        (12345, None),
    ],
)
def test_parse_exif_datetime(value: object, expected: datetime | None) -> None:
    assert parse_exif_datetime(value) == expected


# --- file names --------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("IMG_20240501_183000.jpg", datetime(2024, 5, 1, 18, 30)),
        ("PXL_20240501_183000123.jpg", datetime(2024, 5, 1, 18, 30)),
        ("IMG-20240501-WA0001.jpg", datetime(2024, 5, 1)),
        ("Screenshot 2024-05-01 at 18.30.00.png", datetime(2024, 5, 1, 18, 30)),
        ("Screenshot_20240501.png", datetime(2024, 5, 1)),
        ("holiday 2024-05-01.heic", datetime(2024, 5, 1)),
    ],
)
def test_filename_patterns(name: str, expected: datetime) -> None:
    assert next(FilenameDate().candidates({}, Path(name))) == expected


@pytest.mark.parametrize(
    "name", ["IMG_1234.jpg", "DSC_0042.NEF", "photo.png", "20241399.jpg"]
)
def test_filename_without_date_yields_nothing(name: str) -> None:
    assert list(FilenameDate().candidates({}, Path(name))) == []


# --- validation --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "plausible"),
    [
        (datetime(2024, 5, 1, 18, 30), True),
        (datetime(1970, 1, 1), False),
        (datetime(1989, 12, 31), False),
        (datetime(1990, 1, 1), True),
        (datetime(2000, 1, 1, 14, 0), False),  # camera reset date
        (datetime(2001, 1, 1), False),
        (datetime(2010, 1, 1, 9, 0), False),
        (NOW + timedelta(hours=23), True),  # within tolerance
        (NOW + timedelta(days=2), False),  # future
    ],
)
def test_validator(value: datetime, plausible: bool) -> None:
    assert DateValidator(lambda: NOW).is_plausible(value) is plausible


# --- resolver ----------------------------------------------------------------


def test_prefers_date_time_original() -> None:
    tags = {
        "EXIF:DateTimeOriginal": "2024:05:01 18:30:00",
        "XMP:DateCreated": "2024:04:30 10:00:00",
        "EXIF:CreateDate": "2024:05:02 09:00:00",
    }

    capture = _resolver().resolve(tags, Path("IMG_20230101_000000.jpg"))

    assert capture is not None
    assert (capture.value, capture.source) == (
        datetime(2024, 5, 1, 18, 30),
        DateSource.EXIF_ORIGINAL,
    )


@pytest.mark.parametrize(
    ("tags", "name", "source"),
    [
        ({"XMP:DateCreated": "2024:04:30 10:00:00"}, "a.jpg", DateSource.XMP),
        ({"XMP:DateTimeOriginal": "2024:04:30 10:00:00"}, "a.jpg", DateSource.XMP),
        ({"EXIF:CreateDate": "2024:05:02 09:00:00"}, "a.jpg", DateSource.EXIF_CREATE),
        ({}, "IMG_20240501_183000.jpg", DateSource.FILENAME),
    ],
)
def test_falls_back_in_order(
    tags: dict[str, str], name: str, source: DateSource
) -> None:
    capture = _resolver().resolve(tags, Path(name))

    assert capture is not None
    assert capture.source is source


def test_implausible_date_falls_through_to_next_source() -> None:
    tags = {
        "EXIF:DateTimeOriginal": "2000:01:01 00:05:00",  # camera reset
        "EXIF:CreateDate": "2024:05:02 09:00:00",
    }

    capture = _resolver().resolve(tags, Path("a.jpg"))

    assert capture is not None
    assert capture.source is DateSource.EXIF_CREATE


def test_returns_none_when_nothing_is_plausible() -> None:
    tags = {"EXIF:DateTimeOriginal": "1970:01:01 00:00:00"}

    assert _resolver().resolve(tags, Path("IMG_1234.jpg")) is None


def test_configured_order_is_respected() -> None:
    tags = {"EXIF:DateTimeOriginal": "2024:05:01 18:30:00"}

    capture = _resolver([DateSource.FILENAME, DateSource.EXIF_ORIGINAL]).resolve(
        tags, Path("IMG_20230101_120000.jpg")
    )

    assert capture is not None
    assert capture.source is DateSource.FILENAME


def test_trimmed_order_skips_removed_sources() -> None:
    capture = _resolver([DateSource.EXIF_ORIGINAL]).resolve(
        {"EXIF:CreateDate": "2024:05:02 09:00:00"}, Path("IMG_20240501_183000.jpg")
    )

    assert capture is None


def test_exif_tag_date_tries_keys_in_order() -> None:
    source = ExifTagDate(DateSource.XMP, ("XMP:DateCreated", "XMP:DateTimeOriginal"))
    tags = {"XMP:DateCreated": "junk", "XMP:DateTimeOriginal": "2024:04:30 10:00:00"}

    assert list(source.candidates(tags, Path("a.jpg"))) == [datetime(2024, 4, 30, 10)]


def test_none_is_not_a_configurable_source() -> None:
    with pytest.raises(ValueError, match="not a date source"):
        build_date_sources([DateSource.NOT_FOUND])
