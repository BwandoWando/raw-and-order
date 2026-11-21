"""An exact copy of a stored photo, found in another place."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class PhotoCopy(BaseModel):
    """A file with the same SHA-256 as a photo already catalogued elsewhere."""

    model_config = ConfigDict(frozen=True)

    path: Path
    sha256: str
    original: Path
