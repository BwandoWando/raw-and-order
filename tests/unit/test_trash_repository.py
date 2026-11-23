from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.models import PhotoRow, TrashRow
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.db.trash_repository import SqlAlchemyTrashRepository
from raw_and_order.exceptions import PersistenceError
from raw_and_order.schemas import ExifData, PhotoRecord
from tests.fakes import SAMPLE_ANNOTATION

PHOTO = Path("/photos/a.arw")
MORNING = datetime(2026, 11, 23, 9, 30)  # local wall-clock time, no zone
EVENING = datetime(2026, 11, 23, 21, 0)


@pytest.fixture
def trash(
    session_factory: sessionmaker[Session], repository: SqlAlchemyPhotoRepository
) -> SqlAlchemyTrashRepository:
    repository.upsert(
        PhotoRecord(
            path=PHOTO,
            exif=ExifData(),
            annotation=SAMPLE_ANNOTATION,
            preview_path=Path("/previews/a.jpg"),
            annotated_by="test",
            processed_at=datetime(2026, 11, 1, tzinfo=UTC),
        )
    )
    return SqlAlchemyTrashRepository(session_factory)


def _stored_times(session_factory: sessionmaker[Session]) -> list[datetime]:
    with session_factory() as session:
        return list(session.scalars(select(TrashRow.trashed_at)))


def test_a_photo_is_not_marked_until_trashed(trash: SqlAlchemyTrashRepository) -> None:
    assert not trash.is_trashed(PHOTO)

    trash.set_trashed(PHOTO, True, when=MORNING)

    assert trash.is_trashed(PHOTO)


def test_unmarking_removes_the_mark_and_keeps_the_photo(
    trash: SqlAlchemyTrashRepository, session_factory: sessionmaker[Session]
) -> None:
    trash.set_trashed(PHOTO, True, when=MORNING)

    trash.set_trashed(PHOTO, False, when=EVENING)

    assert not trash.is_trashed(PHOTO)
    assert _stored_times(session_factory) == []
    with session_factory() as session:  # only a mark: the photo stays stored
        assert session.scalar(select(PhotoRow.path)) == str(PHOTO)


def test_marking_again_keeps_the_first_time(
    trash: SqlAlchemyTrashRepository, session_factory: sessionmaker[Session]
) -> None:
    trash.set_trashed(PHOTO, True, when=MORNING)
    trash.set_trashed(PHOTO, True, when=EVENING)

    assert _stored_times(session_factory) == [MORNING]  # one row, local time


def test_only_stored_photos_can_be_marked(trash: SqlAlchemyTrashRepository) -> None:
    with pytest.raises(PersistenceError, match="not in the database"):
        trash.set_trashed(Path("/photos/unknown.arw"), True, when=MORNING)


def test_deleting_the_photo_row_deletes_its_mark(
    trash: SqlAlchemyTrashRepository, session_factory: sessionmaker[Session]
) -> None:
    trash.set_trashed(PHOTO, True, when=MORNING)

    with session_factory.begin() as session:
        session.execute(delete(PhotoRow).where(PhotoRow.path == str(PHOTO)))

    assert _stored_times(session_factory) == []
