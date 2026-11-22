"""Step: find the photo files under ``source_dir`` (normal runs)."""

import logging
from datetime import datetime
from pathlib import Path

from raw_and_order.exceptions import ExifReadError
from raw_and_order.media.pairing import RawPairFilter
from raw_and_order.media.protocols import CaptureTimeReader, PhotoDiscoverer
from raw_and_order.workflow.state import PhotoItem, StateUpdate, WorkflowState

logger = logging.getLogger(__name__)


class DiscoverStep:
    """Lists photo files and drops images that duplicate a raw file.

    An image (e.g. a JPEG) is skipped when a raw file in the same folder has
    the same name and, if both are known, a matching capture time. Only files
    that share a folder and name with a file of the other kind have their
    capture time read, so pairs are confirmed cheaply. Files
    already stored are dropped later by ``skip_known``, after they have been
    fingerprinted, so edited files are picked up again.

    Args:
        discoverer: Finds candidate files.
        pair_filter: Skips images that duplicate a raw file.
        times: Reads capture times to confirm pairs.
    """

    def __init__(
        self,
        discoverer: PhotoDiscoverer,
        pair_filter: RawPairFilter,
        times: CaptureTimeReader,
    ) -> None:
        self._discoverer = discoverer
        self._pair_filter = pair_filter
        self._times = times

    def __call__(self, state: WorkflowState) -> StateUpdate:
        """Return the candidate ``items`` and the skipped pairs."""
        paths = self._discoverer.find(state.source_dir)
        candidates = self._pair_filter.pair_candidates(paths)
        pairs = self._pair_filter.apply(paths, self._capture_times(candidates))
        logger.info(
            "Found %d file(s) in %s (%d skipped as RAW+JPEG pairs, %d kept as "
            "different shots with a raw file's name)",
            len(pairs.kept),
            state.source_dir,
            len(pairs.skipped),
            len(pairs.different_shots),
        )
        return {
            "items": [PhotoItem(path=path) for path in pairs.kept],
            "skipped_pairs": pairs.skipped,
        }

    def _capture_times(self, paths: list[Path]) -> dict[Path, datetime | None]:
        """Capture times, or none if exiftool fails (the name then decides)."""
        if not paths:
            return {}
        try:
            return self._times.capture_times(paths)
        except ExifReadError as exc:
            logger.warning("Pairing by file name only: %s", exc)
            return {}
