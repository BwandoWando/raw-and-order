"""Grid geometry that fits one page of thumbnails on one screen.

Streamlit cannot tell Python the browser's size, so the shape is chosen for a
typical landscape window and the tile height is left to CSS (``vh`` units),
which follows the real window, including resizes.
"""

import math

SCREEN_RATIO = 1.6  # width / height of the area left for the grid
TILE_RATIO = 1.5  # width / height of a tile (3:2, like most camera photos)
REFERENCE_WIDTH_PX = 1600  # grid width used to size thumbnails
HIDPI = 2  # thumbnails at twice the tile width stay sharp on retina screens
THUMBNAIL_SIZES = (256, 384, 512)  # few sizes, so the cache reuses them


def grid_shape(page_size: int) -> tuple[int, int]:
    """Columns and rows that fit ``page_size`` tiles in a landscape window."""
    columns = max(1, math.ceil(math.sqrt(page_size * SCREEN_RATIO / TILE_RATIO)))
    return columns, math.ceil(page_size / columns)


def thumbnail_px(columns: int) -> int:
    """Smallest standard thumbnail size that is sharp at this column count."""
    needed = math.ceil(REFERENCE_WIDTH_PX / columns) * HIDPI
    return next((px for px in THUMBNAIL_SIZES if px >= needed), THUMBNAIL_SIZES[-1])
