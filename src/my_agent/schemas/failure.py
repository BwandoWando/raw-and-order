"""A logged processing failure."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class FailureRecord(BaseModel):
    """A file that failed processing, kept until it succeeds or disappears."""

    model_config = ConfigDict(frozen=True)

    path: Path
    sha256: str | None
    stage: str
    error_type: str
    message: str
    attempts: int
    first_failed_at: datetime
    last_failed_at: datetime
