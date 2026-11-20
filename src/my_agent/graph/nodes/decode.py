"""Node: decode raw or regular image files and save previews."""

from typing import Any

from my_agent.graph.nodes._per_item import apply_step
from my_agent.graph.state import GraphState, PhotoItem, Stage
from my_agent.media.protocols import ImageDecoder, PreviewStore


class DecodeNode:
    """Decodes each file and stores a downscaled JPEG preview.

    Args:
        decoder: Turns a raw or image file into an image.
        preview_store: Saves the preview to disk.
    """

    def __init__(self, decoder: ImageDecoder, preview_store: PreviewStore) -> None:
        self._decoder = decoder
        self._preview_store = preview_store

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return ``items`` with ``preview_path`` filled in."""
        return {"items": apply_step(state.items, Stage.DECODE, self._decode)}

    def _decode(self, item: PhotoItem) -> PhotoItem:
        image = self._decoder.decode(item.path)
        preview_path = self._preview_store.save(image, item.path)
        return item.model_copy(update={"preview_path": preview_path})
