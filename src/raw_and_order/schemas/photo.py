"""A fully processed photo, as stored in the database."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from raw_and_order.schemas.annotation import Annotation
from raw_and_order.schemas.exif import ExifData


class PhotoRecord(BaseModel):
    """A photo with its metadata and annotation."""

    model_config = ConfigDict(frozen=True)

    path: Path
    sha256: str | None = None
    phash: str | None = None
    exif: ExifData
    annotation: Annotation
    preview_path: Path
    annotated_by: str
    processed_at: datetime
