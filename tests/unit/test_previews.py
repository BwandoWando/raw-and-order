from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from raw_and_order.exceptions import PreviewError
from raw_and_order.media.previews import (
    DatedPreviewLayout,
    JpegPreviewStore,
    date_folder,
    make_preview,
    preview_filename,
    type_folder,
)


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
    store = JpegPreviewStore(tmp_path / "previews", DatedPreviewLayout(), max_px=32)

    saved = store.save(Image.new("RGB", (64, 64)), tmp_path / "x.nef", None)

    assert store.load(saved).startswith(b"\xff\xd8")  # JPEG magic bytes


def test_load_missing_preview_raises_domain_error(tmp_path: Path) -> None:
    with pytest.raises(PreviewError):
        JpegPreviewStore(tmp_path, DatedPreviewLayout(), max_px=32).load(
            tmp_path / "missing.jpg"
        )


def test_date_folder_uses_capture_date_or_unknown() -> None:
    assert date_folder(datetime(2024, 5, 1, 23, 59)) == "20240501"
    assert date_folder(None) == "unknown-date"


def test_type_folder_keeps_extension_as_written_but_lowercase() -> None:
    assert type_folder(Path("DSC_1.NEF")) == "nef"
    assert type_folder(Path("a.jpg")) == "jpg"
    assert type_folder(Path("b.JPEG")) == "jpeg"  # .jpg and .jpeg stay separate
    assert type_folder(Path("README")) == "no-extension"


def test_layout_combines_date_type_and_file_name(tmp_path: Path) -> None:
    source = tmp_path / "IMG_7.HEIC"

    relative = DatedPreviewLayout().relative_path(source, datetime(2023, 12, 31))

    assert relative.parent == Path("20231231/heic")
    assert relative.name == preview_filename(source)


def test_store_creates_nested_folders_on_the_fly(tmp_path: Path) -> None:
    store = JpegPreviewStore(tmp_path / "previews", DatedPreviewLayout(), max_px=32)

    saved = store.save(Image.new("RGB", (8, 8)), tmp_path / "x.jpeg", None)

    assert saved.parent == tmp_path / "previews" / "unknown-date" / "jpeg"
    assert saved.is_file()
