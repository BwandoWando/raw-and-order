from datetime import UTC, datetime
from pathlib import Path

from raw_and_order.db.copy_repository import SqlAlchemyCopyRepository
from raw_and_order.schemas import PhotoCopy
from raw_and_order.workflow.state import PhotoItem, WorkflowState
from raw_and_order.workflow.steps import SyncCopyLogStep

WHEN = datetime(2026, 11, 21, tzinfo=UTC)


def _copy(path: str, original: str = "/in/a/x.arw") -> PhotoCopy:
    return PhotoCopy(path=Path(path), sha256="aaa", original=Path(original))


def test_record_inserts_then_updates(copies: SqlAlchemyCopyRepository) -> None:
    copies.record([_copy("/in/b/x.arw")], WHEN)
    copies.record([_copy("/in/b/x.arw", original="/in/c/x.arw")], WHEN)

    assert copies.copies_under(Path("/in")) == [Path("/in/b/x.arw")]


def test_remove_and_folder_scope(copies: SqlAlchemyCopyRepository) -> None:
    copies.record([_copy("/in/b/x.arw"), _copy("/other/x.arw")], WHEN)

    copies.remove([Path("/in/b/x.arw"), Path("/never/logged.arw")])

    assert copies.copies_under(Path("/in")) == []
    assert copies.copies_under(Path("/other")) == [Path("/other/x.arw")]


def test_full_scan_forgets_copies_not_found_again(
    copies: SqlAlchemyCopyRepository,
) -> None:
    copies.record([_copy("/in/gone.arw"), _copy("/in/still.arw")], WHEN)
    node = SyncCopyLogStep(copies, clock=lambda: WHEN)

    node(WorkflowState(source_dir=Path("/in"), copies=[_copy("/in/still.arw")]))

    assert copies.copies_under(Path("/in")) == [Path("/in/still.arw")]


def test_reprocess_failed_only_clears_the_retried_files(
    copies: SqlAlchemyCopyRepository,
) -> None:
    copies.record([_copy("/in/other.arw"), _copy("/in/retried.arw")], WHEN)
    node = SyncCopyLogStep(copies, clock=lambda: WHEN)
    state = WorkflowState(
        source_dir=Path("/in"),
        reprocess_failed=True,
        items=[PhotoItem(path=Path("/in/retried.arw"))],
    )

    node(state)

    assert copies.copies_under(Path("/in")) == [Path("/in/other.arw")]
