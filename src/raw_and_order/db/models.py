"""ORM table definitions. Alembic autogenerates migrations from these."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from raw_and_order.db.base import Base
from raw_and_order.db.types import UtcDateTime


class PhotoRow(Base):
    """One processed photo."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    # Not unique: identical copies in different folders each get a row.
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # 64-bit perceptual hash as 16 hex characters; None until hashed.
    phash: Mapped[str | None] = mapped_column(String(16), index=True)
    preview_path: Mapped[str] = mapped_column(String(1024))

    # EXIF
    make: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    lens_model: Mapped[str | None] = mapped_column(String(256))
    lens_make: Mapped[str | None] = mapped_column(String(128))
    lens_spec: Mapped[str | None] = mapped_column(String(64))
    iso: Mapped[int | None] = mapped_column(Integer)
    exposure_time_s: Mapped[float | None] = mapped_column(Float)
    f_number: Mapped[float | None] = mapped_column(Float)
    focal_length_mm: Mapped[float | None] = mapped_column(Float)
    # The camera's clock as recorded; no time zone (unlike processed_at).
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    date_source: Mapped[str | None] = mapped_column(String(32))
    white_balance: Mapped[str | None] = mapped_column(String(64))
    white_balance_k: Mapped[int | None] = mapped_column(Integer, index=True)
    white_balance_k_source: Mapped[str | None] = mapped_column(String(16))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    gps_latitude: Mapped[float | None] = mapped_column(Float)
    gps_longitude: Mapped[float | None] = mapped_column(Float)
    gps_altitude_m: Mapped[float | None] = mapped_column(Float)

    # Annotation
    description: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    scene: Mapped[str] = mapped_column(String(32), index=True)
    contains_people: Mapped[bool]
    annotated_by: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(UtcDateTime)


class CopyRow(Base):
    """An exact copy (same SHA-256) of a catalogued photo, not annotated again."""

    __tablename__ = "photo_copies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_path: Mapped[str] = mapped_column(String(1024), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime)


class FailureRow(Base):
    """A file that failed processing; removed once it succeeds."""

    __tablename__ = "processing_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(32))
    error_type: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    first_failed_at: Mapped[datetime] = mapped_column(UtcDateTime)
    last_failed_at: Mapped[datetime] = mapped_column(UtcDateTime)


class FavoriteRow(Base):
    """A photo marked as a favorite in the photo details.

    Linked by the photo's row id, which stays the same when the photo is
    processed again. Not by its SHA-256: that is not unique (identical copies
    each get a row) and changes when the file is edited.
    """

    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Wall-clock time of this computer when the star was set; no time zone.
    favorited_at: Mapped[datetime] = mapped_column(DateTime)
