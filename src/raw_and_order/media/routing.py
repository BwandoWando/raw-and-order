"""Pick the right decoder for a file based on its extension."""

from collections.abc import Iterable
from pathlib import Path

from PIL import Image

from raw_and_order.media.protocols import ImageDecoder


class ExtensionRoutingDecoder:
    """Sends raw files to one decoder and everything else to another.

    Args:
        raw_decoder: Used for files whose extension is in ``raw_extensions``.
        image_decoder: Used for all other files.
        raw_extensions: Lowercase extensions including the dot.
    """

    def __init__(
        self,
        raw_decoder: ImageDecoder,
        image_decoder: ImageDecoder,
        raw_extensions: Iterable[str],
    ) -> None:
        self._raw_decoder = raw_decoder
        self._image_decoder = image_decoder
        self._raw_extensions = frozenset(ext.lower() for ext in raw_extensions)

    def decode(self, path: Path) -> Image.Image:
        """Decode ``path`` with the decoder that handles its extension."""
        return self._select(path).decode(path)

    def _select(self, path: Path) -> ImageDecoder:
        if path.suffix.lower() in self._raw_extensions:
            return self._raw_decoder
        return self._image_decoder
