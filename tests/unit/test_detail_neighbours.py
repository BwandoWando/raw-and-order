"""Which photos the details dialog can step to."""

from pathlib import Path

from raw_and_order.ui.detail import (
    LANDSCAPE_SHARE,
    PORTRAIT_SHARE,
    GalleryPage,
    PageTurn,
    column_share,
    neighbours,
    page_position,
    steps,
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


def test_page_position_counts_from_one() -> None:
    assert page_position(PATHS, Path("/a.jpg")) == 1
    assert page_position(PATHS, Path("/c.jpg")) == 3


def test_a_photo_off_the_page_has_no_position() -> None:
    assert page_position(PATHS, Path("/elsewhere.jpg")) is None


def test_steps_stay_on_the_page_away_from_its_ends() -> None:
    page = GalleryPage(tuple(PATHS), has_previous=True, has_next=True)

    assert steps(page, PATHS[1]) == (PATHS[0], PATHS[2])


def test_steps_past_the_page_ends_turn_the_page() -> None:
    page = GalleryPage(tuple(PATHS), has_previous=True, has_next=True)

    assert steps(page, PATHS[0]) == (PageTurn.PREVIOUS, PATHS[1])
    assert steps(page, PATHS[2]) == (PATHS[1], PageTurn.NEXT)


def test_no_step_past_the_first_or_last_photo_of_all() -> None:
    page = GalleryPage(tuple(PATHS))

    assert steps(page, PATHS[0]) == (None, PATHS[1])
    assert steps(page, PATHS[2]) == (PATHS[1], None)


def test_a_photo_off_the_page_never_turns_it() -> None:
    page = GalleryPage(tuple(PATHS), has_previous=True, has_next=True)

    assert steps(page, Path("/elsewhere.jpg")) == (None, None)
