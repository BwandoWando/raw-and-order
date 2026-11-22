"""Raw file decoder backed by ``rawpy`` (LibRaw).

"Embedded image" here means the JPEG (or bitmap) the camera stored inside the
raw file. It is not this app's "preview", the downscaled JPEG saved for the
LLM and the UI (:mod:`raw_and_order.media.previews`).
"""

import io
import logging
from pathlib import Path
from typing import Any

import rawpy
from PIL import Image, ImageOps, UnidentifiedImageError

from raw_and_order.exceptions import ImageDecodeError, UnsupportedFormatError

logger = logging.getLogger(__name__)

EXIF_ORIENTATION_TAG = 0x0112

# LibRaw ``sizes.flip`` -> PIL transpose that makes the image upright. Other
# values (0, or rare mirrored ones) leave the image as it is.
_FLIP_TO_TRANSPOSE = {
    3: Image.Transpose.ROTATE_180,
    5: Image.Transpose.ROTATE_90,  # rotates 90 degrees counter-clockwise
    6: Image.Transpose.ROTATE_270,  # rotates 90 degrees clockwise
}


def apply_raw_flip(image: Image.Image, flip: int) -> Image.Image:
    """Rotate ``image`` according to a LibRaw ``flip`` value (0 = none).

    Unknown values return ``image`` unchanged.
    """
    transpose = _FLIP_TO_TRANSPOSE.get(flip)
    return image.transpose(transpose) if transpose is not None else image


def orient_embedded_image(image: Image.Image, flip: int) -> Image.Image:
    """Make the image embedded in a raw file upright.

    Embedded images are usually stored unrotated, with the orientation kept
    in the raw file. If the image carries its own EXIF orientation, that is
    used instead so the image is never rotated twice.
    """
    if image.getexif().get(EXIF_ORIENTATION_TAG, 1) > 1:
        return ImageOps.exif_transpose(image)
    return apply_raw_flip(image, flip)


class RawpyDecoder:
    """Decodes raw files, preferring the image the camera embedded in them.

    Most raw files contain a JPEG rendered by the camera, often full size
    (rawpy calls it the "thumb"). Using it is much faster than demosaicing and
    matches what the camera showed; a half-size full decode is the fallback
    when there is none or it cannot be read. Not to be confused with this
    app's previews, the small JPEGs saved for the LLM and the UI.
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
        embedded = self._embedded_image(raw)
        if embedded is None:
            return self._full_decode(raw)
        return orient_embedded_image(embedded, raw.sizes.flip).convert("RGB")

    def _embedded_image(self, raw: Any) -> Image.Image | None:
        """The camera's embedded image, or ``None`` if absent or unreadable.

        Rawpy returns either raw RGB pixels (``BITMAP``) or encoded JPEG bytes.
        """
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
        # postprocess() already applies the raw file's orientation. Half size
        # is plenty for a downscaled preview and much faster to decode.
        rgb = raw.postprocess(half_size=True, use_camera_wb=True)
        return Image.fromarray(rgb)
