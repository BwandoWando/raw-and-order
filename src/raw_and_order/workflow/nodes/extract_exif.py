"""Node: read EXIF metadata."""

from typing import Any

from raw_and_order.media.protocols import ExifReader
from raw_and_order.workflow.nodes._per_item import apply_step
from raw_and_order.workflow.state import PhotoItem, Stage, WorkflowState


class ExtractExifNode:
    """Reads EXIF for each file.

    Args:
        exif_reader: Reads metadata from a file.
    """

    def __init__(self, exif_reader: ExifReader) -> None:
        self._exif_reader = exif_reader

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return ``items`` with ``exif`` filled in."""
        return {"items": apply_step(state.items, Stage.EXTRACT_EXIF, self._extract)}

    def _extract(self, item: PhotoItem) -> PhotoItem:
        return item.model_copy(update={"exif": self._exif_reader.read(item.path)})
