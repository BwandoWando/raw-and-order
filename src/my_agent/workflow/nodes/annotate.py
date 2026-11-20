"""Node: annotate previews with the LLM."""

from typing import Any

from my_agent.exceptions import TooManyFailuresError
from my_agent.llm.annotator import Annotator
from my_agent.llm.context import ExifContextFormatter
from my_agent.media.protocols import PreviewStore
from my_agent.workflow.nodes._per_item import apply_step
from my_agent.workflow.state import PhotoItem, Stage, WorkflowState


class AnnotateNode:
    """Sends each preview (plus optional EXIF context) to the annotator.

    Args:
        annotator: Produces the annotation.
        preview_store: Loads preview bytes.
        context_formatter: Decides which EXIF fields the model sees.
        max_consecutive_failures: Stop the run after this many annotation
            failures in a row (0 disables the check).
    """

    def __init__(
        self,
        annotator: Annotator,
        preview_store: PreviewStore,
        context_formatter: ExifContextFormatter,
        max_consecutive_failures: int = 0,
    ) -> None:
        self._annotator = annotator
        self._preview_store = preview_store
        self._context_formatter = context_formatter
        self._max_consecutive_failures = max_consecutive_failures

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return ``items`` with ``annotation`` filled in.

        Photos are annotated one at a time so the run stops exactly when the
        failure streak reaches the limit, without further LLM calls.

        Raises:
            TooManyFailuresError: If too many photos in a row failed.
        """
        streak = state.consecutive_annotate_failures
        items: list[PhotoItem] = []
        for item in state.items:
            [done] = apply_step([item], Stage.ANNOTATE, self._annotate)
            items.append(done)
            streak = consecutive_failures(streak, [done])
            if 0 < self._max_consecutive_failures <= streak:
                raise TooManyFailuresError(
                    f"{streak} photos in a row failed annotation; the last error "
                    f"was: {_last_annotate_error(items)}"
                )
        return {"items": items, "consecutive_annotate_failures": streak}

    def _annotate(self, item: PhotoItem) -> PhotoItem:
        if item.preview_path is None:
            raise ValueError(f"No preview for {item.path}; decode must run first")
        image = self._preview_store.load(item.preview_path)
        context = self._context_formatter.format(item.exif)
        annotation = self._annotator.annotate(image, context)
        return item.model_copy(update={"annotation": annotation})


def consecutive_failures(streak: int, items: list[PhotoItem]) -> int:
    """Continue the failure streak over ``items`` (in order).

    An annotation failure extends it, a successful annotation resets it, and
    files that failed an earlier step are neutral.
    """
    for item in items:
        if item.annotation is not None:
            streak = 0
        elif item.error is not None and item.error.stage is Stage.ANNOTATE:
            streak += 1
    return streak


def _last_annotate_error(items: list[PhotoItem]) -> str:
    errors = [i.error for i in items if i.error and i.error.stage is Stage.ANNOTATE]
    return errors[-1].message if errors else "unknown"
