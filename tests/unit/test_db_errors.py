import pytest
from sqlalchemy.exc import OperationalError

from raw_and_order.db.errors import database_errors
from raw_and_order.exceptions import PersistenceError


def test_database_failures_become_persistence_errors() -> None:
    failure = OperationalError("SELECT 1", {}, Exception("database is locked"))

    with pytest.raises(PersistenceError) as caught, database_errors("list copies"):
        raise failure

    assert str(caught.value).startswith("Could not list copies: ")
    assert "database is locked" in str(caught.value)
    assert caught.value.__cause__ is failure


def test_other_errors_pass_through_unchanged() -> None:
    with pytest.raises(KeyError), database_errors("list copies"):
        raise KeyError("not a database error")
