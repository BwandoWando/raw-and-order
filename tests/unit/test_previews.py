from pathlib import Path

import pytest
from PIL import Image

from my_agent.exceptions import PreviewError
from my_agent.media.previews import JpegPreviewStore, make_preview, preview_filename


def test_make_preview_limits_longest_side() -> None:
    preview = make_preview(Image.new("RGBA", (4000, 3000)), max_px=1000)

    assert preview.size == (1000, 750)
    assert preview.mode == "RGB"


def test_preview_filename_differs_for_same_stem_in_other_folders(
    tmp_path: Path,
) -> None:
    first = preview_filename(tmp_path / "a" / "IMG_0001.CR3")
    second = preview_filename(tmp_path / "b" / "IMG_0001.CR3")

    assert first != second
    assert first.startswith("IMG_0001-")


def test_store_round_trips_jpeg(tmp_path: Path) -> None:
    store = JpegPreviewStore(tmp_path / "previews", max_px=32)

    saved = store.save(Image.new("RGB", (64, 64)), tmp_path / "x.nef")

    assert store.load(saved).startswith(b"\xff\xd8")  # JPEG magic bytes


def test_load_missing_preview_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(PreviewError):
        JpegPreviewStore(tmp_path, max_px=32).load(tmp_path / "missing.jpg")
