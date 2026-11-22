import hashlib
import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageEnhance

from raw_and_order.analysis.similarity import (
    SIMILAR_MAX_DISTANCE,
    Similarity,
    similarity,
)
from raw_and_order.exceptions import FingerprintError
from raw_and_order.media.hashing import (
    PHASH_HEX_LENGTH,
    PHasher,
    Sha256FileHasher,
    hamming_distance,
    hex_length,
    phash,
)

HELLO_SHA256 = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def _scene(size: tuple[int, int] = (600, 400), sun_x: float = 0.75) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, (90, 160, 230))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, height * 2 // 3, width, height], fill=(40, 140, 50))
    x = int(width * sun_x)
    draw.ellipse(
        [x, height // 10, x + width // 8, height // 10 + width // 8],
        fill=(250, 220, 40),
    )
    return image


def _jpeg(image: Image.Image, quality: int = 90) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


# --- SHA-256 -----------------------------------------------------------------


def test_sha256_matches_known_value(tmp_path: Path) -> None:
    path = tmp_path / "hello.txt"
    path.write_bytes(b"hello")

    assert Sha256FileHasher().hash_file(path) == HELLO_SHA256


def test_sha256_streams_across_chunk_boundaries(tmp_path: Path) -> None:
    data = bytes(range(256)) * 1000  # 256 KB
    path = tmp_path / "big.bin"
    path.write_bytes(data)

    assert (
        Sha256FileHasher(chunk_size=1000).hash_file(path)
        == hashlib.sha256(data).hexdigest()
    )


def test_sha256_of_missing_file_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(FingerprintError):
        Sha256FileHasher().hash_file(tmp_path / "missing.nef")


# --- pHash -------------------------------------------------------------------


def test_phash_is_64_bits() -> None:
    value = phash(_scene())

    assert len(value) == PHASH_HEX_LENGTH == 16
    int(value, 16)  # valid hex


def test_phash_length_is_fixed_when_bits_are_not_a_multiple_of_four() -> None:
    hashes = [phash(_texture(seed), size=9) for seed in range(20)]

    assert hex_length(9) == 21
    assert {len(h) for h in hashes} == {21}


def test_phash_survives_resize_and_recompression() -> None:
    original = PHasher().hash_image_bytes(_jpeg(_scene((600, 400))))
    smaller = PHasher().hash_image_bytes(_jpeg(_scene((300, 200)), quality=40))

    assert similarity(hamming_distance(original, smaller)) == Similarity.IDENTICAL


def test_phash_survives_a_brightness_edit() -> None:
    photo = _texture(seed=3).convert("RGB")
    brighter = ImageEnhance.Brightness(photo).enhance(1.1)  # +10%, no clipping

    assert hamming_distance(phash(photo), phash(brighter)) <= 2


def _texture(seed: int) -> Image.Image:
    """A detailed picture (random grey blocks), like a real photo's texture."""
    rng = random.Random(seed)
    pixels = bytes(rng.randrange(256) for _ in range(32 * 32))
    return Image.frombytes("L", (32, 32), pixels).resize((600, 400))


def test_phash_differs_for_different_pictures() -> None:
    first = phash(_texture(seed=1))
    second = phash(_texture(seed=2))

    assert hamming_distance(first, second) > SIMILAR_MAX_DISTANCE


def test_phash_of_invalid_bytes_raises_domain_error() -> None:
    with pytest.raises(FingerprintError):
        PHasher().hash_image_bytes(b"not an image")


def test_hamming_distance() -> None:
    assert hamming_distance("0000000000000000", "0000000000000000") == 0
    assert hamming_distance("0000000000000000", "000000000000000f") == 4
    assert hamming_distance("ffffffffffffffff", "0000000000000000") == 64
    with pytest.raises(ValueError, match="same length"):
        hamming_distance("ff", "fff")
