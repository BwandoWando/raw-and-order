"""Fingerprints: an exact file hash and a perceptual image hash.

- SHA-256 of the file bytes identifies *this exact file*; any byte change,
  including metadata edits, changes it.
- dHash (difference hash) of the image identifies *what it looks like*;
  resized or recompressed copies get the same or a very similar hash.
  Compare two dHashes with :func:`hamming_distance`.
"""

import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from my_agent.exceptions import FingerprintError

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB: low memory even for 80 MB raw files
# 9x9 comparisons -> 81-bit hash, 21 hex characters. Against 8x8 (64 bits) it
# found slightly more look-alikes with about a third of the chance matches.
DHASH_SIZE = 9


def hex_length(size: int) -> int:
    """Hex characters for a ``size`` x ``size`` dHash (bits rounded up to 4)."""
    return -(-size * size // 4)


DHASH_HEX_LENGTH = hex_length(DHASH_SIZE)


class Sha256FileHasher:
    """Hashes a file's bytes with SHA-256, reading it in chunks.

    Args:
        chunk_size: Bytes read per step.
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    def hash_file(self, path: Path) -> str:
        """Return the lowercase hex SHA-256 of ``path``.

        Raises:
            FingerprintError: If the file cannot be read.
        """
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(self._chunk_size):
                    digest.update(chunk)
        except OSError as exc:
            raise FingerprintError(f"Could not hash {path}: {exc}") from exc
        return digest.hexdigest()


def dhash(image: Image.Image, size: int = DHASH_SIZE) -> str:
    """Return the difference hash of ``image`` as a hex string.

    The image is shrunk to ``(size + 1) x size`` greyscale pixels; each bit
    records whether a pixel is brighter than its right-hand neighbour.
    """
    width = size + 1
    pixels = image.convert("L").resize((width, size), Image.Resampling.LANCZOS)
    data = pixels.tobytes()
    value = 0
    for row in range(size):
        for col in range(size):
            left, right = data[row * width + col], data[row * width + col + 1]
            value = (value << 1) | (left > right)
    return f"{value:0{hex_length(size)}x}"


def hamming_distance(first: str, second: str) -> int:
    """Count differing bits between two equal-length hex hashes.

    For 81-bit dHashes, 0 means the same picture (resized or recompressed)
    and 14 or less a close variant; see
    :mod:`my_agent.analysis.similarity`.

    Raises:
        ValueError: If the hashes differ in length or are not hex.
    """
    if len(first) != len(second):
        raise ValueError("Hashes must have the same length")
    return (int(first, 16) ^ int(second, 16)).bit_count()


class DHasher:
    """Computes the perceptual hash of an encoded image (e.g. a JPEG preview)."""

    def hash_image_bytes(self, data: bytes) -> str:
        """Return the dHash of the image encoded in ``data``.

        Raises:
            FingerprintError: If ``data`` is not a readable image.
        """
        try:
            with Image.open(io.BytesIO(data)) as image:
                return dhash(image)
        except (UnidentifiedImageError, OSError) as exc:
            raise FingerprintError(f"Could not compute perceptual hash: {exc}") from exc
