"""Step: decode raw or regular image files and save previews."""

from raw_and_order.media.protocols import ImageDecoder, PreviewStore
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_step


class DecodeStep:
    """Decodes each file and stores a downscaled JPEG preview.

    Args:
        decoder: Turns a raw or image file into an image.
        preview_store: Saves the preview to disk.
    """

    def __init__(self, decoder: ImageDecoder, preview_store: PreviewStore) -> None:
        self._decoder = decoder
        self._preview_store = preview_store

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``preview_path`` filled in.

        The EXIF capture time, when known, decides where the preview is
        stored (see :class:`PreviewLayout`).
        """
        return {"items": apply_step(state.items, Stage.DECODE, self._decode)}

    def _decode(self, item: PhotoItem) -> PhotoItem:
        image = self._decoder.decode(item.path)
        captured_at = item.exif.captured_at if item.exif else None
        preview_path = self._preview_store.save(image, item.path, captured_at)
        return item.model_copy(update={"preview_path": preview_path})
