"""Workflow state models."""

from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, Field

from raw_and_order.schemas import Annotation, ExifData, PhotoCopy


class Stage(StrEnum):
    """The workflow step a file failed in.

    Stored as text in ``processing_failures.stage`` and shown on the
    Failures tab, so the values must not change.
    """

    FINGERPRINT = "fingerprint"
    EXTRACT_EXIF = "extract_exif"
    DECODE = "decode"
    PERCEPTUAL_HASH = "perceptual_hash"
    ANNOTATE = "annotate"
    PERSIST = "persist"


class StepFailure(BaseModel):
    """Why a photo failed in a step; recorded on it instead of stopping the batch.

    A plain record, not an exception: the exceptions are in ``exceptions.py``.
    """

    stage: Stage
    error_type: str
    message: str


class PhotoItem(BaseModel):
    """One file moving through the pipeline."""

    path: Path
    sha256: str | None = None
    exif: ExifData | None = None
    preview_path: Path | None = None
    phash: str | None = None
    annotation: Annotation | None = None
    saved: bool = False
    error: StepFailure | None = None

    @property
    def is_ok(self) -> bool:
        """True while no step has failed for this file."""
        return self.error is None


class FailedPhoto(BaseModel):
    """A photo that failed and why, kept for the run summary after its chunk."""

    path: Path
    error: StepFailure


class WorkflowState(BaseModel):
    """State shared by all workflow steps for one run.

    The planning steps (see the order in :mod:`raw_and_order.workflow.runner`)
    work on every candidate in ``items``. ``select_batch`` then moves the
    photos to process into ``queue``, leaving only the early failures in
    ``items`` for ``sync_planning_failures``. The chunk loop then works on one
    chunk at a time in ``items``. Finished chunks are reduced to counts and
    failures so the state stays small.
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
    failures: list[FailedPhoto] = Field(default_factory=list)
    skipped_pairs: list[Path] = Field(
        default_factory=list,
        description="Images skipped because a raw file of the same shot exists.",
    )
    unchanged: list[Path] = Field(
        default_factory=list,
        description="Files skipped because they are stored with the same SHA-256.",
    )
    copies: list[PhotoCopy] = Field(
        default_factory=list,
        description="Files skipped as exact copies of a photo stored elsewhere.",
    )
    previously_failed: list[Path] = Field(
        default_factory=list,
        description="Files skipped because they are logged as failed.",
    )
    missing: list[Path] = Field(
        default_factory=list,
        description="Logged failures whose file no longer exists (log cleared).",
    )


class StateUpdate(TypedDict, total=False):
    """The fields of :class:`WorkflowState` that one step changed.

    Every step returns one; the runner merges it into the next state. Typed
    (instead of ``dict[str, Any]``) so mypy rejects a misspelled field name
    or a value of the wrong type. The run's settings (``source_dir``,
    ``reprocess`` ...) are not here: no step changes them.
    """

    items: list[PhotoItem]
    queue: list[PhotoItem]
    selected: int
    deferred: int
    chunk_index: int
    chunk_total: int
    saved_count: int
    consecutive_annotate_failures: int
    failures: list[FailedPhoto]
    skipped_pairs: list[Path]
    unchanged: list[Path]
    copies: list[PhotoCopy]
    previously_failed: list[Path]
    missing: list[Path]
