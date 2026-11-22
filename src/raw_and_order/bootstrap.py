"""Composition root: the only place that builds concrete objects.

Everything else receives its dependencies through constructors.
"""

from contextlib import ExitStack
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from raw_and_order.config import LLMProvider, LLMSettings, Settings
from raw_and_order.db.catalog import SqlAlchemyPhotoCatalog
from raw_and_order.db.copy_repository import SqlAlchemyCopyRepository
from raw_and_order.db.failure_repository import SqlAlchemyFailureRepository
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.db.session import create_db_engine, create_session_factory
from raw_and_order.exif_reread import ExifRereader
from raw_and_order.llm.annotator import LLMAnnotator
from raw_and_order.llm.capabilities import (
    DEFAULT_OLLAMA_URL,
    AssumeVisionChecker,
    CapabilityChecker,
    OllamaCapabilityChecker,
)
from raw_and_order.llm.context import ExifContextFormatter
from raw_and_order.llm.factory import create_chat_model
from raw_and_order.llm.prompts import render_prompt
from raw_and_order.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    build_date_sources,
)
from raw_and_order.media.discovery import FileSystemDiscoverer
from raw_and_order.media.exif import PyExifToolReader
from raw_and_order.media.exif_mapping import ExifMapper
from raw_and_order.media.hashing import PHasher, Sha256FileHasher
from raw_and_order.media.heif import enable_heif_support
from raw_and_order.media.pairing import RawPairFilter
from raw_and_order.media.pillow_decoder import PillowDecoder
from raw_and_order.media.previews import DatedPreviewLayout, JpegPreviewStore
from raw_and_order.media.raw import RawpyDecoder
from raw_and_order.media.routing import ExtensionRoutingDecoder
from raw_and_order.media.thumbnails import JpegThumbnailer
from raw_and_order.pipeline import PhotoPipeline
from raw_and_order.rehash import PerceptualRehasher
from raw_and_order.schemas.annotation import annotation_schema
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.workflow.nodes import (
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
from raw_and_order.workflow.runner import PhotoWorkflow, WorkflowSteps

CAPABILITY_CHECK_TIMEOUT_S = 10.0


class Application:
    """Owns long-lived resources and exposes the wired pipeline.

    Use as a context manager so the exiftool process and database engine
    are always closed.

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
    from raw_and_order.ui.cached_library import CachedPhotoLibrary

    session_factory = create_session_factory(create_db_engine(settings.database_url))
    return CachedPhotoLibrary(
        catalog=SqlAlchemyPhotoCatalog(session_factory),
        failures=SqlAlchemyFailureRepository(session_factory),
        thumbnailer=JpegThumbnailer(),
        cache_key=settings.database_url,
    )
