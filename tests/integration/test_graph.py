"""Full pipeline run with fakes for exiftool, rawpy and the LLM."""

import hashlib
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from my_agent.db.failure_repository import SqlAlchemyFailureRepository
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.exceptions import (
    ModelRejectedError,
    ModelUnavailableError,
    RunAbortedError,
    TooManyFailuresError,
)
from my_agent.graph.builder import PipelineNodes, build_graph
from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    LoadFailuresNode,
    LogFailuresNode,
    NextChunkNode,
    PerceptualHashNode,
    PersistNode,
    RecordChunkNode,
    SelectBatchNode,
    SkipKnownNode,
)
from my_agent.graph.state import Stage
from my_agent.llm.context import ExifContextFormatter
from my_agent.media.discovery import FileSystemDiscoverer
from my_agent.media.hashing import DHasher
from my_agent.media.pairing import RawPairFilter
from my_agent.media.previews import DatedPreviewLayout, JpegPreviewStore
from my_agent.pipeline import PhotoPipeline
from my_agent.schemas import ExifData
from tests.fakes import FakeAnnotator, FakeExifReader, FakeFileHasher, FakeImageDecoder


def _pipeline(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    exif: ExifData,
    annotator: FakeAnnotator,
    fail_exif_for: tuple[str, ...] = (),
    fail_hash_for: tuple[str, ...] = (),
    max_consecutive_failures: int = 0,
) -> PhotoPipeline:
    previews = JpegPreviewStore(tmp_path / "previews", DatedPreviewLayout(), max_px=32)
    nodes = PipelineNodes(
        discover=DiscoverNode(
            FileSystemDiscoverer({".nef", ".jpg"}), RawPairFilter({".nef"})
        ),
        load_failures=LoadFailuresNode(failures),
        fingerprint=FingerprintNode(FakeFileHasher(fail_for=fail_hash_for)),
        skip_known=SkipKnownNode(repository, failures),
        select_batch=SelectBatchNode(),
        log_planning_failures=LogFailuresNode(failures),
        next_chunk=NextChunkNode(),
        extract_exif=ExtractExifNode(FakeExifReader(exif, fail_for=fail_exif_for)),
        decode=DecodeNode(FakeImageDecoder(), previews),
        perceptual_hash=PerceptualHashNode(DHasher(), previews),
        annotate=AnnotateNode(
            annotator,
            previews,
            ExifContextFormatter(),
            max_consecutive_failures=max_consecutive_failures,
        ),
        persist=PersistNode(repository, annotated_by="fake:model"),
        log_failures=LogFailuresNode(failures),
        record_chunk=RecordChunkNode(),
    )
    return PhotoPipeline(build_graph(nodes, InMemorySaver()), lambda: "run-test")


def _make_photos(root: Path, *names: str) -> Path:
    root.mkdir()
    for name in names:
        (root / name).touch()
    return root


def test_processes_files_and_isolates_failures(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "good.nef", "bad.nef")
    annotator = FakeAnnotator()

    summary = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        annotator,
        fail_exif_for=("bad.nef",),
    ).run(photos)

    assert (summary.selected, summary.saved) == (2, 1)
    assert [f.path.name for f in summary.failed] == ["bad.nef"]
    assert summary.failed[0].error.stage is Stage.EXTRACT_EXIF
    assert repository.known_paths() == {photos / "good.nef"}
    assert len(annotator.calls) == 1


def test_second_run_skips_known_files_unless_reprocessing(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    pipeline = _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator())

    pipeline.run(photos)

    assert pipeline.run(photos).selected == 0
    assert pipeline.run(photos, reprocess=True).saved == 1


def test_gps_is_not_sent_to_model_by_default(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    annotator = FakeAnnotator()

    _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(photos)

    _, context = annotator.calls[0]
    assert context is not None
    assert "gps" not in context


def test_raw_wins_over_jpeg_of_same_shot(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "DSC_1.NEF", "dsc_1.jpg", "solo.jpg")

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos)

    assert summary.skipped_pairs == 1
    assert repository.known_paths() == {photos / "DSC_1.NEF", photos / "solo.jpg"}


def test_previews_are_filed_by_capture_date_and_type(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.jpg")

    _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator()).run(photos)

    folders = set()
    for name in ("a.nef", "b.jpg"):
        record = repository.get_by_path(photos / name)
        assert record is not None
        assert record.preview_path.is_file()
        folders.add(record.preview_path.parent.relative_to(tmp_path / "previews"))
    assert folders == {Path("20240501/nef"), Path("20240501/jpg")}


def test_stores_sha256_and_dhash(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef")
    (photos / "a.nef").write_bytes(b"raw bytes")

    _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator()).run(photos)

    record = repository.get_by_path(photos / "a.nef")
    assert record is not None
    assert record.sha256 == hashlib.sha256(b"raw bytes").hexdigest()
    assert record.dhash is not None
    assert len(record.dhash) == 16


def test_changed_file_is_reprocessed_unchanged_is_skipped(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_photos(tmp_path / "in", "a.nef", "b.nef")
    (photos / "a.nef").write_bytes(b"original")
    (photos / "b.nef").write_bytes(b"other")
    pipeline = _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator())
    pipeline.run(photos)

    (photos / "a.nef").write_bytes(b"edited")
    summary = pipeline.run(photos)

    assert (summary.selected, summary.unchanged, summary.saved) == (1, 1, 1)
    record = repository.get_by_path(photos / "a.nef")
    assert record is not None
    assert record.sha256 == hashlib.sha256(b"edited").hexdigest()


def test_identical_copies_in_two_folders_are_both_stored(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = tmp_path / "in"
    for folder in ("card", "backup"):
        (photos / folder).mkdir(parents=True)
        (photos / folder / "DSC_1.NEF").write_bytes(b"same bytes")

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos)

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
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(7)))
    pipeline = _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator())

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
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "a.nef", "b.nef")
    pipeline = _pipeline(tmp_path, repository, failures, sample_exif, FakeAnnotator())
    pipeline.run(photos)
    (photos / "c.nef").write_bytes(b"new photo")

    summary = pipeline.run(photos, max_photos=1)

    assert (summary.selected, summary.saved, summary.unchanged) == (1, 1, 2)
    assert summary.deferred == 0


# --- chunks --------------------------------------------------------------------


def test_processes_in_chunks(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(5)))
    annotator = FakeAnnotator()

    summary = _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
        photos, chunk_size=2
    )

    assert (summary.chunks, summary.saved, summary.failed) == (3, 5, [])
    assert len(annotator.calls) == 5


def test_chunk_where_every_photo_fails_does_not_stop_the_run(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "a.nef", "b.nef", "c.nef", "d.nef")

    summary = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("a.nef", "b.nef"),
    ).run(photos, chunk_size=2)

    assert (summary.chunks, summary.saved) == (2, 2)
    assert sorted(f.path.name for f in summary.failed) == ["a.nef", "b.nef"]
    assert _names(repository) == ["c.nef", "d.nef"]


def test_interrupted_run_keeps_finished_chunks_and_rerun_continues(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(5)))
    crashing = FakeAnnotator(crash_on_call=3)  # dies during chunk 2

    with pytest.raises(RuntimeError, match="simulated crash"):
        _pipeline(tmp_path, repository, failures, sample_exif, crashing).run(
            photos, chunk_size=2
        )
    assert _names(repository) == ["p0.nef", "p1.nef"]  # chunk 1 was saved

    annotator = FakeAnnotator()
    summary = _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
        photos, chunk_size=2
    )
    assert (summary.unchanged, summary.selected, summary.saved) == (2, 3, 3)
    assert len(annotator.calls) == 3
    assert len(_names(repository)) == 5


def test_many_chunks_do_not_hit_langgraph_recursion_limit(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i:02}.nef" for i in range(60)))

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos, max_photos=60, chunk_size=1)

    assert (summary.chunks, summary.saved) == (60, 60)


def test_empty_folder_finishes_cleanly(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    (tmp_path / "in").mkdir()

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(tmp_path / "in", chunk_size=2)

    assert (summary.selected, summary.chunks, summary.saved) == (0, 0, 0)


# --- failure log -----------------------------------------------------------------


def test_failed_photo_is_logged_and_skipped_next_run(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "good.nef", "bad.nef")
    failing = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("bad.nef",),
    )

    failing.run(photos)
    [logged] = failures.failures_under(photos)
    assert (logged.path.name, logged.stage, logged.attempts) == (
        "bad.nef",
        "extract_exif",
        1,
    )
    assert logged.error_type == "ExifReadError"

    annotator = FakeAnnotator()
    summary = _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
        photos
    )
    assert (summary.selected, summary.previously_failed, summary.unchanged) == (0, 1, 1)
    assert annotator.calls == []


def test_reprocess_failed_retries_only_failures_and_clears_them(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "good.nef", "bad.nef")
    _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("bad.nef",),
    ).run(photos)
    (photos / "new.nef").write_bytes(b"brand new")

    annotator = FakeAnnotator()
    summary = _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
        photos, reprocess_failed=True
    )

    assert (summary.selected, summary.saved) == (1, 1)  # only bad.nef, not new.nef
    assert _names(repository) == ["bad.nef", "good.nef"]
    assert failures.failures_under(photos) == []


def test_repeat_failure_increases_attempts(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "bad.nef")
    pipeline = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("bad.nef",),
    )

    pipeline.run(photos)
    pipeline.run(photos, reprocess_failed=True)

    [logged] = failures.failures_under(photos)
    assert logged.attempts == 2
    assert logged.last_failed_at >= logged.first_failed_at


def test_missing_failed_file_is_reported_and_removed_from_log(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "gone.nef", "bad.nef")
    pipeline = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("gone.nef", "bad.nef"),
    )
    pipeline.run(photos)
    (photos / "gone.nef").unlink()

    summary = pipeline.run(photos, reprocess_failed=True)

    assert summary.missing == [photos / "gone.nef"]
    assert summary.selected == 1
    assert [r.path.name for r in failures.failures_under(photos)] == ["bad.nef"]


def test_max_photos_applies_to_retried_failures(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    names = tuple(f"bad{i}.nef" for i in range(5))
    photos = _make_distinct(tmp_path / "in", *names)
    _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=names,
    ).run(photos)

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos, reprocess_failed=True, max_photos=2)

    assert (summary.selected, summary.saved, summary.deferred) == (2, 2, 3)
    assert _names(repository) == ["bad0.nef", "bad1.nef"]
    assert len(failures.failures_under(photos)) == 3


def test_changed_failed_file_is_retried_automatically(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "bad.nef")
    _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("bad.nef",),
    ).run(photos)
    (photos / "bad.nef").write_bytes(b"re-exported")

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos)

    assert (summary.selected, summary.saved, summary.previously_failed) == (1, 1, 0)
    assert failures.failures_under(photos) == []


def test_unhashable_file_is_logged_and_skipped_by_path(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "locked.nef", "ok.nef")
    pipeline = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_hash_for=("locked.nef",),
    )

    first = pipeline.run(photos)
    assert [f.path.name for f in first.failed] == ["locked.nef"]
    [logged] = failures.failures_under(photos)
    assert (logged.stage, logged.sha256) == ("fingerprint", None)

    second = pipeline.run(photos)
    assert (second.previously_failed, second.failed) == (1, [])
    assert failures.failures_under(photos)[0].attempts == 1


def test_reprocess_includes_failures(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "good.nef", "bad.nef")
    _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        FakeAnnotator(),
        fail_exif_for=("bad.nef",),
    ).run(photos)

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos, reprocess=True)

    assert (summary.selected, summary.saved) == (2, 2)
    assert failures.failures_under(photos) == []


# --- stop the run when the model is unavailable ----------------------------------


def test_missing_model_stops_the_run_without_logging_failures(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(5)))
    outage = ModelUnavailableError("model 'gemma3:27b' not found (HTTP 404)")
    annotator = FakeAnnotator(errors={3: outage})  # dies during chunk 2

    with pytest.raises(RunAbortedError) as caught:
        _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
            photos, chunk_size=2
        )

    assert caught.value.saved == 2
    assert caught.value.cause is outage
    assert _names(repository) == ["p0.nef", "p1.nef"]
    assert failures.failures_under(photos) == []  # no photo blamed
    assert len(annotator.calls) == 3  # stopped at once, not 5 calls

    summary = _pipeline(
        tmp_path, repository, failures, sample_exif, FakeAnnotator()
    ).run(photos, chunk_size=2)
    assert (summary.unchanged, summary.saved, summary.failed) == (2, 3, [])


def test_rejected_image_is_logged_and_the_run_continues(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", "a.nef", "b.nef", "c.nef")
    annotator = FakeAnnotator(errors={2: ModelRejectedError("rejected (HTTP 400)")})

    summary = _pipeline(tmp_path, repository, failures, sample_exif, annotator).run(
        photos
    )

    assert summary.saved == 2
    assert [f.path.name for f in summary.failed] == ["b.nef"]
    [logged] = failures.failures_under(photos)
    assert (logged.path.name, logged.error_type) == ("b.nef", "ModelRejectedError")


def test_too_many_failures_in_a_row_stops_the_run(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(6)))
    annotator = FakeAnnotator(always=ModelRejectedError("rejected (HTTP 400)"))

    with pytest.raises(RunAbortedError) as caught:
        _pipeline(
            tmp_path,
            repository,
            failures,
            sample_exif,
            annotator,
            max_consecutive_failures=3,
        ).run(photos, chunk_size=2)

    assert isinstance(caught.value.cause, TooManyFailuresError)
    assert "3 photos in a row" in str(caught.value)
    assert len(annotator.calls) == 3  # stopped at the 3rd failure, mid-chunk
    # chunk 1 finished normally, so its 2 failures were logged; chunk 2 was not
    assert len(failures.failures_under(photos)) == 2


def test_a_success_resets_the_failure_streak(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    failures: SqlAlchemyFailureRepository,
    sample_exif: ExifData,
) -> None:
    photos = _make_distinct(tmp_path / "in", *(f"p{i}.nef" for i in range(6)))
    rejected = ModelRejectedError("rejected")
    annotator = FakeAnnotator(
        errors={1: rejected, 2: rejected, 4: rejected, 5: rejected}
    )

    summary = _pipeline(
        tmp_path,
        repository,
        failures,
        sample_exif,
        annotator,
        max_consecutive_failures=3,
    ).run(photos, chunk_size=2)

    assert (summary.saved, len(summary.failed)) == (2, 4)  # never 3 in a row
