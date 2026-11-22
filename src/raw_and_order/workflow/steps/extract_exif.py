"""Step: read EXIF metadata."""

from raw_and_order.media.protocols import ExifReader
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_step


class ExtractExifStep:
    """Reads EXIF for each file.

    Args:
        exif_reader: Reads metadata from a file.
    """

    def __init__(self, exif_reader: ExifReader) -> None:
        self._exif_reader = exif_reader

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``exif`` filled in."""
        return {"items": apply_step(state.items, Stage.EXTRACT_EXIF, self._extract)}

    def _extract(self, item: PhotoItem) -> PhotoItem:
        return item.model_copy(update={"exif": self._exif_reader.read(item.path)})
