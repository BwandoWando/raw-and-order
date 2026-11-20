"""Raw file decoder backed by ``rawpy`` (LibRaw)."""

import io
import logging
from pathlib import Path
from typing import Any

import rawpy
from PIL import Image, UnidentifiedImageError

from my_agent.exceptions import RawDecodeError, UnsupportedFormatError

logger = logging.getLogger(__name__)


class RawpyDecoder:
    """Decodes raw files, preferring the fast embedded preview.

    Most raw files contain a full-size JPEG preview from the camera. Using it
    is much faster than demosaicing; full decoding is the fallback.
    """

    def decode(self, path: Path) -> Image.Image:
        """Return an RGB image for ``path``.

        Raises:
            UnsupportedFormatError: If LibRaw does not support the file.
            RawDecodeError: If the file is corrupt or cannot be read.
        """
        try:
            with rawpy.imread(str(path)) as raw:
                return self._embedded_preview(raw) or self._full_decode(raw)
        except rawpy.LibRawFileUnsupportedError as exc:
            raise UnsupportedFormatError(f"Unsupported raw format: {path}") from exc
        except (rawpy.LibRawError, OSError) as exc:
            raise RawDecodeError(f"Could not decode {path}: {exc}") from exc

    def _embedded_preview(self, raw: Any) -> Image.Image | None:
        try:
            thumb = raw.extract_thumb()
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            return None
        if thumb.format == rawpy.ThumbFormat.BITMAP:
            return Image.fromarray(thumb.data).convert("RGB")
        try:
            return Image.open(io.BytesIO(thumb.data)).convert("RGB")
        except UnidentifiedImageError:
            logger.debug("Embedded thumbnail unreadable, falling back to full decode")
            return None

    def _full_decode(self, raw: Any) -> Image.Image:
        rgb = raw.postprocess(half_size=True, use_camera_wb=True)
        return Image.fromarray(rgb)
