"""Node: find files to process."""

import logging
from typing import Any

from my_agent.media.pairing import RawPairFilter
from my_agent.media.protocols import PhotoDiscoverer
from my_agent.workflow.state import PhotoItem, WorkflowState

logger = logging.getLogger(__name__)


class DiscoverNode:
    """Lists photo files and resolves RAW+JPEG pairs.

    Files already stored are dropped later by ``skip_unchanged``, after they
    have been fingerprinted, so edited files are picked up again.

    Args:
        discoverer: Finds candidate files.
        pair_filter: Skips images that duplicate a raw file.
    """

    def __init__(self, discoverer: PhotoDiscoverer, pair_filter: RawPairFilter) -> None:
        self._discoverer = discoverer
        self._pair_filter = pair_filter

    def __call__(self, state: WorkflowState) -> dict[str, Any]:
        """Return the candidate ``items`` and the skipped pairs."""
        pairs = self._pair_filter.apply(self._discoverer.find(state.source_dir))
        logger.info(
            "Found %d file(s) in %s (%d skipped as RAW+JPEG pairs)",
            len(pairs.kept),
            state.source_dir,
            len(pairs.skipped),
        )
        return {
            "items": [PhotoItem(path=path) for path in pairs.kept],
            "skipped_pairs": pairs.skipped,
        }
