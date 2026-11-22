"""Persistence layer: SQLAlchemy ORM models, repositories and the UI's catalog.

Tables are in :mod:`~raw_and_order.db.models`. Each repository module offers a
``Protocol`` for callers to depend on and a ``SqlAlchemy...`` class that
implements it; all database errors leave this package as
:class:`~raw_and_order.exceptions.PersistenceError` (see
:mod:`~raw_and_order.db.errors`).
"""
