"""Full pipeline run with fakes for exiftool, rawpy and the LLM."""

from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.graph.builder import PipelineNodes, build_graph
from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeRawNode,
    DiscoverNode,
    ExtractExifNode,
    PersistNode,
)
from my_agent.graph.state import Stage
from my_agent.llm.context import ExifContextFormatter
from my_agent.media.discovery import FileSystemDiscoverer
from my_agent.media.previews import JpegPreviewStore
from my_agent.pipeline import PhotoPipeline
from my_agent.schemas import ExifData
from tests.fakes import FakeAnnotator, FakeExifReader, FakeRawDecoder


def _pipeline(
    tmp_path: Path,
    repository: SqlAlchemyPhotoRepository,
    exif: ExifData,
    annotator: FakeAnnotator,
    fail_exif_for: tuple[str, ...] = (),
) -> PhotoPipeline:
    previews = JpegPreviewStore(tmp_path / "previews", max_px=32)
    nodes = PipelineNodes(
        discover=DiscoverNode(FileSystemDiscoverer({".nef"}), repository),
        extract_exif=ExtractExifNode(FakeExifReader(exif, fail_for=fail_exif_for)),
        decode_raw=DecodeRawNode(FakeRawDecoder(), previews),
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
