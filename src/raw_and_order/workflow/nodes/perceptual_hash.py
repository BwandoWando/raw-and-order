"""Node: compute each photo's perceptual hash from its upright preview."""

from typing import Any

from raw_and_order.media.protocols import PerceptualHasher, PreviewStore
from raw_and_order.workflow.nodes._per_item import apply_step
from raw_and_order.workflow.state import PhotoItem, Stage, WorkflowState


class PerceptualHashNode:
    """Hashes what each photo looks like, using its saved preview.

    The preview is already upright and downscaled, so rotated or resized
    copies of a photo get matching hashes.

    Args:
        hasher: Computes the perceptual hash.
        preview_store: Loads the preview bytes.
    """

    def __init__(self, hasher: PerceptualHasher, preview_store: PreviewStore) -> None:
        self._hasher = hasher
        self._preview_store = preview_store

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return ``items`` with ``phash`` filled in."""
        return {"items": apply_step(state.items, Stage.PERCEPTUAL_HASH, self._hash)}

    def _hash(self, item: PhotoItem) -> PhotoItem:
        if item.preview_path is None:
            raise ValueError(f"No preview for {item.path}; decode must run first")
        data = self._preview_store.load(item.preview_path)
        return item.model_copy(update={"phash": self._hasher.hash_image_bytes(data)})
