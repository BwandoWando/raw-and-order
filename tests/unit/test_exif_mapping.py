from datetime import datetime
from pathlib import Path

import pytest

from raw_and_order.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    build_date_sources,
)
from raw_and_order.media.exif_mapping import (
    REQUESTED_TAGS,
    ExifMapper,
    first_meaningful_text,
    map_gps,
)
from raw_and_order.schemas import DateSource

NOW = datetime(2026, 11, 20, 12, 0)


@pytest.fixture
def mapper() -> ExifMapper:
    resolver = CaptureDateResolver(
        build_date_sources(list(DateSource)[:-1]), DateValidator(clock=lambda: NOW)
    )
    return ExifMapper(resolver)


def test_maps_camera_settings_and_lens(mapper: ExifMapper) -> None:
    tags = {
        "EXIF:Make": "Canon",
        "EXIF:Model": "EOS R5",
        "Composite:LensID": "RF24-70mm F2.8 L IS USM",
        "EXIF:LensMake": "Canon",
        "EXIF:LensInfo": "24-70mm f/2.8",
        "EXIF:ISO": 400,
        "EXIF:ExposureTime": 0.008,
        "EXIF:FNumber": 2.8,
        "EXIF:FocalLength": 50.0,
        "EXIF:DateTimeOriginal": "2024:06:01 10:15:30",
        "File:ImageWidth": 8192,
        "File:ImageHeight": 5464,
    }

    exif = mapper.map(tags, Path("IMG_1.CR3"))

    assert (exif.make, exif.model, exif.iso, exif.f_number) == (
        "Canon",
        "EOS R5",
        400,
        2.8,
    )
    assert exif.lens_model == "RF24-70mm F2.8 L IS USM"
    assert (exif.lens_make, exif.lens_spec) == ("Canon", "24-70mm f/2.8")
    assert exif.captured_at == datetime(2024, 6, 1, 10, 15, 30)
    assert exif.date_source is DateSource.EXIF_ORIGINAL
    assert exif.gps is None


def test_no_date_anywhere_reports_none_source(mapper: ExifMapper) -> None:
    exif = mapper.map({}, Path("IMG_1234.jpg"))

    assert exif.captured_at is None
    assert exif.date_source is DateSource.NOT_FOUND


def test_falls_back_to_secondary_keys(mapper: ExifMapper) -> None:
    exif = mapper.map(
        {"MakerNotes:Make": "Sony", "Composite:ISO": "100"}, Path("a.arw")
    )

    assert (exif.make, exif.iso) == ("Sony", 100)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (
            {"Composite:LensID": "61", "EXIF:LensModel": "EF50mm f/1.8 STM"},
            "EF50mm f/1.8 STM",
        ),
        (
            {"Composite:LensID": "Unknown (61)", "MakerNotes:Lens": "Real Lens"},
            "Real Lens",
        ),
        ({"EXIF:LensModel": "----", "XMP:Lens": "From Lightroom"}, "From Lightroom"),
        ({"EXIF:LensModel": "  ", "XMP:LensModel": "N/A"}, None),
        (
            {"Composite:LensID": "Canon EF 50mm f/1.8 II or Sigma 50mm"},
            "Canon EF 50mm f/1.8 II or Sigma 50mm",
        ),
        ({}, None),
    ],
)
def test_lens_chain_skips_codes_and_placeholders(
    mapper: ExifMapper, tags: dict[str, str], expected: str | None
) -> None:
    assert mapper.map(tags, Path("a.nef")).lens_model == expected


def test_first_meaningful_text_keeps_order() -> None:
    tags = {"A": "first", "B": "second"}

    assert first_meaningful_text(tags, ("B", "A")) == "second"


def test_requested_tags_mark_numeric_fields_only() -> None:
    assert "EXIF:ISO#" in REQUESTED_TAGS
    assert "Composite:LensID" in REQUESTED_TAGS  # readable name, no '#'
    assert "Composite:LensID#" not in REQUESTED_TAGS


def test_map_gps_returns_signed_coordinates() -> None:
    gps = map_gps(
        {
            "Composite:GPSLatitude": -33.86,
            "Composite:GPSLongitude": 151.21,
            "EXIF:GPSAltitude": 12.5,
        }
    )

    assert gps is not None
    assert (gps.latitude, gps.longitude, gps.altitude_m) == (-33.86, 151.21, 12.5)


def test_map_gps_ignores_out_of_range_values() -> None:
    assert map_gps({"Composite:GPSLatitude": 200, "Composite:GPSLongitude": 0}) is None
