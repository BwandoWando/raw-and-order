"""The state passed from step to step, and the per-photo records it holds."""

from enum import StrEnum
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, Field

from raw_and_order.schemas import Annotation, ExifData, PhotoCopy


class Stage(StrEnum):
    """The workflow step a file failed in.

    Only the per-photo steps that can fail a single file have a stage. Stored
    as text in ``processing_failures.stage`` and shown on the
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
    """One file moving through the pipeline.

    The steps fill the fields in order: ``sha256`` (fingerprint), ``exif``
    (extract_exif), ``preview_path`` (decode), ``phash`` (perceptual_hash),
    ``annotation`` (annotate) and ``saved`` (persist). Once ``error`` is set,
    later steps leave the item unchanged, so the fields after the failing
    step stay ``None``.
    """

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
    """A photo that failed and why, kept for the run summary.

    Built by ``select_batch`` (early failures) and ``tally_chunk`` (chunk
    failures), after which the photo itself leaves ``items``.
    """

    path: Path
    error: StepFailure


class WorkflowState(BaseModel):
    """State shared by all workflow steps for one run.

    The step order and what each step writes are listed in
    :mod:`raw_and_order.workflow.runner`. ``items`` changes meaning over the
    run:

    1. Planning: every candidate file; ``skip_known`` and ``skip_copies``
       remove the ones that need no work (listed in ``unchanged``,
       ``previously_failed`` and ``copies``).
    2. ``select_batch`` moves the photos to process into ``queue`` and
       leaves only the early failures in ``items``, for
       ``sync_planning_failures`` to log.
    3. Chunk loop: ``next_chunk`` moves the next chunk from ``queue`` into
       ``items``; ``tally_chunk`` adds it to ``saved_count`` and ``failures``
       and empties ``items``, so the state stays small.

    The first five fields are the run's settings and no step changes them.
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
    items: list[PhotoItem] = Field(default_factory=list)  # what the step works on
    queue: list[PhotoItem] = Field(default_factory=list)  # not yet in a chunk
    selected: int = 0  # photos queued by select_batch for this run
    deferred: int = Field(default=0, description="Left for a later run.")
    chunk_index: int = 0  # 1-based number of the current chunk
    chunk_total: int = 0
    saved_count: int = 0  # photos saved in finished chunks
    consecutive_annotate_failures: int = Field(
        default=0, description="Annotation failures in a row, across chunks."
    )
    failures: list[FailedPhoto] = Field(default_factory=list)  # all, for the summary
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
