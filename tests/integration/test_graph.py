"""Full pipeline run with fakes for exiftool, rawpy and the LLM."""

import hashlib
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.graph.builder import PipelineNodes, build_graph
from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    NextChunkNode,
    PerceptualHashNode,
    PersistNode,
    RecordChunkNode,
    SelectBatchNode,
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
        select_batch=SelectBatchNode(),
        next_chunk=NextChunkNode(),
        extract_exif=ExtractExifNode(FakeExifReader(exif, fail_for=fail_exif_for)),
        decode=DecodeNode(FakeImageDecoder(), previews),
        perceptual_hash=PerceptualHashNode(DHasher(), previews),
        annotate=AnnotateNode(annotator, previews, ExifContextFormatter()),
        persist=PersistNode(repository, annotated_by="fake:model"),
        record_chunk=RecordChunkNode(),
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

    assert (summary.selected, summary.saved) == (2, 1)
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

    assert pipeline.run(photos).selected == 0
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

    assert (summary.selected, summary.unchanged, summary.saved) == (1, 1, 1)
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


def _names(repository: SqlAlchemyPhotoRepository) -> list[str]:
    return sorted(path.name for path in repository.known_paths())


def _make_distinct(root: Path, *names: str) -> Path:
    """Photos with different contents (so each has its own SHA-256)."""
    root.mkdir()
    for name in names:
        (root / name).write_bytes(name.encode())
    return root


# --- max photos: take the first X, defer the rest ------------------------------


def test_takes_first_photos_by_path_and_defers_the_rest(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(7)))
    pipeline = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator())

    first = pipeline.run(photos, max_photos=3)
    assert (first.selected, first.saved, first.deferred) == (3, 3, 4)
    assert _names(repository) == ["p0.nef", "p1.nef", "p2.nef"]

    second = pipeline.run(photos, max_photos=3)
    assert (second.selected, second.unchanged, second.deferred) == (3, 3, 1)
    assert _names(repository)[-1] == "p5.nef"

    third = pipeline.run(photos, max_photos=3)
    assert (third.selected, third.deferred) == (1, 0)
    assert len(_names(repository)) == 7


def test_unchanged_files_use_no_slots(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", "a.nef", "b.nef")
    pipeline = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator())
    pipeline.run(photos)
    (photos / "c.nef").write_bytes(b"new photo")

    summary = pipeline.run(photos, max_photos=1)

    assert (summary.selected, summary.saved, summary.unchanged) == (1, 1, 2)
    assert summary.deferred == 0


# --- chunks --------------------------------------------------------------------


def test_processes_in_chunks(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(5)))
    annotator = FakeAnnotator()

    summary = _pipeline(tmp_path, repository, sample_exif, annotator).run(
        photos, chunk_size=2
    )

    assert (summary.chunks, summary.saved, summary.failed) == (3, 5, [])
    assert len(annotator.calls) == 5


def test_chunk_where_every_photo_fails_does_not_stop_the_run(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", "a.nef", "b.nef", "c.nef", "d.nef")

    summary = _pipeline(
        tmp_path,
        repository,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("a.nef", "b.nef"),
    ).run(photos, chunk_size=2)

    assert (summary.chunks, summary.saved) == (2, 2)
    assert sorted(f.path.name for f in summary.failed) == ["a.nef", "b.nef"]
    assert _names(repository) == ["c.nef", "d.nef"]


def test_interrupted_run_keeps_finished_chunks_and_rerun_continues(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(5)))
    crashing = FakeAnnotator(crash_on_call=3)  # dies during chunk 2

    with pytest.raises(RuntimeError, match="simulated crash"):
        _pipeline(tmp_path, repository, sample_exif, crashing).run(photos, chunk_size=2)
    assert _names(repository) == ["p0.nef", "p1.nef"]  # chunk 1 was saved

    annotator = FakeAnnotator()
    summary = _pipeline(tmp_path, repository, sample_exif, annotator).run(
        photos, chunk_size=2
    )
    assert (summary.unchanged, summary.selected, summary.saved) == (2, 3, 3)
    assert len(annotator.calls) == 3
    assert len(_names(repository)) == 5


def test_many_chunks_do_not_hit_langgraph_recursion_limit(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i:02}.nef" for i in range(60)))

    summary = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(
        photos, max_photos=60, chunk_size=1
    )

    assert (summary.chunks, summary.saved) == (60, 60)


def test_empty_folder_finishes_cleanly(
    tmp_path: Path, repository: SqlAlchemyPhotoRepository, sample_exif: ExifData
) -> None:
    (tmp_path / "in").mkdir()

    summary = _pipeline(tmp_path, repository, sample_exif, FakeAnnotator()).run(
        tmp_path / "in", chunk_size=2
    )

    assert (summary.selected, summary.chunks, summary.saved) == (0, 0, 0)
