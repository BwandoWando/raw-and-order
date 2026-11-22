"""Turn database library errors into the app's :class:`PersistenceError`."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from raw_and_order.exceptions import PersistenceError


@contextmanager
def database_errors(action: str) -> Iterator[None]:
    """Raise :class:`PersistenceError` if the database fails inside the block.

    ``action`` completes the message "Could not ...", e.g. ``"list copies"``
    gives ``Could not list copies: <the database's error>``. Errors that are
    not from the database pass through unchanged.

    Example:
        >>> with database_errors("list copies"):  # doctest: +SKIP
        ...     rows = session.scalars(select(CopyRow)).all()
    """
    try:
        yield
    except SQLAlchemyError as exc:
        raise PersistenceError(f"Could not {action}: {exc}") from exc
