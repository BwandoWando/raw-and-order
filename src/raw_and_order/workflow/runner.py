"""Run the workflow steps in a fixed order.

```
discover (or load_failures for --reprocess-failed)
  -> fingerprint -> skip_known -> skip_copies -> record_copies
  -> select_batch -> log_planning_failures
  -> while photos are queued:
       next_chunk -> extract_exif -> decode -> perceptual_hash -> annotate -> persist
       (stop the chunk's remaining steps early if every photo in it failed)
       -> log_failures -> record_chunk
```

Each step receives the current :class:`WorkflowState` and returns the fields
it changed; the runner merges them into the next state.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from raw_and_order.exceptions import FatalRunError, RunAbortedError
from raw_and_order.workflow.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    LoadFailuresNode,
    LogFailuresNode,
    NextChunkNode,
    PerceptualHashNode,
    PersistNode,
    RecordChunkNode,
    RecordCopiesNode,
    SelectBatchNode,
    SkipCopiesNode,
    SkipKnownNode,
)
from raw_and_order.workflow.routing import has_pending_items, has_queued_photos
from raw_and_order.workflow.state import WorkflowState

Step = Callable[[WorkflowState], Mapping[str, Any]]


@dataclass(frozen=True)
class WorkflowSteps:
    """All steps the workflow needs, already built with their dependencies."""

    discover: DiscoverNode
    load_failures: LoadFailuresNode
    fingerprint: FingerprintNode
    skip_known: SkipKnownNode
    skip_copies: SkipCopiesNode
    record_copies: RecordCopiesNode
    select_batch: SelectBatchNode
    log_planning_failures: LogFailuresNode
    next_chunk: NextChunkNode
    extract_exif: ExtractExifNode
    decode: DecodeNode
    perceptual_hash: PerceptualHashNode
    annotate: AnnotateNode
    persist: PersistNode
    log_failures: LogFailuresNode
    record_chunk: RecordChunkNode


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
            s.record_copies,
            s.select_batch,
            s.log_planning_failures,
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
        state = apply(state, s.log_failures)
        return apply(state, s.record_chunk)
