"""Which photos the details dialog can step to."""

from pathlib import Path

from raw_and_order.ui.detail import neighbours

PATHS = [Path("/a.jpg"), Path("/b.jpg"), Path("/c.jpg")]


def test_first_photo_has_only_a_next() -> None:
    assert neighbours(PATHS, PATHS[0]) == (None, PATHS[1])


def test_middle_photo_has_both() -> None:
    assert neighbours(PATHS, PATHS[1]) == (PATHS[0], PATHS[2])


def test_last_photo_has_only_a_previous() -> None:
    assert neighbours(PATHS, PATHS[2]) == (PATHS[1], None)


def test_single_or_unknown_photo_has_none() -> None:
    assert neighbours(PATHS[:1], PATHS[0]) == (None, None)
    assert neighbours(PATHS, Path("/other.jpg")) == (None, None)
