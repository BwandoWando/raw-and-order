"""Skip images that duplicate a raw file of the same shot (RAW+JPEG pairs).

A raw file and an image are the same shot when they sit in the same folder,
share a file name stem (case-insensitive) and were captured within
:data:`PAIR_MAX_TIME_DIFFERENCE` of each other. Cameras reuse file names
(e.g. a Sony counter wraps from DSC09999 to DSC00001), so the capture time
tells a real pair from two different shots with the same name. If either
file has no capture time, the name alone decides.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

PAIR_MAX_TIME_DIFFERENCE = timedelta(seconds=1)

CaptureTimes = Mapping[Path, datetime | None]


@dataclass(frozen=True)
class PairFilterResult:
    """Files to process, files skipped as pairs, and same-name non-pairs."""

    kept: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    # Images kept although a raw file has their name: other capture time.
    different_shots: list[Path] = field(default_factory=list)


def shot_key(path: Path) -> tuple[Path, str]:
    """Identify a shot by folder and case-insensitive file name stem."""
    return path.parent, path.stem.lower()


def same_shot(raw_time: datetime | None, image_time: datetime | None) -> bool:
    """True unless both times are known and further apart than the limit."""
    if raw_time is None or image_time is None:
        return True
    return abs(raw_time - image_time) <= PAIR_MAX_TIME_DIFFERENCE


class RawPairFilter:
    """Drops non-raw images that pair with a raw file in the same folder.

    Raw files are never dropped, so two raw versions of one shot (e.g. CR2
    and a converted DNG) are both kept.

    Args:
        raw_extensions: Lowercase extensions including the dot.
    """

    def __init__(self, raw_extensions: Iterable[str]) -> None:
        self._raw_extensions = frozenset(ext.lower() for ext in raw_extensions)

    def pair_candidates(self, paths: Iterable[Path]) -> list[Path]:
        """Files whose folder and stem are shared by a raw file and an image."""
        candidates = list(paths)
        raw_keys = {shot_key(p) for p in candidates if self._is_raw(p)}
        image_keys = {shot_key(p) for p in candidates if not self._is_raw(p)}
        shared = raw_keys & image_keys
        return [p for p in candidates if shot_key(p) in shared]

    def apply(
        self, paths: Iterable[Path], capture_times: CaptureTimes | None = None
    ) -> PairFilterResult:
        """Split ``paths`` into kept and skipped, preserving order.

        Args:
            paths: Candidate files.
            capture_times: Capture time per file; missing entries count as
                unknown, so only the name decides for them.
        """
        candidates = list(paths)
        times = capture_times or {}
        raws: dict[tuple[Path, str], list[Path]] = {}
        for path in candidates:
            if self._is_raw(path):
                raws.setdefault(shot_key(path), []).append(path)
        result = PairFilterResult()
        for path in candidates:
            partners = [] if self._is_raw(path) else raws.get(shot_key(path), [])
            if any(same_shot(times.get(raw), times.get(path)) for raw in partners):
                result.skipped.append(path)
                continue
            result.kept.append(path)
            if partners:
                result.different_shots.append(path)
        return result

    def _is_raw(self, path: Path) -> bool:
        return path.suffix.lower() in self._raw_extensions
