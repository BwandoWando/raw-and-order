from datetime import UTC, datetime
from pathlib import Path

from my_agent.db.failure_repository import SqlAlchemyFailureRepository

T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 1, 2, tzinfo=UTC)


def _record(repo: SqlAlchemyFailureRepository, path: str, when: datetime = T1) -> None:
    repo.record(Path(path), "sha", "decode", "ImageDecodeError", "corrupt", when)


def test_record_then_update_increments_attempts(
    failures: SqlAlchemyFailureRepository,
) -> None:
    _record(failures, "/in/a.nef", T1)
    failures.record(
        Path("/in/a.nef"), "sha2", "annotate", "InvalidModelOutputError", "bad", T2
    )

    [record] = failures.failures_under(Path("/in"))
    assert (record.attempts, record.stage, record.sha256) == (2, "annotate", "sha2")
    assert (record.first_failed_at, record.last_failed_at) == (T1, T2)


def test_resolve_removes_entries_and_ignores_unknown(
    failures: SqlAlchemyFailureRepository,
) -> None:
    _record(failures, "/in/a.nef")
    _record(failures, "/in/b.nef")

    failures.resolve([Path("/in/a.nef"), Path("/in/unknown.nef")])
    failures.resolve([])

    assert list(failures.known_failures()) == [Path("/in/b.nef")]


def test_failures_under_filters_by_folder(
    failures: SqlAlchemyFailureRepository,
) -> None:
    for path in ("/in/a.nef", "/in/sub/b.nef", "/other/c.nef", "/input/d.nef"):
        _record(failures, path)

    names = [r.path.as_posix() for r in failures.failures_under(Path("/in"))]

    assert names == ["/in/a.nef", "/in/sub/b.nef"]  # not /input or /other
