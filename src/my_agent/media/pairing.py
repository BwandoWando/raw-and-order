"""Skip images that duplicate a raw file of the same shot (RAW+JPEG pairs)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PairFilterResult:
    """Files to process and files skipped as duplicates of a raw file."""

    kept: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)


def shot_key(path: Path) -> tuple[Path, str]:
    """Identify a shot by folder and case-insensitive file name stem."""
    return path.parent, path.stem.lower()


class RawPairFilter:
    """Drops non-raw images when a raw file of the same shot is in the same folder.

    Raw files are never dropped, so two raw versions of one shot (e.g. CR2
    and a converted DNG) are both kept.

    Args:
        raw_extensions: Lowercase extensions including the dot.
    """

    def __init__(self, raw_extensions: Iterable[str]) -> None:
        self._raw_extensions = frozenset(ext.lower() for ext in raw_extensions)

    def apply(self, paths: Iterable[Path]) -> PairFilterResult:
        """Split ``paths`` into kept and skipped, preserving order."""
        candidates = list(paths)
        raw_shots = {shot_key(p) for p in candidates if self._is_raw(p)}
        result = PairFilterResult()
        for path in candidates:
            is_duplicate = not self._is_raw(path) and shot_key(path) in raw_shots
            (result.skipped if is_duplicate else result.kept).append(path)
        return result

    def _is_raw(self, path: Path) -> bool:
        return path.suffix.lower() in self._raw_extensions
