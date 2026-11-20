"""Node: drop files already stored with the same contents."""

import logging
from pathlib import Path
from typing import Any

from my_agent.db.repository import PhotoRepository
from my_agent.graph.state import GraphState, PhotoItem

logger = logging.getLogger(__name__)


class SkipUnchangedNode:
    """Skips files whose path and SHA-256 match a stored record.

    New files and files whose contents changed are kept. With ``reprocess``
    every file is kept.

    Args:
        repository: Provides the stored fingerprints.
    """

    def __init__(self, repository: PhotoRepository) -> None:
        self._repository = repository

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return the remaining ``items`` and the ``unchanged`` paths."""
        if state.reprocess:
            return {"unchanged": []}
        stored = self._repository.known_fingerprints()
        keep: list[PhotoItem] = []
        unchanged: list[Path] = []
        for item in state.items:
            if _is_unchanged(item, stored):
                unchanged.append(item.path)
            else:
                keep.append(item)
        logger.info("%d file(s) unchanged since last run", len(unchanged))
        return {"items": keep, "unchanged": unchanged}


def _is_unchanged(item: PhotoItem, stored: dict[Path, str | None]) -> bool:
    return item.sha256 is not None and stored.get(item.path) == item.sha256
