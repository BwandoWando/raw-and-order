"""Step: compute each photo's perceptual hash from its upright preview."""

from raw_and_order.media.protocols import PerceptualHasher, PreviewStore
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_step


class PerceptualHashStep:
    """Hashes what each photo looks like, using its saved preview.

    The preview is already upright (EXIF orientation applied) and downscaled,
    so copies that differ only in orientation flag or size get matching hashes.

    Args:
        hasher: Computes the perceptual hash.
        preview_store: Loads the preview bytes.
    """

    def __init__(self, hasher: PerceptualHasher, preview_store: PreviewStore) -> None:
        self._hasher = hasher
        self._preview_store = preview_store

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``phash`` filled in."""
        return {"items": apply_step(state.items, Stage.PERCEPTUAL_HASH, self._hash)}

    def _hash(self, item: PhotoItem) -> PhotoItem:
        """Hash one preview; a missing one is a step-order bug (``ValueError``)."""
        if item.preview_path is None:
            raise ValueError(f"No preview for {item.path}; decode must run first")
        data = self._preview_store.load(item.preview_path)
        return item.model_copy(update={"phash": self._hasher.hash_image_bytes(data)})
