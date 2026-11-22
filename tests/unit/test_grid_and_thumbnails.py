import io
from pathlib import Path

import pytest
from PIL import Image

from raw_and_order.exceptions import PreviewError
from raw_and_order.media.thumbnails import JpegThumbnailer
from raw_and_order.schemas.query import PAGE_SIZES
from raw_and_order.ui.gallery import thumbnail_css
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
