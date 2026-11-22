from pathlib import Path

from raw_and_order.workflow.state import PhotoItem, Stage, StepFailure, WorkflowState
from raw_and_order.workflow.steps import NextChunkStep, SelectBatchStep, TallyChunkStep

ERROR = StepFailure(stage=Stage.FINGERPRINT, error_type="X", message="x")


def _state(
    names: list[str],
    max_photos: int | None,
    chunk_size: int | None = None,
    failed: list[str] | None = None,
) -> WorkflowState:
    items = [PhotoItem(path=Path(f"/in/{n}")) for n in names]
    items += [PhotoItem(path=Path(f"/in/{n}"), error=ERROR) for n in failed or []]
    return WorkflowState(
        source_dir=Path("/in"),
        items=items,
        max_photos=max_photos,
        chunk_size=chunk_size,
    )


def test_selects_first_by_path_and_defers_rest() -> None:
    update = SelectBatchStep()(
        _state(["c.nef", "a.nef", "d.nef", "b.nef"], max_photos=2)
    )

    assert [i.path.name for i in update["queue"]] == ["a.nef", "b.nef"]
    assert (update["selected"], update["deferred"]) == (2, 2)
    assert update["items"] == []


def test_no_limit_selects_everything() -> None:
    update = SelectBatchStep()(_state(["a.nef", "b.nef"], max_photos=None))

    assert (update["selected"], update["deferred"]) == (2, 0)


def test_failed_files_use_no_slot_and_become_failures() -> None:
    update = SelectBatchStep()(_state(["a.nef"], max_photos=1, failed=["bad.nef"]))

    assert [i.path.name for i in update["queue"]] == ["a.nef"]
    assert [f.path.name for f in update["failures"]] == ["bad.nef"]


def test_chunk_total() -> None:
    names = [f"p{i}.nef" for i in range(5)]

    assert SelectBatchStep()(_state(names, None, chunk_size=2))["chunk_total"] == 3
    assert SelectBatchStep()(_state(names, None, chunk_size=None))["chunk_total"] == 1
    assert SelectBatchStep()(_state([], None, chunk_size=2))["chunk_total"] == 0


def test_next_chunk_takes_chunk_size_from_queue() -> None:
    queue = [PhotoItem(path=Path(f"/in/p{i}.nef")) for i in range(5)]
    state = WorkflowState(source_dir=Path("/in"), queue=queue, chunk_size=2)

    update = NextChunkStep()(state)

    assert [i.path.name for i in update["items"]] == ["p0.nef", "p1.nef"]
    assert len(update["queue"]) == 3
    assert update["chunk_index"] == 1


def test_tally_chunk_folds_results_into_totals() -> None:
    items = [
        PhotoItem(path=Path("/in/a.nef"), saved=True),
        PhotoItem(path=Path("/in/b.nef"), error=ERROR),
    ]
    state = WorkflowState(
        source_dir=Path("/in"), items=items, saved_count=10, selected=12
    )

    update = TallyChunkStep()(state)

    assert update["saved_count"] == 11
    assert [f.path.name for f in update["failures"]] == ["b.nef"]
    assert update["items"] == []
