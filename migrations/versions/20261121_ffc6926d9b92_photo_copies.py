"""photo copies: exact copies of catalogued photos (same SHA-256)

Revision ID: ffc6926d9b92
Revises: 60df8658bbc2
Create Date: 2026-11-21 09:28:31.606593
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ffc6926d9b92"
down_revision: str | None = "60df8658bbc2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "photo_copies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_path", sa.String(length=1024), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_copies")),
    )
    with op.batch_alter_table("photo_copies", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_photo_copies_original_path"), ["original_path"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_photo_copies_path"), ["path"], unique=True)
        batch_op.create_index(
            batch_op.f("ix_photo_copies_sha256"), ["sha256"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("photo_copies", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_photo_copies_sha256"))
        batch_op.drop_index(batch_op.f("ix_photo_copies_path"))
        batch_op.drop_index(batch_op.f("ix_photo_copies_original_path"))

    op.drop_table("photo_copies")
