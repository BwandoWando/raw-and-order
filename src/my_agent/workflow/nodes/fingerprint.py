"""Node: compute each file's SHA-256 fingerprint."""

from typing import Any

from my_agent.media.protocols import FileHasher
from my_agent.workflow.nodes._per_item import apply_step
from my_agent.workflow.state import PhotoItem, Stage, WorkflowState


class FingerprintNode:
    """Hashes each file's bytes.

    Args:
        hasher: Computes the file hash.
    """

    def __init__(self, hasher: FileHasher) -> None:
        self._hasher = hasher

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return ``items`` with ``sha256`` filled in."""
        return {"items": apply_step(state.items, Stage.FINGERPRINT, self._hash)}

    def _hash(self, item: PhotoItem) -> PhotoItem:
        return item.model_copy(update={"sha256": self._hasher.hash_file(item.path)})
