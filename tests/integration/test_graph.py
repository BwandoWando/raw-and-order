"""Full pipeline run with fakes for exiftool, rawpy and the LLM."""

import hashlib
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.exceptions import BatchLimitExceededError
from my_agent.graph.builder import PipelineNodes, build_graph
from my_agent.graph.nodes import (
    AnnotateNode,
    BatchLimitNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    PerceptualHashNode,
    PersistNode,
    SkipUnchangedNode,
)
from my_agent.graph.state import Stage
from my_agent.llm.context import ExifContextFormatter
from my_agent.media.discovery import FileSystemDiscoverer
from my_agent.media.hashing import DHasher, Sha256FileHasher
from my_agent.media.pairing import RawPairFilter
from my_agent.media.previews import DatedPreviewLayout, JpegPreviewStore
from my_agent.pipeline import PhotoPipeline
from my_agent.schemas import ExifData
from tests.fakes import FakeAnnotator, FakeExifReader, FakeImageDecoder


def _pipeline(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    exif: ExifData,
    annotator: FakeAnnotator,
    fail_exif_for: tuple[str, ...] = (),
) -> PhotoPipeline:
    previews = JpegPreviewStore(tmp_path / "previews", DatedPreviewLayout(), max_px=32)
    nodes = PipelineNodes(
        discover=DiscoverNode(
            FileSystemDiscoverer({".nef", ".jpg"}), RawPairFilter({".nef"})
        ),
        fingerprint=FingerprintNode(Sha256FileHasher()),
        skip_unchanged=SkipUnchangedNode(repository),
        check_limit=BatchLimitNode(),
        extract_exif=ExtractExifNode(FakeExifReader(exif, fail_for=fail_exif_for)),
        decode=DecodeNode(FakeImageDecoder(), previews),
        perceptual_hash=PerceptualHashNode(DHasher(), previews),
        annotate=AnnotateNode(annotator, previews, ExifContextFormatter()),
        persist=PersistNode(repository, annotated_by="fake:model"),
    )
    return PhotoPipeline(build_graph(nodes, InMemorySaver()), lambda: "run-test")


def _make_photos(root: Path, *names: str) -> Path:
    root.mkdir()
    for name in names:
        (root / name).touch()
    return root


def test_processes_files_and_isolates_failures(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "good.nef", "bad.nef")
    annotator = FakeAnnotator()

    summary = _pipeline(
        tmp_path, repository, sample_exif, annotator, fail_exif_for=("bad.nef",)
    ).run(photos)

    assert (summary.discovered, summary.saved) == (2, 1)
    assert [f.path.name for f in summary.failed] == ["bad.nef"]
    assert summary.failed[0].error.stage is Stage.EXTRACT_EXIF
    assert repository.known_paths() == {photos / "good.nef"}
    assert len(annotator.calls) == 1


def test_second_run_skips_known_files_unless_reprocessing(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    pipeline = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator())

    pipeline.run(photos)

    assert pipeline.run(photos).discovered == 0
    assert pipeline.run(photos, reprocess=True).saved == 1


def test_gps_is_not_sent_to_model_by_default(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    annotator = FakeAnnotator()

    _pipeline(tmp_path, repository, sample_exif, annotator).run(photos)

    _, context = annotator.calls[0]
    assert context is not None
    assert "gps" not in context


def test_raw_wins_over_jpeg_of_same_shot(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "DSC_1.NEF", "dsc_1.jpg", "solo.jpg")

    summary = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(photos)

    assert summary.skipped_pairs == 1
    assert repository.known_paths() == {photos / "DSC_1.NEF", photos / "solo.jpg"}


def test_previews_are_filed_by_capture_date_and_type(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.jpg")

    _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(photos)

    folders = set()
    for name in ("a.nef", "b.jpg"):
        record = repository.get_by_path(photos / name)
        assert record is not None
        assert record.preview_path.is_file()
        folders.add(record.preview_path.parent.relative_to(tmp_path / "previews"))
    assert folders == {Path("20240501/nef"), Path("20240501/jpg")}


def test_stores_sha256_and_dhash(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    (photos / "a.nef").write_bytes(b"raw bytes")

    _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(photos)

    record = repository.get_by_path(photos / "a.nef")
    assert record is not None
    assert record.sha256 == hashlib.sha256(b"raw bytes").hexdigest()
    assert record.dhash is not None
    assert len(record.dhash) == 16


def test_changed_file_is_reprocessed_unchanged_is_skipped(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.nef")
    (photos / "a.nef").write_bytes(b"original")
    (photos / "b.nef").write_bytes(b"other")
    pipeline = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator())
    pipeline.run(photos)

    (photos / "a.nef").write_bytes(b"edited")
    summary = pipeline.run(photos)

    assert (summary.discovered, summary.unchanged, summary.saved) == (1, 1, 1)
    record = repository.get_by_path(photos / "a.nef")
    assert record is not None
    assert record.sha256 == hashlib.sha256(b"edited").hexdigest()


def test_identical_copies_in_two_folders_are_both_stored(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = tmp_path / "in"
    for folder in ("card", "backup"):
        (photos / folder).mkdir(parents=True)
        (photos / folder / "DSC_1.NEF").write_bytes(b"same bytes")

    summary = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(photos)

    assert summary.saved == 2
    fingerprints = set(repository.known_fingerprints().values())
    assert fingerprints == {hashlib.sha256(b"same bytes").hexdigest()}


def test_over_limit_stops_before_any_work(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.nef", "c.nef")
    annotator = FakeAnnotator()

    with pytest.raises(BatchLimitExceededError, match=r"Found 3 photos.*limit of 2"):
        _pipeline(tmp_path, repository, sample_exif, annotator).run(
            photos, max_photos=2
        )

    assert annotator.calls == []
    assert repository.known_paths() == set()
    assert not (tmp_path / "previews").exists()


def test_unchanged_files_do_not_count_towards_limit(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.nef")
    pipeline = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator())
    pipeline.run(photos, max_photos=2)
    (photos / "c.nef").write_bytes(b"new photo")

    summary = pipeline.run(photos, max_photos=1)

    assert (summary.saved, summary.unchanged) == (1, 2)
