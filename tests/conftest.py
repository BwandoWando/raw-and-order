from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.base import Base
from raw_and_order.db.copy_repository import SqlAlchemyCopyRepository
from raw_and_order.db.failure_repository import SqlAlchemyFailureRepository
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.db.session import create_db_engine, create_session_factory
from raw_and_order.schemas import ExifData, GpsCoordinate


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


@pytest.fixture
def copies(session_factory: sessionmaker[Session]) -> SqlAlchemyCopyRepository:
    return SqlAlchemyCopyRepository(session_factory)
