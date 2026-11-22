"""Step: compute each file's SHA-256 fingerprint."""

from raw_and_order.media.protocols import FileHasher
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_step


class FingerprintStep:
    """Hashes each file's bytes.

    Args:
        hasher: Computes the file hash.
    """

    def __init__(self, hasher: FileHasher) -> None:
        self._hasher = hasher

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``sha256`` filled in."""
        return {"items": apply_step(state.items, Stage.FINGERPRINT, self._hash)}

    def _hash(self, item: PhotoItem) -> PhotoItem:
        return item.model_copy(update={"sha256": self._hasher.hash_file(item.path)})
