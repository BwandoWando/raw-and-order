"""Run the workflow steps in a fixed order.

```
discover (or load_failures for --reprocess-failed)
  -> fingerprint -> skip_known -> skip_copies -> sync_copy_log
  -> select_batch -> sync_planning_failures
  -> while photos are queued:
       next_chunk -> extract_exif -> decode -> perceptual_hash -> annotate -> persist
       (stop the chunk's remaining steps early if every photo in it failed)
       -> sync_failure_log -> tally_chunk
```

Each step receives the current :class:`WorkflowState` and returns the fields
it changed; the runner merges them into the next state.
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
    """Run ``step`` and return the state with its changes merged in."""
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
                the LLM is unavailable); carries the photos saved so far.
        """
        try:
            state = self._plan(state)
            while has_queued_photos(state):
                state = self._process_chunk(state)
        except FatalRunError as exc:
            raise RunAbortedError(exc, saved=state.saved_count) from exc
        return state

    def _plan(self, state: WorkflowState) -> WorkflowState:
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
