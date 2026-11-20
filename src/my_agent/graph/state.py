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


class FileFailure(BaseModel):
    """A file that failed, kept after its chunk has been recorded."""

    path: Path
    error: FileError


class GraphState(BaseModel):
    """State shared by all nodes for one run.

    Planning steps (discover -> fingerprint -> skip_unchanged -> select_batch)
    work on every candidate in ``items``. ``select_batch`` then moves the
    photos to process into ``queue``, and the chunk loop works on one chunk
    at a time in ``items``. Finished chunks are reduced to counts and
    failures so checkpoints stay small.
    """

    source_dir: Path
    reprocess: bool = False
    reprocess_failed: bool = Field(
        default=False, description="Retry only the logged failures under source_dir."
    )
    max_photos: int | None = Field(
        default=None, description="Photos to process this run; None = all."
    )
    chunk_size: int | None = Field(
        default=None, description="Photos saved per chunk; None = one chunk."
    )
    items: list[PhotoItem] = Field(default_factory=list)
    queue: list[PhotoItem] = Field(default_factory=list)
    selected: int = 0
    deferred: int = Field(default=0, description="Left for a later run.")
    chunk_index: int = 0
    chunk_total: int = 0
    saved_count: int = 0
    consecutive_annotate_failures: int = Field(
        default=0, description="Annotation failures in a row, across chunks."
    )
    failures: list[FileFailure] = Field(default_factory=list)
    skipped_pairs: list[Path] = Field(
        default_factory=list,
        description="Images skipped because a raw file of the same shot exists.",
    )
    unchanged: list[Path] = Field(
        default_factory=list,
        description="Files skipped because they are stored with the same SHA-256.",
    )
    previously_failed: list[Path] = Field(
        default_factory=list,
        description="Files skipped because they are logged as failed.",
    )
    missing: list[Path] = Field(
        default_factory=list,
        description="Logged failures whose file no longer exists (log cleared).",
    )
