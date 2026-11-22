from datetime import UTC, datetime
from pathlib import Path

import pytest

from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.exceptions import ExifReadError
from raw_and_order.maintenance.exif_reread import ExifRereader
from raw_and_order.schemas import ExifData, PhotoRecord, WhiteBalanceSource
from tests.fakes import SAMPLE_ANNOTATION

OLD = ExifData(model="ILCE-6400", lens_model="65535")  # as stored by the old reader
NEW = ExifData(
    model="ILCE-6400",
    lens_model="Sigma 17-40mm F1.8 DC | A",
    white_balance="Auto",
    white_balance_k=5400,
    white_balance_k_source=WhiteBalanceSource.ESTIMATED,
)


class MapExifReader:
    """Returns EXIF per file name; raises for names in ``fail_for``."""

    def __init__(
        self, by_name: dict[str, ExifData], fail_for: tuple[str, ...] = ()
    ) -> None:
        self._by_name = by_name
        self._fail_for = fail_for
        self.read_paths: list[Path] = []

    def read(self, path: Path) -> ExifData:
        self.read_paths.append(path)
        if path.name in self._fail_for:
            raise ExifReadError(f"corrupt: {path.name}")
        return self._by_name.get(path.name, OLD)


def _store(
    repository: SqlAlchemyPhotoRepository, path: Path, exif: ExifData = OLD
) -> None:
    repository.upsert(
        PhotoRecord(
            path=path,
            sha256="sha",
            phash="0" * 16,
            exif=exif,
            annotation=SAMPLE_ANNOTATION,
            preview_path=path.with_suffix(".jpg"),
            annotated_by="ollama:gemma3:12b",
            processed_at=datetime(2026, 11, 20, tzinfo=UTC),
        )
    )


@pytest.fixture
def photos(tmp_path: Path, repository: SqlAlchemyPhotoRepository) -> Path:
    folder = tmp_path / "in"
    folder.mkdir()
    for name in ("a.arw", "b.arw", "same.arw", "bad.arw"):
        (folder / name).write_bytes(b"x")
        _store(repository, folder / name)
    _store(repository, folder / "gone.arw")  # stored, but the file was deleted
    other = tmp_path / "other"
    other.mkdir()
    (other / "c.arw").write_bytes(b"x")
    _store(repository, other / "c.arw")  # outside the folder: must not be touched
    return folder


def test_updates_only_changed_exif_and_reports_the_rest(
    photos: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    reader = MapExifReader({"a.arw": NEW, "b.arw": NEW}, fail_for=("bad.arw",))

    summary = ExifRereader(repository, reader).run(photos)

    assert (summary.checked, summary.updated, summary.unchanged) == (5, 2, 1)
    assert summary.missing == [photos / "gone.arw"]
    assert [f.path.name for f in summary.failed] == ["bad.arw"]
    assert all(p.is_relative_to(photos) for p in reader.read_paths)


def test_exif_is_replaced_but_annotation_and_hashes_are_kept(
    photos: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    ExifRereader(repository, MapExifReader({"a.arw": NEW})).run(photos)

    record = repository.get_by_path(photos / "a.arw")
    assert record is not None
    assert record.exif == NEW
    assert record.annotation == SAMPLE_ANNOTATION
    assert (record.sha256, record.phash, record.annotated_by) == (
        "sha",
        "0" * 16,
        "ollama:gemma3:12b",
    )


def test_failed_read_leaves_stored_exif_unchanged(
    photos: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    ExifRereader(repository, MapExifReader({}, fail_for=("bad.arw",))).run(photos)

    record = repository.get_by_path(photos / "bad.arw")
    assert record is not None
    assert record.exif == OLD


def test_folder_with_no_stored_photos(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    summary = ExifRereader(repository, MapExifReader({})).run(tmp_path / "empty")

    assert (summary.checked, summary.updated) == (0, 0)
