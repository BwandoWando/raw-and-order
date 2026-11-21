"""Recomputing stored perceptual hashes from previews (``my-agent rehash``)."""

import io
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.media.hashing import DHASH_HEX_LENGTH, DHasher
from my_agent.rehash import PerceptualRehasher
from my_agent.schemas import ExifData, PhotoRecord
from tests.fakes import SAMPLE_ANNOTATION

OLD_HASH = "0" * 16  # a 64-bit hash from before the upgrade


class FilePreviews:
    """Loads previews straight from disk (only ``load`` is needed)."""

    def load(self, preview_path: Path) -> bytes:
        return preview_path.read_bytes()


def _store(repository: SqlAlchemyPhotoRepository, path: Path, preview: Path) -> None:
    repository.upsert(
        PhotoRecord(
            path=path,
            sha256="sha",
            dhash=OLD_HASH,
            exif=ExifData(model="GR IV"),
            annotation=SAMPLE_ANNOTATION,
            preview_path=preview,
            annotated_by="fake",
            processed_at=datetime(2026, 11, 21, tzinfo=UTC),
        )
    )


def _jpeg(path: Path) -> Path:
    image = Image.linear_gradient("L").convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    path.write_bytes(buffer.getvalue())
    return path


def _rehasher(repository: SqlAlchemyPhotoRepository) -> PerceptualRehasher:
    return PerceptualRehasher(repository, DHasher(), FilePreviews())


def test_rehash_updates_hashes_and_lists_problems(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    _store(repository, Path("/p/good.arw"), _jpeg(tmp_path / "good.jpg"))
    _store(repository, Path("/p/gone.arw"), tmp_path / "gone.jpg")
    (tmp_path / "bad.jpg").write_bytes(b"not a jpeg")
    _store(repository, Path("/p/bad.arw"), tmp_path / "bad.jpg")

    summary = _rehasher(repository).run()

    assert (summary.checked, summary.updated, summary.unchanged) == (3, 1, 0)
    assert summary.missing_previews == [Path("/p/gone.arw")]
    assert [f.path for f in summary.failed] == [Path("/p/bad.arw")]
    good = repository.get_by_path(Path("/p/good.arw"))
    assert good is not None and good.dhash is not None
    assert len(good.dhash) == DHASH_HEX_LENGTH
    assert good.annotated_by == "fake"  # nothing else changes
    bad = repository.get_by_path(Path("/p/bad.arw"))
    assert bad is not None and bad.dhash == OLD_HASH


def test_second_rehash_changes_nothing(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository
) -> None:
    _store(repository, Path("/p/good.arw"), _jpeg(tmp_path / "good.jpg"))
    _rehasher(repository).run()

    summary = _rehasher(repository).run()

    assert (summary.updated, summary.unchanged) == (0, 1)
