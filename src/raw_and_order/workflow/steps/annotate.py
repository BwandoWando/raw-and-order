"""Step: annotate previews with the LLM, stopping the run on a failure streak."""

from raw_and_order.exceptions import TooManyFailuresError
from raw_and_order.llm.annotator import Annotator
from raw_and_order.llm.context import ExifContextFormatter
from raw_and_order.media.protocols import PreviewStore
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_to_photo


class AnnotateStep:
    """Sends each preview (plus optional EXIF context) to the annotator.

    Every annotation-stage failure (invalid output, an image the model
    rejected) adds to a streak that carries over between chunks; an outage
    (:class:`ModelUnavailableError`) is not counted but stops the run at once.

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

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``annotation`` and the updated streak.

        Reads each photo's ``preview_path`` and ``exif``. Photos are annotated
        one at a time so the run stops as soon as the failure streak reaches
        the limit, without further LLM calls.

        Raises:
            TooManyFailuresError: If ``max_consecutive_failures`` photos in a
                row failed annotation.
            ModelUnavailableError: If the LLM cannot be used at all.
        """
        streak = state.consecutive_annotate_failures
        items: list[PhotoItem] = []
        for item in state.items:
            done = apply_to_photo(item, Stage.ANNOTATE, self._annotate)
            items.append(done)
            streak = next_streak(streak, done)
            if self._streak_limit_reached(streak):
                last_error = done.error.message if done.error else "unknown"
                raise TooManyFailuresError(
                    f"{streak} photos in a row failed annotation; the last error "
                    f"was: {last_error}"
                )
        return {"items": items, "consecutive_annotate_failures": streak}

    def _streak_limit_reached(self, streak: int) -> bool:
        """True once ``streak`` reaches the limit; a limit of 0 means never."""
        limit = self._max_consecutive_failures
        return limit > 0 and streak >= limit

    def _annotate(self, item: PhotoItem) -> PhotoItem:
        """Annotate one photo.

        A missing preview is a bug in the step order, so it raises
        ``ValueError``, which is not recorded on the photo but ends the run.
        """
        if item.preview_path is None:
            raise ValueError(f"No preview for {item.path}; decode must run first")
        image = self._preview_store.load(item.preview_path)
        context = self._context_formatter.format(item.exif)
        annotation = self._annotator.annotate(image, context)
        return item.model_copy(update={"annotation": annotation})


def next_streak(streak: int, item: PhotoItem) -> int:
    """The annotation-failure streak after ``item`` (annotated or not).

    A successful annotation resets it to 0, an annotation failure adds 1,
    and a photo that failed an earlier step leaves it as it was.
    """
    if item.annotation is not None:
        return 0
    if item.error is not None and item.error.stage is Stage.ANNOTATE:
        return streak + 1
    return streak
