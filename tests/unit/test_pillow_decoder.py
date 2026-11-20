from pathlib import Path

import pytest
from PIL import Image

from my_agent.exceptions import ImageDecodeError, UnsupportedFormatError
from my_agent.media.heif import enable_heif_support
from my_agent.media.pillow_decoder import PillowDecoder

ORIENTATION = 0x0112


def _save_with_orientation(path: Path, size: tuple[int, int], orientation: int) -> None:
    image = Image.new("RGB", size)
    exif = image.getexif()
    exif[ORIENTATION] = orientation
    image.save(path, exif=exif)


@pytest.mark.parametrize("suffix", [".jpg", ".png", ".tiff", ".webp"])
def test_decodes_common_formats(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / f"img{suffix}"
    mode = "RGB" if suffix == ".jpg" else "RGBA"  # JPEG has no alpha channel
    Image.new(mode, (40, 30)).save(path)

    image = PillowDecoder().decode(path)

    assert (image.size, image.mode) == ((40, 30), "RGB")


def test_applies_exif_orientation(tmp_path: Path) -> None:
    path = tmp_path / "portrait.jpg"
    _save_with_orientation(path, (40, 30), orientation=6)  # rotate 90 degrees

    assert PillowDecoder().decode(path).size == (30, 40)


def test_decodes_heic_when_enabled(tmp_path: Path) -> None:
    if not enable_heif_support():
        pytest.skip("pillow-heif not installed")
    path = tmp_path / "phone.heic"
    Image.new("RGB", (40, 30)).save(path)

    assert PillowDecoder().decode(path).size == (40, 30)


def test_non_image_raises_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "notes.jpg"
    path.write_text("not an image")

    with pytest.raises(UnsupportedFormatError):
        PillowDecoder().decode(path)


def test_truncated_image_raises_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.jpg"
    Image.new("RGB", (200, 200), color=(10, 200, 30)).save(path)
    path.write_bytes(path.read_bytes()[:400])

    with pytest.raises(ImageDecodeError):
        PillowDecoder().decode(path)


def test_missing_file_raises_decode_error(tmp_path: Path) -> None:
    with pytest.raises(ImageDecodeError):
        PillowDecoder().decode(tmp_path / "missing.jpg")
