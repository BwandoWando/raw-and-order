"""Node: save results to the database."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from my_agent.db.repository import PhotoRepository
from my_agent.graph.nodes._per_item import apply_step
from my_agent.graph.state import GraphState, PhotoItem, Stage
from my_agent.schemas import PhotoRecord


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


class PersistNode:
    """Upserts each annotated photo.

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

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return ``items`` with ``saved`` set."""
        return {"items": apply_step(state.items, Stage.PERSIST, self._persist)}

    def _persist(self, item: PhotoItem) -> PhotoItem:
        self._repository.upsert(self._to_record(item))
        return item.model_copy(update={"saved": True})

    def _to_record(self, item: PhotoItem) -> PhotoRecord:
        if item.exif is None or item.annotation is None or item.preview_path is None:
            raise ValueError(f"{item.path} is incomplete; earlier steps must run first")
        return PhotoRecord(
            path=item.path,
            sha256=item.sha256,
            dhash=item.dhash,
            exif=item.exif,
            annotation=item.annotation,
            preview_path=item.preview_path,
            annotated_by=self._annotated_by,
            processed_at=self._clock(),
        )
