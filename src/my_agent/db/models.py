"""ORM table definitions. Alembic autogenerates migrations from these."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from my_agent.db.base import Base
from my_agent.db.types import UtcDateTime


class PhotoRow(Base):
    """One processed photo."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    # Not unique: identical copies in different folders each get a row.
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    dhash: Mapped[str | None] = mapped_column(String(16), index=True)
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
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    date_source: Mapped[str | None] = mapped_column(String(32))
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
