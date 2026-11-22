"""Engine and session factory creation, with the SQLite settings the app needs."""

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, make_url
from sqlalchemy.orm import Session, sessionmaker


def ensure_sqlite_directory(database_url: str) -> None:
    """Create the parent directory of a file-based SQLite database."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
        Path(str(url.database)).parent.mkdir(parents=True, exist_ok=True)


def create_db_engine(database_url: str) -> Engine:
    """Create an engine; for SQLite, also create its folder and set it up.

    Every SQLite connection gets foreign keys and WAL mode (see
    :func:`_configure_sqlite`).
    """
    ensure_sqlite_directory(database_url)
    engine = create_engine(database_url)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``."""
    return sessionmaker(engine, expire_on_commit=False)


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    """Run on each new connection.

    SQLite turns foreign keys off for every new connection unless asked;
    favorites rely on them to be deleted with their photo. WAL lets the UI
    read while a run writes.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
