"""Node: annotate previews with the LLM."""

from typing import Any

from my_agent.graph.nodes._per_item import apply_step
from my_agent.graph.state import GraphState, PhotoItem, Stage
from my_agent.llm.annotator import Annotator
from my_agent.llm.context import ExifContextFormatter
from my_agent.media.protocols import PreviewStore


class AnnotateNode:
    """Sends each preview (plus optional EXIF context) to the annotator.

    Args:
        annotator: Produces the annotation.
        preview_store: Loads preview bytes.
        context_formatter: Decides which EXIF fields the model sees.
    """

    def __init__(
        self,
        annotator: Annotator,
        preview_store: PreviewStore,
        context_formatter: ExifContextFormatter,
    ) -> None:
        self._annotator = annotator
        self._preview_store = preview_store
        self._context_formatter = context_formatter

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return ``items`` with ``annotation`` filled in."""
        return {"items": apply_step(state.items, Stage.ANNOTATE, self._annotate)}

    def _annotate(self, item: PhotoItem) -> PhotoItem:
        if item.preview_path is None:
            raise ValueError(f"No preview for {item.path}; decode_raw must run first")
        image = self._preview_store.load(item.preview_path)
        context = self._context_formatter.format(item.exif)
        annotation = self._annotator.annotate(image, context)
        return item.model_copy(update={"annotation": annotation})
