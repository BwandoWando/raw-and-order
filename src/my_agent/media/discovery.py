"""Find raw photo files on disk."""

from collections.abc import Iterable
from pathlib import Path

from my_agent.exceptions import SourceDirectoryError


class FileSystemDiscoverer:
    """Finds files with supported extensions under a directory.

    Args:
        extensions: Lowercase extensions including the dot, e.g. ``{".nef"}``.
        recursive: Whether to search subdirectories.
    """

    def __init__(self, extensions: Iterable[str], recursive: bool = True) -> None:
        self._extensions = frozenset(ext.lower() for ext in extensions)
        self._recursive = recursive

    def find(self, root: Path) -> list[Path]:
        """Return supported files under ``root``, sorted by path.

        Raises:
            SourceDirectoryError: If ``root`` is not an existing directory.
        """
        if not root.is_dir():
            raise SourceDirectoryError(root)
        pattern = "**/*" if self._recursive else "*"
        return sorted(p for p in root.glob(pattern) if self._is_supported(p))

    def _is_supported(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in self._extensions
