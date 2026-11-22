"""Which photos the details dialog can step to."""

from pathlib import Path

from raw_and_order.schemas.query import PhotoQuery
from raw_and_order.ui.detail import (
    LANDSCAPE_SHARE,
    PORTRAIT_SHARE,
    GalleryPage,
    PageTurn,
    column_share,
    follow,
    neighbours,
    page_of,
    page_position,
    steps,
)
from tests.fakes import FakePhotoLibrary

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


def test_page_of_finds_the_page_a_position_is_on() -> None:
    assert [page_of(n, 24) for n in (1, 24, 25, 48, 49)] == [1, 1, 2, 2, 3]


def _library_of(count: int) -> FakePhotoLibrary:
    from tests.unit.test_ui_renderers import _record

    return FakePhotoLibrary([_record(i) for i in range(count)])


def _first_page(library: FakePhotoLibrary, page_size: int = 24) -> GalleryPage:
    query = PhotoQuery(page_size=page_size)
    return GalleryPage.from_result(library.search(query), query)


def test_follow_a_turn_reads_the_next_page_and_shows_its_first_photo() -> None:
    library = _library_of(30)
    page = _first_page(library)

    turned, path = follow(PageTurn.NEXT, page, library)

    assert turned.number == 2 and len(turned.paths) == 6
    assert turned.has_previous and not turned.has_next
    assert path == turned.paths[0]


def test_follow_back_shows_the_last_photo_of_the_previous_page() -> None:
    library = _library_of(30)
    second, _ = follow(PageTurn.NEXT, _first_page(library), library)

    back, path = follow(PageTurn.PREVIOUS, second, library)

    assert back.number == 1 and path == back.paths[-1]


def test_follow_a_photo_on_another_page_reads_that_page() -> None:
    library = _library_of(30)
    target = Path("/photos/IMG_27.DNG")

    page, path = follow(target, _first_page(library), library)

    assert page.number == 2 and path == target and target in page.paths


def test_follow_a_photo_on_this_page_or_off_the_filters_keeps_the_page() -> None:
    library = _library_of(30)
    first = _first_page(library)

    assert follow(Path("/photos/IMG_3.DNG"), first, library) == (
        first,
        Path("/photos/IMG_3.DNG"),
    )
    assert follow(Path("/photos/gone.DNG"), first, library) == (
        first,
        Path("/photos/gone.DNG"),
    )
