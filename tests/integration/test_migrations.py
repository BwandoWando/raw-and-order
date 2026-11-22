"""Migrations apply and roll back cleanly, and match the ORM models."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from raw_and_order.db.base import Base

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config


def test_upgrade_matches_models_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    config = _alembic_config(url)

    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []
    command.downgrade(config, "base")


def _add_photo(url: str, photo_id: int, preview: Path) -> None:
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO photos (id, path, preview_path, description, tags,"
                " scene, contains_people, annotated_by, processed_at)"
                " VALUES (:id, :path, :preview, '', '[]', 'other', 0, 'test',"
                " '2024-05-01 00:00:00')"
            ),
            {
                "id": photo_id,
                "path": f"/photos/{photo_id}.nef",
                "preview": str(preview),
            },
        )
    engine.dispose()


def _preview_paths(url: str) -> dict[int, Path]:
    engine = create_engine(url)
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id, preview_path FROM photos")).all()
    engine.dispose()
    return {photo_id: Path(stored) for photo_id, stored in rows}


def test_preview_folders_move_to_year_month_day_and_back(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    config = _alembic_config(url)
    root = tmp_path / "previews"
    flat = root / "20240501" / "nef" / "a-1.jpg"
    undated = root / "unknown-date" / "jpg" / "b-2.jpg"
    for preview in (flat, undated):
        preview.parent.mkdir(parents=True)
        preview.write_bytes(b"jpeg")
    command.upgrade(config, "052f7e208915")
    _add_photo(url, 1, flat)
    _add_photo(url, 2, undated)

    command.upgrade(config, "8b90482f2e0b")

    nested = root / "2024" / "05" / "01" / "nef" / "a-1.jpg"
    assert _preview_paths(url) == {1: nested, 2: undated}
    assert nested.read_bytes() == b"jpeg"
    assert not (root / "20240501").exists()  # emptied old folder is removed
    assert undated.is_file()

    command.downgrade(config, "052f7e208915")

    assert _preview_paths(url) == {1: flat, 2: undated}
    assert flat.read_bytes() == b"jpeg"
    assert not (root / "2024").exists()
