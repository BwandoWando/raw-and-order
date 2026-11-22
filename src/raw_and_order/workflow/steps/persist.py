"""Step: save each finished photo to the database."""

from collections.abc import Callable
from datetime import UTC, datetime

from raw_and_order.db.repository import PhotoRepository
from raw_and_order.schemas import PhotoRecord
from raw_and_order.workflow.state import PhotoItem, Stage, StateUpdate, WorkflowState
from raw_and_order.workflow.steps._per_item import apply_step


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


class PersistStep:
    """Upserts each annotated photo, keyed by its path.

    A database error is recorded on that photo (stage ``persist``); the
    other photos are still saved.

    Args:
        repository: Where records are stored.
        annotated_by: Model label saved with each record.
        clock: Returns the current time; injectable for tests.
    """

    def __init__(
        self,
        repository: PhotoRepository,
        annotated_by: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._annotated_by = annotated_by
        self._clock = clock

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return ``items`` with ``saved`` set to ``True`` for stored photos."""
        return {"items": apply_step(state.items, Stage.PERSIST, self._persist)}

    def _persist(self, item: PhotoItem) -> PhotoItem:
        self._repository.upsert(self._to_record(item))
        return item.model_copy(update={"saved": True})

    def _to_record(self, item: PhotoItem) -> PhotoRecord:
        """Build the stored record; missing fields mean a step-order bug."""
        if item.exif is None or item.annotation is None or item.preview_path is None:
            raise ValueError(f"{item.path} is incomplete; earlier steps must run first")
        return PhotoRecord(
            path=item.path,
            sha256=item.sha256,
            phash=item.phash,
            exif=item.exif,
            annotation=item.annotation,
            preview_path=item.preview_path,
            annotated_by=self._annotated_by,
            processed_at=self._clock(),
        )
