from pathlib import Path

import pytest

from my_agent.workflow.nodes import SkipKnownNode
from my_agent.workflow.state import PhotoItem, WorkflowState


class StubPhotos:
    def __init__(self, fingerprints: dict[Path, str | None]) -> None:
        self._fingerprints = fingerprints

    def known_fingerprints(self) -> dict[Path, str | None]:
        return self._fingerprints


class StubFailures:
    def __init__(self, failures: dict[Path, str | None]) -> None:
        self._failures = failures

    def known_failures(self) -> dict[Path, str | None]:
        return self._failures


STORED: dict[Path, str | None] = {
    Path("/in/same.nef"): "aaa",
    Path("/in/edited.nef"): "old",
    Path("/in/legacy.nef"): None,  # stored before fingerprints existed
}
FAILED: dict[Path, str | None] = {
    Path("/in/still_bad.nef"): "bbb",
    Path("/in/fixed.nef"): "was_bad",  # contents changed since it failed
    Path("/in/unhashable.nef"): None,  # failed at the fingerprint step
}


def _node() -> SkipKnownNode:
    return SkipKnownNode(StubPhotos(STORED), StubFailures(FAILED))  # type: ignore[arg-type]


def _state(**flags: bool) -> WorkflowState:
    names = {
        "same": "aaa",
        "edited": "new",
        "new": "ccc",
        "legacy": "ddd",
        "still_bad": "bbb",
        "fixed": "now_good",
        "unhashable": None,
    }
    items = [
        PhotoItem(path=Path(f"/in/{n}.nef"), sha256=sha) for n, sha in names.items()
    ]
    return WorkflowState(source_dir=Path("/in"), items=items, **flags)


def test_skips_unchanged_photos_and_known_failures() -> None:
    update = _node()(_state())

    assert [i.path.stem for i in update["items"]] == [
        "edited",
        "new",
        "legacy",
        "fixed",
    ]
    assert update["unchanged"] == [Path("/in/same.nef")]
    assert update["previously_failed"] == [
        Path("/in/still_bad.nef"),
        Path("/in/unhashable.nef"),
    ]


@pytest.mark.parametrize("flag", ["reprocess", "reprocess_failed"])
def test_reprocess_modes_skip_nothing(flag: str) -> None:
    update = _node()(_state(**{flag: True}))

    assert "items" not in update
    assert (update["unchanged"], update["previously_failed"]) == ([], [])
