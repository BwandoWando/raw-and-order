"""Small JPEG thumbnails of saved previews, for dense gallery grids."""

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from raw_and_order.exceptions import PreviewError

THUMBNAIL_QUALITY = 80


class JpegThumbnailer:
    """Shrinks a preview so its longest side is at most ``max_px``.

    Args:
        quality: JPEG quality of the thumbnails (1-100).
    """

    def __init__(self, quality: int = THUMBNAIL_QUALITY) -> None:
        self._quality = quality

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes:
        """Return JPEG bytes of the shrunk preview.

        Raises:
            PreviewError: If the preview is missing or not an image.
        """
        try:
            with Image.open(preview_path) as image:
                image.thumbnail((max_px, max_px))
                buffer = io.BytesIO()
                image.convert("RGB").save(buffer, "JPEG", quality=self._quality)
        except (OSError, UnidentifiedImageError) as exc:
            raise PreviewError(f"Could not read preview {preview_path}: {exc}") from exc
        return buffer.getvalue()

    def size(self, preview_path: Path) -> tuple[int, int]:
        """Return the preview's width and height, read from its header only.

        Previews are saved already rotated, so this is the photo as shown.

        Raises:
            PreviewError: If the preview is missing or not an image.
        """
        try:
            with Image.open(preview_path) as image:
                width, height = image.size
                return int(width), int(height)
        except (OSError, UnidentifiedImageError) as exc:
            raise PreviewError(f"Could not read preview {preview_path}: {exc}") from exc
