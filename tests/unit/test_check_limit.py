from pathlib import Path

import pytest

from my_agent.exceptions import BatchLimitExceededError
from my_agent.graph.nodes import BatchLimitNode
from my_agent.graph.state import FileError, GraphState, PhotoItem, Stage


def _state(count: int, max_photos: int | None, failed: int = 0) -> GraphState:
    error = FileError(stage=Stage.FINGERPRINT, error_type="X", message="x")
    items = [PhotoItem(path=Path(f"/in/{i}.nef")) for i in range(count)]
    items += [
        PhotoItem(path=Path(f"/in/bad{i}.nef"), error=error) for i in range(failed)
    ]
    return GraphState(source_dir=Path("/in"), items=items, max_photos=max_photos)


@pytest.mark.parametrize(
    ("count", "limit"), [(0, 1), (499, 500), (500, 500), (10, None)]
)
def test_within_limit_passes(count: int, limit: int | None) -> None:
    assert BatchLimitNode()(_state(count, limit)) == {}


def test_over_limit_raises_with_counts() -> None:
    with pytest.raises(BatchLimitExceededError) as caught:
        BatchLimitNode()(_state(501, 500))

    assert (caught.value.count, caught.value.limit) == (501, 500)
    assert "Nothing was processed" in str(caught.value)


def test_failed_files_are_not_counted() -> None:
    assert BatchLimitNode()(_state(500, 500, failed=3)) == {}
