"""Composition root: the only place that builds concrete objects.

Everything else receives its dependencies through constructors.
"""

from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from my_agent.config import LLMProvider, LLMSettings, Settings
from my_agent.db.catalog import SqlAlchemyPhotoCatalog
from my_agent.db.copy_repository import SqlAlchemyCopyRepository
from my_agent.db.failure_repository import SqlAlchemyFailureRepository
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.db.session import create_db_engine, create_session_factory
from my_agent.exif_reread import ExifRereader
from my_agent.llm.annotator import LLMAnnotator
from my_agent.llm.capabilities import (
    DEFAULT_OLLAMA_URL,
    AssumeVisionChecker,
    CapabilityChecker,
    OllamaCapabilityChecker,
)
from my_agent.llm.context import ExifContextFormatter
from my_agent.llm.factory import create_chat_model
from my_agent.llm.prompts import render_prompt
from my_agent.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    build_date_sources,
)
from my_agent.media.discovery import FileSystemDiscoverer
from my_agent.media.exif import PyExifToolReader
from my_agent.media.exif_mapping import ExifMapper
from my_agent.media.hashing import PHasher, Sha256FileHasher
from my_agent.media.heif import enable_heif_support
from my_agent.media.pairing import RawPairFilter
from my_agent.media.pillow_decoder import PillowDecoder
from my_agent.media.previews import DatedPreviewLayout, JpegPreviewStore
from my_agent.media.raw import RawpyDecoder
from my_agent.media.routing import ExtensionRoutingDecoder
from my_agent.media.thumbnails import JpegThumbnailer
from my_agent.pipeline import PhotoPipeline
from my_agent.rehash import PerceptualRehasher
from my_agent.schemas.annotation import annotation_schema
from my_agent.ui.library import PhotoLibrary
from my_agent.workflow.nodes import (
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
    RecordCopiesNode,
    SelectBatchNode,
    SkipCopiesNode,
    SkipKnownNode,
)
from my_agent.workflow.runner import PhotoWorkflow, WorkflowSteps

CAPABILITY_CHECK_TIMEOUT_S = 10.0


class Application:
    """Owns long-lived resources and exposes the wired pipeline.

    Use as a context manager so the exiftool process, database engine and
    exiftool process and database engine are always closed.

    Args:
        settings: Validated application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = ExitStack()
        self.pipeline: PhotoPipeline | None = None

    def __enter__(self) -> Self:
        try:
            self.pipeline = PhotoPipeline(self._build_workflow())
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stack.close()

    def _build_workflow(self) -> PhotoWorkflow:
        s = self._settings
        engine = create_db_engine(s.database_url)
        self._stack.callback(engine.dispose)
        session_factory = create_session_factory(engine)
        repository = SqlAlchemyPhotoRepository(session_factory)
        failures = SqlAlchemyFailureRepository(session_factory)
        date_resolver = CaptureDateResolver(
            build_date_sources(s.date_sources), DateValidator()
        )
        exif_reader = self._stack.enter_context(
            PyExifToolReader(ExifMapper(date_resolver))
        )
        preview_store = JpegPreviewStore(
            s.preview_dir, DatedPreviewLayout(), s.preview_max_px, s.preview_quality
        )
        enable_heif_support()
        decoder = ExtensionRoutingDecoder(
            RawpyDecoder(), PillowDecoder(), s.raw_extensions
        )
        discoverer = FileSystemDiscoverer(s.raw_extensions | s.image_extensions)
        steps = WorkflowSteps(
            discover=DiscoverNode(
                discoverer, RawPairFilter(s.raw_extensions), exif_reader
            ),
            load_failures=LoadFailuresNode(failures),
            fingerprint=FingerprintNode(Sha256FileHasher()),
            skip_known=SkipKnownNode(repository, failures),
            skip_copies=SkipCopiesNode(repository, Path.is_file),
            record_copies=RecordCopiesNode(SqlAlchemyCopyRepository(session_factory)),
            select_batch=SelectBatchNode(),
            log_planning_failures=LogFailuresNode(failures),
            next_chunk=NextChunkNode(),
            extract_exif=ExtractExifNode(exif_reader),
            decode=DecodeNode(decoder, preview_store),
            perceptual_hash=PerceptualHashNode(PHasher(), preview_store),
            annotate=AnnotateNode(
                build_annotator(s.llm, s.max_tags),
                preview_store,
                ExifContextFormatter(s.send_exif_to_llm, include_gps=not s.redact_gps),
                max_consecutive_failures=s.max_consecutive_failures,
            ),
            persist=PersistNode(repository, annotated_by=s.llm.label),
            log_failures=LogFailuresNode(failures),
            record_chunk=RecordChunkNode(),
        )
        return PhotoWorkflow(steps)


class ExifRereadApplication:
    """Owns the resources for ``--reread-exif``: database and exiftool only.

    No LLM is built, so no model or API key is needed.

    Args:
        settings: Validated application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = ExitStack()
        self.rereader: ExifRereader | None = None

    def __enter__(self) -> Self:
        try:
            self.rereader = self._build()
        except BaseException:
            self._stack.close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stack.close()

    def _build(self) -> ExifRereader:
        s = self._settings
        engine = create_db_engine(s.database_url)
        self._stack.callback(engine.dispose)
        store = SqlAlchemyPhotoRepository(create_session_factory(engine))
        date_resolver = CaptureDateResolver(
            build_date_sources(s.date_sources), DateValidator()
        )
        reader = self._stack.enter_context(PyExifToolReader(ExifMapper(date_resolver)))
        return ExifRereader(store, reader)


class RehashApplication:
    """Owns the resources for ``raw-and-order rehash``: the database only.

    Hashes come from saved previews, so no exiftool, decoder or LLM is built.

    Args:
        settings: Validated application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = ExitStack()
        self.rehasher: PerceptualRehasher | None = None

    def __enter__(self) -> Self:
        s = self._settings
        engine = create_db_engine(s.database_url)
        self._stack.callback(engine.dispose)
        store = SqlAlchemyPhotoRepository(create_session_factory(engine))
        previews = JpegPreviewStore(
            s.preview_dir, DatedPreviewLayout(), s.preview_max_px, s.preview_quality
        )
        self.rehasher = PerceptualRehasher(store, PHasher(), previews)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stack.close()


def build_annotator(llm: LLMSettings, max_tags: int) -> LLMAnnotator:
    """Create the chat model and wrap it in an :class:`LLMAnnotator`.

    ``max_tags`` sets both the prompt's wording and the schema's limit, so
    the two can never disagree.
    """
    return LLMAnnotator(
        create_chat_model(llm),
        render_prompt("annotate_system", max_tags=max_tags),
        output_schema=annotation_schema(max_tags),
        max_retries=llm.max_retries,
        max_output_fix_attempts=llm.max_output_fix_attempts,
    )


def check_model(llm: LLMSettings) -> None:
    """Fail fast if the configured model is unreachable or cannot see images.

    Raises:
        ConfigurationError: If the model cannot be used.
    """
    if llm.provider is not LLMProvider.OLLAMA:
        _ensure_vision(AssumeVisionChecker(), llm.model)
        return
    base_url = llm.base_url or DEFAULT_OLLAMA_URL
    with httpx.Client(base_url=base_url, timeout=CAPABILITY_CHECK_TIMEOUT_S) as client:
        _ensure_vision(OllamaCapabilityChecker(client), llm.model)


def _ensure_vision(checker: CapabilityChecker, model: str) -> None:
    checker.ensure_vision_support(model)


def build_ui_library(settings: Settings) -> PhotoLibrary:
    """Build the UI's read-only, cached photo library from settings.

    The engine lives as long as the UI process; the UI caches the result.
    Streamlit is imported here, not at module level, so the CLI runs
    without the ``ui`` extra installed.
    """
    from my_agent.ui.cached_library import CachedPhotoLibrary

    session_factory = create_session_factory(create_db_engine(settings.database_url))
    return CachedPhotoLibrary(
        catalog=SqlAlchemyPhotoCatalog(session_factory),
        failures=SqlAlchemyFailureRepository(session_factory),
        thumbnailer=JpegThumbnailer(),
        cache_key=settings.database_url,
    )
