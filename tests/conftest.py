from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from my_agent.db.base import Base
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.db.session import create_db_engine, create_session_factory
from my_agent.schemas import ExifData, GpsCoordinate


@pytest.fixture
def sample_exif() -> ExifData:
    return ExifData(
        make="Nikon",
        model="Z6",
        iso=200,
        exposure_time_s=0.004,
        f_number=8.0,
        captured_at=datetime(2024, 5, 1, 18, 30),
        gps=GpsCoordinate(latitude=46.5, longitude=8.1),
    )


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def repository(session_factory: sessionmaker[Session]) -> SqlAlchemyPhotoRepository:
    return SqlAlchemyPhotoRepository(session_factory)
