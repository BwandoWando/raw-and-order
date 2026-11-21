from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

from my_agent.media.pairing import RawPairFilter

RAW = {".nef", ".cr2", ".dng"}


def _apply(*names: str) -> tuple[list[str], list[str]]:
    result = RawPairFilter(RAW).apply(Path(n) for n in names)
    return [p.as_posix() for p in result.kept], [p.as_posix() for p in result.skipped]


def test_raw_wins_and_jpeg_is_skipped() -> None:
    assert _apply("a/DSC_1.NEF", "a/DSC_1.JPG") == (["a/DSC_1.NEF"], ["a/DSC_1.JPG"])


def test_matching_ignores_case() -> None:
    assert _apply("a/DSC_1.nef", "a/dsc_1.jpg") == (["a/DSC_1.nef"], ["a/dsc_1.jpg"])


def test_jpeg_without_raw_partner_is_kept() -> None:
    assert _apply("a/solo.jpg", "a/other.nef") == (["a/solo.jpg", "a/other.nef"], [])


def test_same_name_in_different_folders_is_not_a_pair() -> None:
    assert _apply("a/DSC_1.NEF", "b/DSC_1.JPG") == (["a/DSC_1.NEF", "b/DSC_1.JPG"], [])


def test_two_raw_versions_are_both_kept() -> None:
    assert _apply("a/IMG.CR2", "a/IMG.dng", "a/IMG.jpg") == (
        ["a/IMG.CR2", "a/IMG.dng"],
        ["a/IMG.jpg"],
    )


T0 = datetime(2026, 5, 1, 18, 30, 0)


def _apply_timed(times: Mapping[str, datetime | None], *names: str) -> list[str]:
    paths = [Path(n) for n in names]
    known = {Path(n): t for n, t in times.items()}
    return [p.as_posix() for p in RawPairFilter(RAW).apply(paths, known).skipped]


def test_pair_within_one_second_is_skipped() -> None:
    times = {"a/DSC_1.NEF": T0, "a/DSC_1.JPG": T0 + timedelta(seconds=1)}

    assert _apply_timed(times, "a/DSC_1.NEF", "a/DSC_1.JPG") == ["a/DSC_1.JPG"]


def test_same_name_but_different_capture_time_is_kept() -> None:
    # e.g. the counter wrapped and an older JPG landed in the same folder
    raw, jpg = Path("a/DSC_1.NEF"), Path("a/DSC_1.JPG")

    result = RawPairFilter(RAW).apply(
        [raw, jpg], {raw: T0, jpg: T0 + timedelta(seconds=2)}
    )

    assert result.skipped == []
    assert result.different_shots == [Path("a/DSC_1.JPG")]


def test_unknown_capture_time_falls_back_to_the_name() -> None:
    times: dict[str, datetime | None] = {"a/DSC_1.NEF": T0, "a/DSC_1.JPG": None}

    assert _apply_timed(times, "a/DSC_1.NEF", "a/DSC_1.JPG") == ["a/DSC_1.JPG"]


def test_any_matching_raw_version_makes_it_a_pair() -> None:
    times = {
        "a/IMG.CR2": T0 - timedelta(days=400),
        "a/IMG.dng": T0,
        "a/IMG.jpg": T0,
    }

    assert _apply_timed(times, "a/IMG.CR2", "a/IMG.dng", "a/IMG.jpg") == ["a/IMG.jpg"]


def test_pair_candidates_are_only_shared_names() -> None:
    names = ["a/DSC_1.NEF", "a/DSC_1.JPG", "a/DSC_2.NEF", "a/solo.jpg", "b/DSC_1.JPG"]

    candidates = RawPairFilter(RAW).pair_candidates(Path(n) for n in names)

    assert [p.as_posix() for p in candidates] == ["a/DSC_1.NEF", "a/DSC_1.JPG"]
