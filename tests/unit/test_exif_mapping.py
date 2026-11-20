from datetime import datetime

from my_agent.media.exif_mapping import map_exif, map_gps, parse_exif_datetime


def test_map_exif_reads_grouped_numeric_tags() -> None:
    tags = {
        "EXIF:Make": "Canon",
        "EXIF:Model": "EOS R5",
        "Composite:LensID": "RF24-70mm F2.8 L IS USM",
        "EXIF:ISO": 400,
        "EXIF:ExposureTime": 0.008,
        "EXIF:FNumber": 2.8,
        "EXIF:FocalLength": 50.0,
        "EXIF:DateTimeOriginal": "2024:06:01 10:15:30",
        "File:ImageWidth": 8192,
        "File:ImageHeight": 5464,
    }

    exif = map_exif(tags)

    assert exif.make == "Canon"
    assert exif.lens_model == "RF24-70mm F2.8 L IS USM"
    assert exif.iso == 400
    assert exif.f_number == 2.8
    assert exif.captured_at == datetime(2024, 6, 1, 10, 15, 30)
    assert exif.width_px == 8192
    assert exif.gps is None


def test_captured_at_uses_only_date_time_original() -> None:
    assert map_exif({"EXIF:CreateDate": "2024:06:01 10:15:30"}).captured_at is None


def test_map_exif_falls_back_to_secondary_keys() -> None:
    exif = map_exif({"MakerNotes:Make": "Sony", "Composite:ISO": "100"})

    assert exif.make == "Sony"
    assert exif.iso == 100


def test_map_gps_returns_signed_coordinates() -> None:
    gps = map_gps(
        {
            "Composite:GPSLatitude": -33.86,
            "Composite:GPSLongitude": 151.21,
            "Composite:GPSAltitude": 12.5,
        }
    )

    assert gps is not None
    assert (gps.latitude, gps.longitude, gps.altitude_m) == (-33.86, 151.21, 12.5)


def test_map_gps_ignores_out_of_range_values() -> None:
    assert map_gps({"Composite:GPSLatitude": 200, "Composite:GPSLongitude": 0}) is None


def test_parse_exif_datetime_handles_junk() -> None:
    assert parse_exif_datetime("0000:00:00 00:00:00") is None
    assert parse_exif_datetime(None) is None
    assert parse_exif_datetime("2024:01:02 03:04:05+02:00") == datetime(
        2024, 1, 2, 3, 4, 5
    )
