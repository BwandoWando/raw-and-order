from datetime import datetime
from pathlib import Path

from raw_and_order.media.discovery import FileSystemDiscoverer
from raw_and_order.media.pairing import RawPairFilter
from raw_and_order.workflow.nodes import DiscoverNode
from raw_and_order.workflow.state import WorkflowState
from tests.fakes import FakeCaptureTimes

SHOT = datetime(2026, 5, 1, 18, 30, 0)


def _folder(tmp_path: Path, *names: str) -> Path:
    for name in names:
        (tmp_path / name).write_bytes(name.encode())
    return tmp_path


def _discover(root: Path, times: FakeCaptureTimes) -> list[str]:
    node = DiscoverNode(
        FileSystemDiscoverer({".arw", ".jpg"}), RawPairFilter({".arw"}), times
    )
    update = node(WorkflowState(source_dir=root))
    return [item.path.name for item in update["items"]]


def test_reads_capture_times_only_for_pair_candidates(tmp_path: Path) -> None:
    root = _folder(tmp_path, "DSC_1.ARW", "DSC_1.JPG", "DSC_2.ARW", "solo.jpg")
    times = FakeCaptureTimes({"DSC_1.ARW": SHOT, "DSC_1.JPG": SHOT})

    kept = _discover(root, times)

    assert kept == ["DSC_1.ARW", "DSC_2.ARW", "solo.jpg"]
    assert sorted(p.name for p in times.asked) == ["DSC_1.ARW", "DSC_1.JPG"]


def test_different_capture_times_keep_both_files(tmp_path: Path) -> None:
    root = _folder(tmp_path, "DSC_1.ARW", "DSC_1.JPG")
    times = FakeCaptureTimes({"DSC_1.ARW": SHOT, "DSC_1.JPG": SHOT.replace(year=2025)})

    assert _discover(root, times) == ["DSC_1.ARW", "DSC_1.JPG"]


def test_exiftool_failure_falls_back_to_names(tmp_path: Path) -> None:
    root = _folder(tmp_path, "DSC_1.ARW", "DSC_1.JPG")

    assert _discover(root, FakeCaptureTimes(fail=True)) == ["DSC_1.ARW"]


def test_no_candidates_means_no_exiftool_call(tmp_path: Path) -> None:
    times = FakeCaptureTimes()

    _discover(_folder(tmp_path, "a.ARW", "b.jpg"), times)

    assert times.asked == []
