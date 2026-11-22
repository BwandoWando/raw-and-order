import pytest

from raw_and_order.media.exif_values import as_float, as_int, as_text, first_value

TAGS = {"EXIF:Make": "", "MakerNotes:Make": "SONY", "EXIF:ISO": "100"}


def test_first_value_skips_missing_and_empty_keys() -> None:
    keys = ("XMP:Make", "EXIF:Make", "MakerNotes:Make")

    assert first_value(TAGS, keys) == "SONY"
    assert first_value(TAGS, ("XMP:Make",)) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(" Auto ", "Auto"), ("   ", None), (None, None), (61, "61")],
)
def test_as_text(value: object, expected: str | None) -> None:
    assert as_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("1.8", 1.8), (100, 100.0), ("n/a", None), (None, None)]
)
def test_as_float(value: object, expected: float | None) -> None:
    assert as_float(value) == expected


def test_as_int_truncates() -> None:
    assert as_int("6400.0") == 6400
    assert as_int("x") is None
