import io
from pathlib import Path

import pytest
from PIL import Image

from raw_and_order.exceptions import PreviewError
from raw_and_order.media.thumbnails import JpegThumbnailer
from raw_and_order.schemas.query import PAGE_SIZES
from raw_and_order.ui.gallery import (
    CURRENT_PAGE_COLOURS,
    open_label,
    page_window,
    pager_css,
    thumbnail_css,
    tile_marks_html,
)
from raw_and_order.ui.grid import THUMBNAIL_SIZES, grid_shape, thumbnail_px


@pytest.mark.parametrize("page_size", PAGE_SIZES)
def test_grid_holds_the_whole_page_and_is_wider_than_tall(page_size: int) -> None:
    columns, rows = grid_shape(page_size)

    assert columns * rows >= page_size
    assert columns * (rows - 1) < page_size  # no empty last row
    assert columns >= rows  # landscape screens


def test_grid_shapes_for_each_page_size() -> None:
    assert [grid_shape(n) for n in PAGE_SIZES] == [
        (7, 4),
        (9, 6),
        (11, 7),
        (13, 8),
    ]


def test_denser_grids_get_smaller_thumbnails() -> None:
    sizes = [thumbnail_px(grid_shape(n)[0]) for n in PAGE_SIZES]

    assert sizes == sorted(sizes, reverse=True)
    assert set(sizes) <= set(THUMBNAIL_SIZES)


def test_css_divides_the_window_height_by_the_rows() -> None:
    css = thumbnail_css(rows=9)

    assert "100vh" in css
    assert "/ 9)" in css
    assert "8 * 0.25rem" in css  # gaps between 9 rows


def test_css_fits_whole_photos_in_square_tiles() -> None:
    css = thumbnail_css(rows=4)

    assert "aspect-ratio: 1 / 1" in css
    assert "object-fit: contain" in css


def test_thumbnail_shrinks_to_the_longest_side(tmp_path: Path) -> None:
    preview = tmp_path / "p.jpg"
    Image.new("RGB", (1024, 683), (200, 100, 50)).save(preview)

    data = JpegThumbnailer().thumbnail(preview, 256)

    with Image.open(io.BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert image.size == (256, 171)


def test_thumbnail_of_a_missing_preview_is_a_preview_error(tmp_path: Path) -> None:
    with pytest.raises(PreviewError):
        JpegThumbnailer().thumbnail(tmp_path / "gone.jpg", 128)


def test_size_is_the_preview_as_shown(tmp_path: Path) -> None:
    preview = tmp_path / "portrait.jpg"
    Image.new("RGB", (300, 450)).save(preview)

    assert JpegThumbnailer().size(preview) == (300, 450)


def test_size_of_a_missing_preview_is_a_preview_error(tmp_path: Path) -> None:
    with pytest.raises(PreviewError):
        JpegThumbnailer().size(tmp_path / "gone.jpg")


def test_a_corrupt_preview_is_a_preview_error(tmp_path: Path) -> None:
    preview = tmp_path / "broken.jpg"
    preview.write_bytes(b"not a jpeg")

    with pytest.raises(PreviewError):
        JpegThumbnailer().thumbnail(preview, 128)
    with pytest.raises(PreviewError):
        JpegThumbnailer().size(preview)


def test_square_crops_the_centre_without_stretching(tmp_path: Path) -> None:
    # Red left and right thirds, blue centre: a centre crop keeps only blue.
    preview = tmp_path / "landscape.jpg"
    image = Image.new("RGB", (900, 600), (220, 0, 0))
    image.paste((0, 0, 220), (150, 0, 750, 600))
    image.save(preview, quality=95)

    data = JpegThumbnailer().square(preview, 160)

    with Image.open(io.BytesIO(data)) as tile:
        assert tile.format == "JPEG"
        assert tile.size == (160, 160)
        red, _, blue = tile.convert("RGB").getpixel((3, 80))
        assert blue > 150 and red < 60  # the red side was cropped away


def test_square_of_a_portrait_keeps_the_middle_rows(tmp_path: Path) -> None:
    preview = tmp_path / "portrait.jpg"
    Image.new("RGB", (400, 600), (10, 160, 10)).save(preview)

    data = JpegThumbnailer().square(preview, 96)

    with Image.open(io.BytesIO(data)) as tile:
        assert tile.size == (96, 96)


def test_square_of_a_missing_preview_is_a_preview_error(tmp_path: Path) -> None:
    with pytest.raises(PreviewError):
        JpegThumbnailer().square(tmp_path / "gone.jpg", 96)


@pytest.mark.parametrize(
    ("page", "pages", "expected"),
    [
        (14, 867, range(9, 19)),  # as in the design: 9 ... 18 around 14
        (1, 867, range(1, 11)),  # slides right at the start
        (3, 867, range(1, 11)),
        (867, 867, range(858, 868)),  # slides left at the end
        (864, 867, range(858, 868)),
        (3, 5, range(1, 6)),  # fewer pages than the window
        (1, 1, range(1, 2)),
    ],
)
def test_page_window_keeps_ten_numbers_around_the_page(
    page: int, pages: int, expected: range
) -> None:
    window = page_window(page, pages)

    assert window == expected
    assert page in window


def test_the_current_page_inverts_with_the_theme() -> None:
    light_circle, light_number = CURRENT_PAGE_COLOURS["light"]
    dark_circle, _ = CURRENT_PAGE_COLOURS["dark"]

    assert f"background: {light_circle};" in pager_css("light")
    assert f"color: {light_number};" in pager_css(None)  # unknown: light
    assert f"background: {dark_circle};" in pager_css("dark")


def test_unmarked_photos_get_no_badges() -> None:
    assert tile_marks_html(favorite=False, trashed=False) == ""


def test_badges_show_a_star_a_bin_or_both() -> None:
    star = tile_marks_html(favorite=True, trashed=False)
    bin_ = tile_marks_html(favorite=False, trashed=True)
    both = tile_marks_html(favorite=True, trashed=True)

    assert 'aria-label="Favorite"' in star and "Marked for deletion" not in star
    assert 'aria-label="Marked for deletion"' in bin_ and "Favorite" not in bin_
    assert both.count('class="ro-tile-mark') == 2
    assert "<button" not in both  # read-only: nothing to toggle in the gallery


def test_the_tile_label_says_how_the_photo_is_marked() -> None:
    assert open_label("a.jpg", False, False) == "Open details for a.jpg"
    assert open_label("a.jpg", True, True) == (
        "Open details for a.jpg, favorite, marked for deletion"
    )


def test_the_tile_stylesheet_has_no_raw_angle_brackets() -> None:
    # st.html drops a <style> whose text contains "<", e.g. an unencoded SVG.
    body = thumbnail_css(rows=4).split("<style>")[1].split("</style>")[0]

    assert "<" not in body
    assert "data:image/svg+xml," in body  # the star and bin icons
