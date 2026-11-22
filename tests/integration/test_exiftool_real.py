"""Runs the real exiftool; skipped if it is not installed."""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from raw_and_order.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    build_date_sources,
)
from raw_and_order.media.exif import PyExifToolReader
from raw_and_order.media.exif_mapping import ExifMapper
from raw_and_order.schemas import DateSource, ExifData, WhiteBalanceSource

pytestmark = pytest.mark.skipif(shutil.which("exiftool") is None, reason="no exiftool")

ORDER = [
    DateSource.EXIF_ORIGINAL,
    DateSource.XMP,
    DateSource.EXIF_CREATE,
    DateSource.FILENAME,
]


def _write(path: Path, *args: str) -> Path:
    Image.new("RGB", (60, 40)).save(path)
    if args:
        subprocess.run(
            ["exiftool", "-q", "-overwrite_original", *args, str(path)], check=True
        )
    return path


def _read(path: Path) -> ExifData:
    mapper = ExifMapper(CaptureDateResolver(build_date_sources(ORDER), DateValidator()))
    with PyExifToolReader(mapper) as reader:
        return reader.read(path)


def test_reads_numbers_lens_and_original_date(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "a.jpg",
        "-DateTimeOriginal=2024:05:01 18:30:00",
        "-LensModel=RF24-70mm F2.8 L IS USM",
        "-LensMake=Canon",
        "-LensInfo=24 70 2.8 2.8",
        "-ISO=400",
        "-ExposureTime=1/250",
        "-FNumber=2.8",
        "-GPSLatitude=33.86",
        "-GPSLatitudeRef=S",
        "-GPSLongitude=151.21",
        "-GPSLongitudeRef=E",
    )

    exif = _read(path)

    assert exif.lens_model == "RF24-70mm F2.8 L IS USM"
    assert (exif.lens_make, exif.lens_spec) == ("Canon", "24-70mm f/2.8")
    assert (exif.iso, exif.exposure_time_s, exif.f_number) == (400, 0.004, 2.8)
    assert exif.gps is not None
    assert exif.gps.latitude == -33.86
    assert (exif.captured_at, exif.date_source) == (
        datetime(2024, 5, 1, 18, 30),
        DateSource.EXIF_ORIGINAL,
    )


def test_xmp_date_used_when_exif_date_missing(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "export.jpg", "-XMP-photoshop:DateCreated=2024:04:30 10:00:00"
    )

    exif = _read(path)

    assert (exif.captured_at, exif.date_source) == (
        datetime(2024, 4, 30, 10),
        DateSource.XMP,
    )


def test_filename_date_used_when_no_tags(tmp_path: Path) -> None:
    exif = _read(_write(tmp_path / "IMG_20240501_183000.jpg"))

    assert exif.date_source is DateSource.FILENAME


def test_no_date_at_all(tmp_path: Path) -> None:
    exif = _read(_write(tmp_path / "plain.png"))

    assert (exif.captured_at, exif.date_source, exif.lens_model) == (
        None,
        DateSource.NONE,
        None,
    )


def test_reads_white_balance_mode_and_editor_temperature(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "edited.jpg",
        "-WhiteBalance=Manual",
        "-XMP-crs:ColorTemperature=5650",
    )

    exif = _read(path)

    assert (exif.white_balance, exif.white_balance_k) == ("Manual", 5650)
    assert exif.white_balance_k_source is WhiteBalanceSource.EDITED


def test_capture_times_in_one_batch(tmp_path: Path) -> None:
    shot = _write(tmp_path / "DSC_1.jpg", "-EXIF:DateTimeOriginal=2026:05:01 18:30:00")
    undated = _write(tmp_path / "DSC_2.jpg")
    mapper = ExifMapper(CaptureDateResolver(build_date_sources(ORDER), DateValidator()))

    with PyExifToolReader(mapper) as reader:
        times = reader.capture_times([shot, undated])

    assert times == {shot: datetime(2026, 5, 1, 18, 30, 0), undated: None}
