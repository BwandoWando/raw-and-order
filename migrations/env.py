"""Alembic environment: reads the DB URL from app settings."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from raw_and_order.config import load_settings
from raw_and_order.db import models  # noqa: F401  (registers tables on Base.metadata)
from raw_and_order.db.base import Base
from raw_and_order.db.session import create_db_engine

config = context.config
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Prefer an explicit URL (used by tests), else app settings."""
    return config.get_main_option("sqlalchemy.url") or load_settings().database_url


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite cannot ALTER most columns in place
        compare_type=True,
        literal_binds=url is not None,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection."""
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations to the database."""
    engine = create_db_engine(_database_url())
    with engine.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
