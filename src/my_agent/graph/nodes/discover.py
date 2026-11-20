"""Node: find files to process."""

import logging
from typing import Any

from my_agent.db.repository import PhotoRepository
from my_agent.graph.state import GraphState, PhotoItem
from my_agent.media.pairing import RawPairFilter
from my_agent.media.protocols import PhotoDiscoverer

logger = logging.getLogger(__name__)


class DiscoverNode:
    """Lists photo files to process for this run.

    Order matters: RAW+JPEG pairs are resolved before already-stored files
    are dropped, so a JPEG stays skipped even if its raw partner was saved in
    an earlier run.

    Args:
        discoverer: Finds candidate files.
        pair_filter: Skips images that duplicate a raw file.
        repository: Used to skip files that were already processed.
    """

    def __init__(
        self,
        discoverer: PhotoDiscoverer,
        pair_filter: RawPairFilter,
        repository: PhotoRepository,
    ) -> None:
        self._discoverer = discoverer
        self._pair_filter = pair_filter
        self._repository = repository

    def __call__(self, state: GraphState) -> dict[str, Any]:
        """Return the ``items`` to process and the skipped pairs."""
        pairs = self._pair_filter.apply(self._discoverer.find(state.source_dir))
        paths = pairs.kept
        if not state.reprocess:
            known = self._repository.known_paths()
            paths = [path for path in paths if path not in known]
        logger.info(
            "Found %d file(s) to process in %s (%d skipped as RAW+JPEG pairs)",
            len(paths),
            state.source_dir,
            len(pairs.skipped),
        )
        return {
            "items": [PhotoItem(path=path) for path in paths],
            "skipped_pairs": pairs.skipped,
        }
