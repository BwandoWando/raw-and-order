from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from my_agent.db.base import Base
from my_agent.db.failure_repository import SqlAlchemyFailureRepository
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.db.session import create_db_engine, create_session_factory
from my_agent.schemas import ExifData, GpsCoordinate


@pytest.fixture(autouse=True)
def isolate_from_real_settings(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never let a test touch the real database, previews or LLM from ``.env``.

    Environment variables take precedence over ``.env``, so anything that
    loads settings (e.g. a CLI test) only sees throwaway locations. The LLM
    points at a closed local port, so an accidental call fails fast.
    """
    base = tmp_path_factory.mktemp("isolated")
    monkeypatch.setenv("DATA_DIR", str(base))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{base / 'app.db'}")
    monkeypatch.setenv("PREVIEW_DIR", str(base / "previews"))
    monkeypatch.setenv("LLM__PROVIDER", "ollama")
    monkeypatch.setenv("LLM__BASE_URL", "http://127.0.0.1:9")


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


@pytest.fixture
def failures(session_factory: sessionmaker[Session]) -> SqlAlchemyFailureRepository:
    return SqlAlchemyFailureRepository(session_factory)
