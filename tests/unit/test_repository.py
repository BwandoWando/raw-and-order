from datetime import UTC, datetime
from pathlib import Path

from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.schemas import ExifData, PhotoRecord
from tests.fakes import SAMPLE_ANNOTATION


def _record(exif: ExifData, description: str = "first") -> PhotoRecord:
    return PhotoRecord(
        path=Path("/photos/a.nef"),
        exif=exif,
        annotation=SAMPLE_ANNOTATION.model_copy(update={"description": description}),
        preview_path=Path("/previews/a.jpg"),
        annotated_by="ollama:test",
        processed_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


def test_upsert_then_get_round_trips(
    repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    record = _record(sample_exif)

    repository.upsert(record)
    loaded = repository.get_by_path(record.path)

    assert loaded is not None
    assert loaded.exif == record.exif
    assert loaded.annotation == record.annotation


def test_upsert_updates_existing_row(
    repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    repository.upsert(_record(sample_exif, "first"))
    repository.upsert(_record(sample_exif, "second"))

    loaded = repository.get_by_path(Path("/photos/a.nef"))
    assert loaded is not None
    assert loaded.annotation.description == "second"
    assert repository.known_paths() == {Path("/photos/a.nef")}


def test_get_missing_returns_none(repository: SqlAlchemyPhotoRepository) -> None:
    assert repository.get_by_path(Path("/nope.nef")) is None
