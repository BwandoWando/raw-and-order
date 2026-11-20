"""Graph state models."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from my_agent.schemas import Annotation, ExifData


class Stage(StrEnum):
    """Pipeline steps, used to report where a file failed."""

    FINGERPRINT = "fingerprint"
    EXTRACT_EXIF = "extract_exif"
    DECODE = "decode"
    PERCEPTUAL_HASH = "perceptual_hash"
    ANNOTATE = "annotate"
    PERSIST = "persist"


class FileError(BaseModel):
    """Why a single file failed, recorded instead of stopping the batch."""

    stage: Stage
    error_type: str
    message: str


class PhotoItem(BaseModel):
    """One file moving through the pipeline."""

    path: Path
    sha256: str | None = None
    exif: ExifData | None = None
    preview_path: Path | None = None
    dhash: str | None = None
    annotation: Annotation | None = None
    saved: bool = False
    error: FileError | None = None

    @property
    def is_ok(self) -> bool:
        """True while no step has failed for this file."""
        return self.error is None


class GraphState(BaseModel):
    """State shared by all nodes for one batch run."""

    source_dir: Path
    reprocess: bool = False
    max_photos: int | None = Field(
        default=None, description="Per-run limit; None means no limit."
    )
    items: list[PhotoItem] = Field(default_factory=list)
    skipped_pairs: list[Path] = Field(
        default_factory=list,
        description="Images skipped because a raw file of the same shot exists.",
    )
    unchanged: list[Path] = Field(
        default_factory=list,
        description="Files skipped because they are stored with the same SHA-256.",
    )
