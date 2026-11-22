"""previews: YYYYMMDD folders become YYYY/MM/DD

Moves every stored photo's preview file from
``<root>/YYYYMMDD/<extension>/<file>`` to ``<root>/YYYY/MM/DD/<extension>/<file>``
and rewrites ``photos.preview_path`` to match. ``unknown-date`` previews stay
where they are. Emptied old folders are removed.

Safe to re-run after an interruption: a row whose file was already moved is
just updated. Relative paths are resolved from the current directory, as the
app does, so run ``alembic`` from the project root.

Revision ID: 8b90482f2e0b
Revises: 052f7e208915
Create Date: 2026-11-22 16:10:25.260464
"""

import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "8b90482f2e0b"
down_revision: str | None = "052f7e208915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLAT_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})")
_YEAR, _MONTH_OR_DAY = re.compile(r"\d{4}"), re.compile(r"\d{2}")


def _to_nested(path: Path) -> Path | None:
    """``.../20240501/nef/x.jpg`` -> ``.../2024/05/01/nef/x.jpg``, else None."""
    if len(path.parts) < 3:
        return None
    match = _FLAT_DATE.fullmatch(path.parts[-3])
    if match is None:
        return None
    return path.parents[2].joinpath(*match.groups(), *path.parts[-2:])


def _to_flat(path: Path) -> Path | None:
    """``.../2024/05/01/nef/x.jpg`` -> ``.../20240501/nef/x.jpg``, else None."""
    if len(path.parts) < 5:
        return None
    year, month, day = path.parts[-5:-2]
    if not (
        _YEAR.fullmatch(year)
        and _MONTH_OR_DAY.fullmatch(month)
        and _MONTH_OR_DAY.fullmatch(day)
    ):
        return None
    return path.parents[4].joinpath(year + month + day, *path.parts[-2:])


def _move(old: Path, new: Path) -> None:
    """Move one preview, then drop the old folders if they are now empty."""
    if not old.is_file():
        return  # already moved by an interrupted run, or missing anyway
    new.parent.mkdir(parents=True, exist_ok=True)
    os.replace(old, new)
    for folder in old.parents:
        try:
            folder.rmdir()
        except OSError:
            break  # not empty (or not ours): stop climbing


def _relocate(convert: Callable[[Path], Path | None]) -> None:
    """Move each photo's preview with ``convert`` and update its stored path."""
    photos = sa.table(
        "photos", sa.column("id", sa.Integer), sa.column("preview_path", sa.String)
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(photos.c.id, photos.c.preview_path)).all()
    updates = []
    for photo_id, stored in rows:
        new = convert(Path(stored))
        if new is None:
            continue
        _move(Path(stored), new)
        updates.append({"photo_id": photo_id, "new_path": str(new)})
    if updates:
        connection.execute(
            photos.update()
            .where(photos.c.id == sa.bindparam("photo_id"))
            .values(preview_path=sa.bindparam("new_path")),
            updates,
        )


def upgrade() -> None:
    _relocate(_to_nested)


def downgrade() -> None:
    _relocate(_to_flat)
