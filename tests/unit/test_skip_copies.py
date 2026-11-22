from pathlib import Path

from raw_and_order.workflow.nodes import SkipCopiesNode
from raw_and_order.workflow.state import PhotoItem, WorkflowState


class StubPhotos:
    def __init__(self, fingerprints: dict[Path, str | None]) -> None:
        self._fingerprints = fingerprints

    def known_fingerprints(self) -> dict[Path, str | None]:
        return self._fingerprints


def _run(
    stored: dict[Path, str | None],
    items: list[tuple[str, str | None]],
    on_disk: set[str] | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    def exists(path: Path) -> bool:
        return on_disk is None or path.as_posix() in on_disk

    node = SkipCopiesNode(StubPhotos(stored), exists)
    state = WorkflowState(
        source_dir=Path("/in"),
        items=[PhotoItem(path=Path(p), sha256=sha) for p, sha in items],
    )
    update = node(state)
    kept = [item.path.as_posix() for item in update["items"]]
    copies = [(c.path.as_posix(), c.original.as_posix()) for c in update["copies"]]
    return kept, copies


def test_copy_of_a_stored_photo_in_another_folder_is_skipped() -> None:
    kept, copies = _run({Path("/in/a/x.arw"): "aaa"}, [("/in/b/x.arw", "aaa")])

    assert (kept, copies) == ([], [("/in/b/x.arw", "/in/a/x.arw")])


def test_first_file_in_a_run_is_the_original() -> None:
    kept, copies = _run({}, [("/in/a/1.arw", "aaa"), ("/in/b/2.arw", "aaa")])

    assert kept == ["/in/a/1.arw"]
    assert copies == [("/in/b/2.arw", "/in/a/1.arw")]


def test_reprocessing_the_original_keeps_it() -> None:
    kept, copies = _run({Path("/in/a/x.arw"): "aaa"}, [("/in/a/x.arw", "aaa")])

    assert (kept, copies) == (["/in/a/x.arw"], [])


def test_two_stored_copies_reprocessed_keep_only_the_first_by_path() -> None:
    stored: dict[Path, str | None] = {
        Path("/in/b/x.arw"): "aaa",
        Path("/in/a/x.arw"): "aaa",
    }

    kept, copies = _run(stored, [("/in/a/x.arw", "aaa"), ("/in/b/x.arw", "aaa")])

    assert kept == ["/in/a/x.arw"]
    assert copies == [("/in/b/x.arw", "/in/a/x.arw")]


def test_deleted_original_does_not_count() -> None:
    stored: dict[Path, str | None] = {Path("/in/a/x.arw"): "aaa"}

    kept, copies = _run(stored, [("/in/b/x.arw", "aaa")], on_disk={"/in/b/x.arw"})

    assert (kept, copies) == (["/in/b/x.arw"], [])


def test_different_contents_and_unhashed_files_are_kept() -> None:
    kept, copies = _run(
        {Path("/in/a/x.arw"): "aaa"}, [("/in/b/x.arw", "bbb"), ("/in/c.arw", None)]
    )

    assert (kept, copies) == (["/in/b/x.arw", "/in/c.arw"], [])
