import pytest
from PIL import Image

from my_agent.media.raw import (
    EXIF_ORIENTATION_TAG,
    apply_raw_flip,
    orient_embedded_preview,
)


def _marked_image() -> Image.Image:
    """40x30 image with a red top-left pixel, to track rotation."""
    image = Image.new("RGB", (40, 30), color=(0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0))
    return image


@pytest.mark.parametrize(
    ("flip", "size", "red_at"),
    [
        (0, (40, 30), (0, 0)),  # no rotation
        (3, (40, 30), (39, 29)),  # 180 degrees
        (5, (30, 40), (0, 39)),  # 90 degrees counter-clockwise
        (6, (30, 40), (29, 0)),  # 90 degrees clockwise
    ],
)
def test_apply_raw_flip(
    flip: int, size: tuple[int, int], red_at: tuple[int, int]
) -> None:
    rotated = apply_raw_flip(_marked_image(), flip)

    assert rotated.size == size
    assert rotated.getpixel(red_at) == (255, 0, 0)


def test_embedded_exif_orientation_takes_priority_over_flip() -> None:
    image = _marked_image()
    image.getexif()[EXIF_ORIENTATION_TAG] = 6

    oriented = orient_embedded_preview(image, flip=3)

    assert oriented.size == (30, 40)  # rotated by EXIF (90), not by flip (180)
