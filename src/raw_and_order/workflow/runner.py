"""Run the workflow steps in a fixed order.

```
planning (once per run)
  discover          -> items (photo files, minus skipped pairs), skipped_pairs
    or load_failures  (with --reprocess-failed: items = logged failures, missing)
  fingerprint       -> items[].sha256
  skip_known        -> items minus unchanged / previously_failed (none are
                       skipped with --reprocess or --reprocess-failed)
  skip_copies       -> items minus copies
  sync_copy_log     (writes the copy log only)
  select_batch      -> queue, selected, deferred, chunk_total, failures,
                       chunk_index = 0;
                       items = only the photos that already failed
  sync_planning_failures (writes those early failures to the failure log)

chunk loop (while queue is not empty)
  next_chunk        -> items = next chunk taken from queue, chunk_index
  extract_exif      -> items[].exif
  decode            -> items[].preview_path
  perceptual_hash   -> items[].phash
  annotate          -> items[].annotation, consecutive_annotate_failures
  persist           -> items[].saved (row written to the database)
    (before each of these five steps: if every photo in the chunk has
    failed, skip the rest and go straight to sync_failure_log)
  sync_failure_log  (logs the chunk's failures; clears entries of saved photos)
  tally_chunk       -> saved_count, failures; items = []
```

Each step receives the current :class:`WorkflowState` and returns a
:class:`StateUpdate` with only the fields it changed; :func:`apply` merges it
into the next state. A photo that fails a step keeps going through the list
with ``error`` set, and the later per-photo steps pass it through unchanged.
"""

from collections.abc import Callable
from dataclasses import dataclass

from raw_and_order.exceptions import FatalRunError, RunAbortedError
from raw_and_order.workflow.state import StateUpdate, WorkflowState
from raw_and_order.workflow.steps import (
    AnnotateStep,
    DecodeStep,
    DiscoverStep,
    ExtractExifStep,
    FingerprintStep,
    LoadFailuresStep,
    NextChunkStep,
    PerceptualHashStep,
    PersistStep,
    SelectBatchStep,
    SkipCopiesStep,
    SkipKnownStep,
    SyncCopyLogStep,
    SyncFailureLogStep,
    TallyChunkStep,
)

Step = Callable[[WorkflowState], StateUpdate]


@dataclass(frozen=True)
class WorkflowSteps:
    """All steps the workflow needs, already built with their dependencies."""

    discover: DiscoverStep
    load_failures: LoadFailuresStep
    fingerprint: FingerprintStep
    skip_known: SkipKnownStep
    skip_copies: SkipCopiesStep
    sync_copy_log: SyncCopyLogStep
    select_batch: SelectBatchStep
    sync_planning_failures: SyncFailureLogStep
    next_chunk: NextChunkStep
    extract_exif: ExtractExifStep
    decode: DecodeStep
    perceptual_hash: PerceptualHashStep
    annotate: AnnotateStep
    persist: PersistStep
    sync_failure_log: SyncFailureLogStep
    tally_chunk: TallyChunkStep


def apply(state: WorkflowState, step: Step) -> WorkflowState:
    """Run ``step`` and return the state with its changes merged in.

    ``model_copy(update=...)`` does not re-validate, so the
    :class:`StateUpdate` type check (mypy) is what keeps the values valid.
    """
    return state.model_copy(update=dict(step(state)))


class PhotoWorkflow:
    """Runs the steps in order: planning once, then one chunk at a time.

    Args:
        steps: The configured steps.
    """

    def __init__(self, steps: WorkflowSteps) -> None:
        self._steps = steps

    def run(self, state: WorkflowState) -> WorkflowState:
        """Run the whole workflow and return the final state.

        Raises:
            RunAbortedError: If a step raised a :class:`FatalRunError` (e.g.
                the LLM is unavailable or too many annotations failed in a
                row), which happens in ``annotate``. It carries the
                ``saved_count`` of the chunks finished so far; nothing from the
                interrupted chunk is saved or written to the failure log.
        """
        try:
            state = self._plan(state)
            while has_queued_photos(state):
                state = self._process_chunk(state)
        except FatalRunError as exc:
            raise RunAbortedError(exc, saved=state.saved_count) from exc
        return state

    def _plan(self, state: WorkflowState) -> WorkflowState:
        """Find, filter and queue the photos; log the ones that failed early."""
        s = self._steps
        entry: Step = s.load_failures if state.reprocess_failed else s.discover
        for step in (
            entry,
            s.fingerprint,
            s.skip_known,
            s.skip_copies,
            s.sync_copy_log,
            s.select_batch,
            s.sync_planning_failures,
        ):
            state = apply(state, step)
        return state

    def _process_chunk(self, state: WorkflowState) -> WorkflowState:
        """Process the next chunk from the queue, then log and tally it."""
        s = self._steps
        state = apply(state, s.next_chunk)
        for step in (
            s.extract_exif,
            s.decode,
            s.perceptual_hash,
            s.annotate,
            s.persist,
        ):
            if not has_pending_items(state):
                break  # every photo in this chunk failed; skip to logging
            state = apply(state, step)
        state = apply(state, s.sync_failure_log)
        return apply(state, s.tally_chunk)


def has_queued_photos(state: WorkflowState) -> bool:
    """True if photos are still waiting for a chunk."""
    return bool(state.queue)


def has_pending_items(state: WorkflowState) -> bool:
    """True if at least one photo in the current chunk has not failed."""
    return any(item.is_ok for item in state.items)
