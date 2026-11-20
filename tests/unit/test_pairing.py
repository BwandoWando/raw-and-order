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
