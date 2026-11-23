from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.favorite_repository import SqlAlchemyFavoriteRepository
from raw_and_order.db.models import FavoriteRow, PhotoRow
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.exceptions import PersistenceError
from raw_and_order.schemas import ExifData, PhotoRecord
from tests.fakes import SAMPLE_ANNOTATION

PHOTO = Path("/photos/a.arw")
MORNING = datetime(2026, 11, 22, 9, 30)  # local wall-clock time, no zone
EVENING = datetime(2026, 11, 22, 21, 0)


@pytest.fixture
def favorites(
    session_factory: sessionmaker[Session], repository: SqlAlchemyPhotoRepository
) -> SqlAlchemyFavoriteRepository:
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
    return SqlAlchemyFavoriteRepository(session_factory)


def _stored_times(session_factory: sessionmaker[Session]) -> list[datetime]:
    with session_factory() as session:
        return list(session.scalars(select(FavoriteRow.favorited_at)))


def test_a_photo_is_not_a_favorite_until_starred(
    favorites: SqlAlchemyFavoriteRepository,
) -> None:
    assert not favorites.is_favorite(PHOTO)

    favorites.set_favorite(PHOTO, True, when=MORNING)

    assert favorites.is_favorite(PHOTO)


def test_unstarring_removes_the_favorite(
    favorites: SqlAlchemyFavoriteRepository, session_factory: sessionmaker[Session]
) -> None:
    favorites.set_favorite(PHOTO, True, when=MORNING)

    favorites.set_favorite(PHOTO, False, when=EVENING)

    assert not favorites.is_favorite(PHOTO)
    assert _stored_times(session_factory) == []


def test_starring_again_keeps_the_first_time(
    favorites: SqlAlchemyFavoriteRepository, session_factory: sessionmaker[Session]
) -> None:
    favorites.set_favorite(PHOTO, True, when=MORNING)
    favorites.set_favorite(PHOTO, True, when=EVENING)

    assert _stored_times(session_factory) == [MORNING]  # one row, local time


def test_only_stored_photos_can_be_starred(
    favorites: SqlAlchemyFavoriteRepository,
) -> None:
    with pytest.raises(PersistenceError, match="not in the database"):
        favorites.set_favorite(Path("/photos/unknown.arw"), True, when=MORNING)


def test_deleting_the_photo_deletes_its_favorite(
    favorites: SqlAlchemyFavoriteRepository, session_factory: sessionmaker[Session]
) -> None:
    favorites.set_favorite(PHOTO, True, when=MORNING)

    with session_factory.begin() as session:
        session.execute(delete(PhotoRow).where(PhotoRow.path == str(PHOTO)))

    assert _stored_times(session_factory) == []


def test_favorites_among_checks_a_whole_page_at_once(
    favorites: SqlAlchemyFavoriteRepository,
) -> None:
    favorites.set_favorite(PHOTO, True, when=MORNING)
    unknown = Path("/photos/not-stored.arw")

    assert favorites.favorites_among([PHOTO, unknown]) == {PHOTO}
    assert favorites.favorites_among([unknown]) == set()
    assert favorites.favorites_among([]) == set()
