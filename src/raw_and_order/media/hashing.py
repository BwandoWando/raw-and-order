"""Fingerprints: an exact file hash and a perceptual image hash.

- SHA-256 of the file bytes identifies *this exact file*; any byte change,
  including metadata edits, changes it.
- pHash (perceptual hash, from the image's low frequencies) identifies *what
  it looks like*; resized, recompressed or lightly edited copies get the same
  or a very similar hash.
  Compare two pHashes with :func:`hamming_distance`.
"""

import hashlib
import io
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from raw_and_order.exceptions import FingerprintError

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MiB: low memory even for 80 MB raw files
# 8x8 low frequencies -> 64-bit hash, 16 hex characters. Its few chance
# matches are filtered out by also requiring shared tags (analysis/similarity.py).
PHASH_SIZE = 8
PHASH_DCT_SIZE = 32  # the image is shrunk to 32x32 before the DCT


def hex_length(size: int) -> int:
    """Hex characters for a ``size`` x ``size`` pHash (bits rounded up to 4)."""
    return -(-size * size // 4)


PHASH_HEX_LENGTH = hex_length(PHASH_SIZE)


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


@cache
def _dct_matrix(n: int) -> np.ndarray:
    """The n x n DCT-II basis (unscaled; scale does not change the bits)."""
    k = np.arange(n)[:, None]
    i = np.arange(n)[None, :]
    return np.cos(np.pi * (2 * i + 1) * k / (2 * n))


def phash(
    image: Image.Image, size: int = PHASH_SIZE, dct_size: int = PHASH_DCT_SIZE
) -> str:
    """Return the perceptual hash of ``image`` as a hex string.

    The image is shrunk to ``dct_size`` x ``dct_size`` greyscale pixels and
    turned into frequencies (a 2-D DCT). The ``size`` x ``size`` lowest
    frequencies describe its overall structure; each bit records whether one
    of them is above their median. Brightness, contrast and compression
    changes barely move these, unlike pixel-by-pixel comparisons.
    """
    grey = image.convert("L").resize((dct_size, dct_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(grey, dtype=np.float64)
    basis = _dct_matrix(dct_size)
    low = (basis @ pixels @ basis.T)[:size, :size]
    value = 0
    for bit in (low > np.median(low)).flatten():
        value = (value << 1) | int(bit)
    return f"{value:0{hex_length(size)}x}"


def hamming_distance(first: str, second: str) -> int:
    """Count differing bits between two equal-length hex hashes.

    For 64-bit pHashes, about 2 or less means the same picture (resized or
    recompressed) and 14 or less a close variant; see
    :mod:`raw_and_order.analysis.similarity`.

    Raises:
        ValueError: If the hashes differ in length or are not hex.
    """
    if len(first) != len(second):
        raise ValueError("Hashes must have the same length")
    return (int(first, 16) ^ int(second, 16)).bit_count()


class PHasher:
    """Computes the perceptual hash of an encoded image (e.g. a JPEG preview)."""

    def hash_image_bytes(self, data: bytes) -> str:
        """Return the pHash of the image encoded in ``data``.

        Raises:
            FingerprintError: If ``data`` is not a readable image.
        """
        try:
            with Image.open(io.BytesIO(data)) as image:
                return phash(image)
        except (UnidentifiedImageError, OSError) as exc:
            raise FingerprintError(f"Could not compute perceptual hash: {exc}") from exc
