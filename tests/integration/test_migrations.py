"""Migrations apply and roll back cleanly, and match the ORM models."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from my_agent.db.base import Base

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
