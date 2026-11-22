"""Interfaces for media adapters, used for constructor injection."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from PIL.Image import Image

from raw_and_order.schemas.exif import ExifData


class PhotoDiscoverer(Protocol):
    """Finds photo files to process."""

    def find(self, root: Path) -> list[Path]:
        """Return supported photo files under ``root``, sorted."""
        ...


class FileHasher(Protocol):
    """Computes an exact fingerprint of a file's bytes."""

    def hash_file(self, path: Path) -> str:
        """Return the hex digest of ``path``."""
        ...


class PerceptualHasher(Protocol):
    """Computes a hash of what an image looks like."""

    def hash_image_bytes(self, data: bytes) -> str:
        """Return the perceptual hash of an encoded image."""
        ...


class ExifReader(Protocol):
    """Reads EXIF metadata from a file."""

    def read(self, path: Path) -> ExifData:
        """Return the EXIF metadata of ``path``."""
        ...


class CaptureTimeReader(Protocol):
    """Reads only the capture time of many files at once."""

    def capture_times(self, paths: Sequence[Path]) -> dict[Path, datetime | None]:
        """Return each path's ``DateTimeOriginal``; ``None`` if it has none.

        The value is as recorded, without the fallbacks and plausibility checks
        of the full capture date.
        """
        ...


class Thumbnailer(Protocol):
    """Makes small JPEG thumbnails of saved previews and reads their size."""

    def thumbnail(self, preview_path: Path, max_px: int) -> bytes:
        """Return JPEG bytes no larger than ``max_px`` on the longest side."""
        ...

    def square(self, preview_path: Path, px: int) -> bytes:
        """Return JPEG bytes of the preview's centre, cropped to ``px`` square."""
        ...

    def size(self, preview_path: Path) -> tuple[int, int]:
        """Return the preview's width and height in pixels."""
        ...


class ImageDecoder(Protocol):
    """Decodes a raw or regular image file into a viewable image."""

    def decode(self, path: Path) -> Image:
        """Return an upright RGB image for ``path``."""
        ...


class PreviewLayout(Protocol):
    """Decides where a preview is stored, relative to the preview root."""

    def relative_path(self, source: Path, captured_at: datetime | None) -> Path:
        """Return the relative preview path for ``source``."""
        ...


class PreviewReader(Protocol):
    """Loads saved previews."""

    def load(self, preview_path: Path) -> bytes:
        """Return the JPEG bytes of a saved preview."""
        ...


class PreviewStore(Protocol):
    """Saves and loads downscaled JPEG previews."""

    def save(self, image: Image, source: Path, captured_at: datetime | None) -> Path:
        """Save a preview of ``image`` for ``source`` and return its path."""
        ...

    def load(self, preview_path: Path) -> bytes:
        """Return the JPEG bytes of a saved preview."""
        ...
