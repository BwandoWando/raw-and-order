"""Raw file decoder backed by ``rawpy`` (LibRaw)."""

import io
import logging
from pathlib import Path
from typing import Any

import rawpy
from PIL import Image, ImageOps, UnidentifiedImageError

from raw_and_order.exceptions import ImageDecodeError, UnsupportedFormatError

logger = logging.getLogger(__name__)

EXIF_ORIENTATION_TAG = 0x0112

# LibRaw ``sizes.flip`` -> PIL transpose that makes the image upright.
_FLIP_TO_TRANSPOSE = {
    3: Image.Transpose.ROTATE_180,
    5: Image.Transpose.ROTATE_90,  # 90 degrees counter-clockwise
    6: Image.Transpose.ROTATE_270,  # 90 degrees clockwise
}


def apply_raw_flip(image: Image.Image, flip: int) -> Image.Image:
    """Rotate ``image`` according to a LibRaw ``flip`` value (0 = none)."""
    transpose = _FLIP_TO_TRANSPOSE.get(flip)
    return image.transpose(transpose) if transpose is not None else image


def orient_embedded_preview(image: Image.Image, flip: int) -> Image.Image:
    """Make an embedded preview upright.

    Embedded previews are usually stored unrotated, with the orientation kept
    in the raw file. If the preview carries its own EXIF orientation, that is
    used instead so the image is never rotated twice.
    """
    if image.getexif().get(EXIF_ORIENTATION_TAG, 1) > 1:
        return ImageOps.exif_transpose(image)
    return apply_raw_flip(image, flip)


class RawpyDecoder:
    """Decodes raw files, preferring the fast embedded preview.

    Most raw files contain a full-size JPEG preview from the camera. Using it
    is much faster than demosaicing; full decoding is the fallback.
    """

    def decode(self, path: Path) -> Image.Image:
        """Return an upright RGB image for ``path``.

        Raises:
            UnsupportedFormatError: If LibRaw does not support the file.
            ImageDecodeError: If the file is corrupt or cannot be read.
        """
        try:
            with rawpy.imread(str(path)) as raw:
                return self._decode_open_raw(raw)
        except rawpy.LibRawFileUnsupportedError as exc:
            raise UnsupportedFormatError(f"Unsupported raw format: {path}") from exc
        except (rawpy.LibRawError, OSError) as exc:
            raise ImageDecodeError(f"Could not decode {path}: {exc}") from exc

    def _decode_open_raw(self, raw: Any) -> Image.Image:
        preview = self._embedded_preview(raw)
        if preview is None:
            return self._full_decode(raw)
        return orient_embedded_preview(preview, raw.sizes.flip).convert("RGB")

    def _embedded_preview(self, raw: Any) -> Image.Image | None:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            return None
        if thumb.format == rawpy.ThumbFormat.BITMAP:
            return Image.fromarray(thumb.data)
        try:
            return Image.open(io.BytesIO(thumb.data))
        except UnidentifiedImageError:
            logger.debug("Embedded thumbnail unreadable, falling back to full decode")
            return None

    def _full_decode(self, raw: Any) -> Image.Image:
        # postprocess() already applies the raw file's orientation.
        rgb = raw.postprocess(half_size=True, use_camera_wb=True)
        return Image.fromarray(rgb)
