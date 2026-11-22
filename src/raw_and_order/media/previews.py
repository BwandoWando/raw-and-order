"""Downscaled JPEG previews that are sent to the LLM."""

import hashlib
from datetime import datetime
from pathlib import Path

from PIL import Image

from raw_and_order.exceptions import PreviewError
from raw_and_order.media.protocols import PreviewLayout

DATE_FOLDER_FORMAT = "%Y%m%d"
UNKNOWN_DATE_FOLDER = "unknown-date"
NO_EXTENSION_FOLDER = "no-extension"


def make_preview(image: Image.Image, max_px: int) -> Image.Image:
    """Return an RGB copy of ``image`` whose longest side is at most ``max_px``."""
    preview = image.convert("RGB")
    preview.thumbnail((max_px, max_px))
    return preview


def preview_filename(source: Path) -> str:
    """Return a stable, collision-free file name for the preview of ``source``."""
    digest = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    return f"{source.stem}-{digest}.jpg"


def date_folder(captured_at: datetime | None) -> str:
    """Return ``YYYYMMDD`` for the capture date, or ``unknown-date``."""
    if captured_at is None:
        return UNKNOWN_DATE_FOLDER
    return captured_at.strftime(DATE_FOLDER_FORMAT)


def type_folder(source: Path) -> str:
    """Return the source extension, lowercase and without the dot (``nef``)."""
    return source.suffix.lower().lstrip(".") or NO_EXTENSION_FOLDER


class DatedPreviewLayout:
    """Places previews at ``YYYYMMDD/<extension>/<stem>-<hash>.jpg``.

    The date is the photo's EXIF ``DateTimeOriginal``; photos without one go
    under ``unknown-date``. Extensions are kept as written, so ``.jpg`` and
    ``.jpeg`` get separate folders.
    """

    def relative_path(self, source: Path, captured_at: datetime | None) -> Path:
        """Return the preview path for ``source``, relative to the store root."""
        return (
            Path(date_folder(captured_at))
            / type_folder(source)
            / preview_filename(source)
        )


class JpegPreviewStore:
    """Stores previews as JPEG files, creating folders as needed.

    Args:
        directory: Root folder for previews.
        layout: Decides the sub-folder and file name of each preview.
        max_px: Longest side of the preview in pixels.
        quality: JPEG quality, 1-100.
    """

    def __init__(
        self,
        directory: Path,
        layout: PreviewLayout,
        max_px: int,
        quality: int = 85,
    ) -> None:
        self._directory = directory
        self._layout = layout
        self._max_px = max_px
        self._quality = quality

    def save(
        self, image: Image.Image, source: Path, captured_at: datetime | None
    ) -> Path:
        """Write a preview of ``image`` for ``source`` and return its path.

        Raises:
            PreviewError: If the folder or file cannot be written.
        """
        target = self._directory / self._layout.relative_path(source, captured_at)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            make_preview(image, self._max_px).save(
                target, "JPEG", quality=self._quality
            )
        except OSError as exc:
            raise PreviewError(f"Could not write preview {target}: {exc}") from exc
        return target

    def load(self, preview_path: Path) -> bytes:
        """Return the JPEG bytes of a saved preview.

        Raises:
            PreviewError: If the file cannot be read.
        """
        try:
            return preview_path.read_bytes()
        except OSError as exc:
            raise PreviewError(f"Could not read preview {preview_path}: {exc}") from exc
