"""Which photos the details dialog can step to."""

from pathlib import Path

from raw_and_order.ui.detail import (
    LANDSCAPE_SHARE,
    PORTRAIT_SHARE,
    column_share,
    neighbours,
)

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


def test_portrait_photos_leave_more_width_to_the_text() -> None:
    assert column_share((400, 600)) == PORTRAIT_SHARE
    assert PORTRAIT_SHARE[1] > PORTRAIT_SHARE[0]


def test_landscape_square_and_unknown_photos_keep_the_wide_photo_column() -> None:
    assert column_share((600, 400)) == LANDSCAPE_SHARE
    assert column_share((500, 500)) == LANDSCAPE_SHARE
    assert column_share(None) == LANDSCAPE_SHARE
