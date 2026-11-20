"""Node: find files to process."""

import logging
from typing import Any

from my_agent.db.repository import PhotoRepository
from my_agent.graph.state import GraphState, PhotoItem
from my_agent.media.protocols import PhotoDiscoverer

logger = logging.getLogger(__name__)


class DiscoverNode:
    """Lists photo files, skipping ones already stored unless reprocessing.

    Args:
        discoverer: Finds candidate files.
        repository: Used to skip files that were already processed.
    """

    def __init__(
        self, discoverer: PhotoDiscoverer, repository: PhotoRepository
    ) -> None:
        self._discoverer = discoverer
        self._repository = repository

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return the new ``items`` list for the batch."""
        paths = self._discoverer.find(state.source_dir)
        if not state.reprocess:
            known = self._repository.known_paths()
            paths = [path for path in paths if path not in known]
        logger.info("Found %d file(s) to process in %s", len(paths), state.source_dir)
        return {"items": [PhotoItem(path=path) for path in paths]}
