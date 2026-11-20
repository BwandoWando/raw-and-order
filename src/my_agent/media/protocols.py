"""Interfaces for media adapters, used for constructor injection."""

from pathlib import Path
from typing import Protocol

from PIL.Image import Image

from my_agent.schemas.exif import ExifData


class PhotoDiscoverer(Protocol):
    """Finds photo files to process."""

    def find(self, root: Path) -> list[Path]:
        """Return supported photo files under ``root``, sorted."""
        ...


class ExifReader(Protocol):
    """Reads EXIF metadata from a file."""

    def read(self, path: Path) -> ExifData:
        """Return the EXIF metadata of ``path``."""
        ...


class RawDecoder(Protocol):
    """Decodes a raw file into a viewable image."""

    def decode(self, path: Path) -> Image:
        """Return an RGB image for ``path``."""
        ...


class PreviewStore(Protocol):
    """Saves and loads downscaled JPEG previews."""

    def save(self, image: Image, source: Path) -> Path:
        """Save a preview of ``image`` for ``source`` and return its path."""
        ...

    def load(self, preview_path: Path) -> bytes:
        """Return the JPEG bytes of a saved preview."""
        ...
