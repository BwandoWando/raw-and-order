"""Decoder for regular image files (JPEG, PNG, TIFF, WebP, HEIC) via Pillow."""

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from my_agent.exceptions import ImageDecodeError, UnsupportedFormatError


class PillowDecoder:
    """Opens image files with Pillow and rotates them upright.

    HEIC/HEIF files need :func:`my_agent.media.heif.enable_heif_support` to
    have been called at startup.
    """

    def decode(self, path: Path) -> Image.Image:
        """Return an upright RGB image for ``path``.

        Raises:
            UnsupportedFormatError: If Pillow cannot identify the format.
            ImageDecodeError: If the file is corrupt, unreadable or too large.
        """
        try:
            with Image.open(path) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
        except UnidentifiedImageError as exc:
            raise UnsupportedFormatError(f"Not a supported image: {path}") from exc
        except (OSError, Image.DecompressionBombError) as exc:
            raise ImageDecodeError(f"Could not decode {path}: {exc}") from exc
