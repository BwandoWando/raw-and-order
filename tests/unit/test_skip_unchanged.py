from pathlib import Path

from my_agent.graph.nodes import SkipUnchangedNode
from my_agent.graph.state import GraphState, PhotoItem


class StubRepository:
    def __init__(self, fingerprints: dict[Path, str | None]) -> None:
        self._fingerprints = fingerprints

    def known_fingerprints(self) -> dict[Path, str | None]:
        return self._fingerprints


def _state(reprocess: bool = False) -> GraphState:
    return GraphState(
        source_dir=Path("/in"),
        reprocess=reprocess,
        items=[
            PhotoItem(path=Path("/in/same.nef"), sha256="aaa"),
            PhotoItem(path=Path("/in/edited.nef"), sha256="new"),
            PhotoItem(path=Path("/in/new.nef"), sha256="ccc"),
            PhotoItem(path=Path("/in/legacy.nef"), sha256="ddd"),
        ],
    )


STORED: dict[Path, str | None] = {
    Path("/in/same.nef"): "aaa",
    Path("/in/edited.nef"): "old",
    Path("/in/legacy.nef"): None,  # stored before fingerprints existed
}


def test_skips_only_files_with_matching_path_and_hash() -> None:
    update = SkipUnchangedNode(StubRepository(STORED))(_state())  # type: ignore[arg-type]

    assert [item.path.name for item in update["items"]] == [
        "edited.nef",
        "new.nef",
        "legacy.nef",
    ]
    assert update["unchanged"] == [Path("/in/same.nef")]


def test_reprocess_keeps_everything() -> None:
    update = SkipUnchangedNode(StubRepository(STORED))(_state(reprocess=True))  # type: ignore[arg-type]

    assert "items" not in update
    assert update["unchanged"] == []
