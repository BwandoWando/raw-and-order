import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from my_agent.exceptions import FingerprintError
from my_agent.media.hashing import DHasher, Sha256FileHasher, dhash, hamming_distance

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


# --- dHash -------------------------------------------------------------------


def test_dhash_is_16_hex_characters() -> None:
    value = dhash(_scene())

    assert len(value) == 16
    int(value, 16)  # valid hex


def test_dhash_survives_resize_and_recompression() -> None:
    original = DHasher().hash_image_bytes(_jpeg(_scene((600, 400))))
    smaller = DHasher().hash_image_bytes(_jpeg(_scene((300, 200)), quality=40))

    assert hamming_distance(original, smaller) <= 4


def test_dhash_differs_for_different_pictures() -> None:
    first = dhash(_scene(sun_x=0.75))
    second = dhash(_scene(sun_x=0.05).transpose(Image.Transpose.FLIP_TOP_BOTTOM))

    assert hamming_distance(first, second) > 10


def test_dhash_of_invalid_bytes_raises_domain_error() -> None:
    with pytest.raises(FingerprintError):
        DHasher().hash_image_bytes(b"not an image")


def test_hamming_distance() -> None:
    assert hamming_distance("0000000000000000", "0000000000000000") == 0
    assert hamming_distance("0000000000000000", "000000000000000f") == 4
    assert hamming_distance("ffffffffffffffff", "0000000000000000") == 64
    with pytest.raises(ValueError, match="same length"):
        hamming_distance("ff", "fff")
