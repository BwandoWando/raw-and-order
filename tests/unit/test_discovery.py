from pathlib import Path

import pytest

from my_agent.exceptions import SourceDirectoryError
from my_agent.media.discovery import FileSystemDiscoverer


def test_find_returns_supported_files_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    for name in ("a.NEF", "b.cr3", "sub/c.dng", "notes.txt", "photo.jpg"):
        (tmp_path / name).touch()

    found = FileSystemDiscoverer({".nef", ".cr3", ".dng"}).find(tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in found] == [
        "a.NEF",
        "b.cr3",
        "sub/c.dng",
    ]


def test_find_non_recursive_skips_subdirectories(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.dng").touch()

    assert FileSystemDiscoverer({".dng"}, recursive=False).find(tmp_path) == []


def test_find_raises_for_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(SourceDirectoryError):
        FileSystemDiscoverer({".dng"}).find(tmp_path / "missing")
