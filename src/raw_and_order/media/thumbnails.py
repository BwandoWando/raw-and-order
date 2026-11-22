"""Small JPEG thumbnails of saved previews, for dense gallery grids."""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from raw_and_order.exceptions import PreviewError

THUMBNAIL_QUALITY = 80


class JpegThumbnailer:
    """Shrinks saved previews into JPEG thumbnails and reads their size.

    Args:
        quality: JPEG quality of the thumbnails (1-100).
    """

    def __init__(self, quality: int = THUMBNAIL_QUALITY) -> None:
        self._quality = quality

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes:
        """Return JPEG bytes of the preview, longest side at most ``max_px``.

        Smaller previews are never enlarged.

        Raises:
            PreviewError: If the preview is missing or not an image.
        """
        with _open_preview(preview_path) as image:
            image.thumbnail((max_px, max_px))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "JPEG", quality=self._quality)
        return buffer.getvalue()

    def size(self, preview_path: Path) -> tuple[int, int]:
        """Return the preview's width and height, read from its header only.

        Previews are saved already rotated, so this is the photo as shown.

        Raises:
            PreviewError: If the preview is missing or not an image.
        """
        with _open_preview(preview_path) as image:
            width, height = image.size
        return int(width), int(height)


@contextmanager
def _open_preview(preview_path: Path) -> Iterator[Image.Image]:
    """Open a saved preview, turning any read failure into a PreviewError.

    Failures while the image is in use (e.g. a truncated file found while
    shrinking it) are converted too.
    """
    try:
        with Image.open(preview_path) as image:
            yield image
    except (OSError, UnidentifiedImageError) as exc:
        raise PreviewError(f"Could not read preview {preview_path}: {exc}") from exc
