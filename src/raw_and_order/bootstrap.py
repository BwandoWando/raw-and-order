"""Composition root: the only place that builds concrete objects.

Everything else receives its dependencies through constructors. Each command
gets one ``open_*`` function to use in a ``with`` block: it opens what the
command needs (database, exiftool), builds the object that does the work,
and closes everything again when the block ends.
"""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

import httpx
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.config import LLMProvider, LLMSettings, Settings
from raw_and_order.db.catalog import SqlAlchemyPhotoCatalog
from raw_and_order.db.copy_repository import SqlAlchemyCopyRepository
from raw_and_order.db.failure_repository import SqlAlchemyFailureRepository
from raw_and_order.db.favorite_repository import SqlAlchemyFavoriteRepository
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.db.session import create_db_engine, create_session_factory
from raw_and_order.llm.annotator import LLMAnnotator
from raw_and_order.llm.capabilities import (
    DEFAULT_OLLAMA_URL,
    AssumeVisionChecker,
    OllamaCapabilityChecker,
)
from raw_and_order.llm.context import ExifContextFormatter
from raw_and_order.llm.factory import create_chat_model
from raw_and_order.llm.prompts import render_prompt
from raw_and_order.maintenance.exif_reread import ExifRereader
from raw_and_order.maintenance.rehash import PerceptualRehasher
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
from raw_and_order.schemas.annotation import annotation_schema
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.workflow.runner import PhotoWorkflow, WorkflowSteps
from raw_and_order.workflow.steps import (
    AnnotateStep,
    DecodeStep,
    DiscoverStep,
    ExtractExifStep,
    FingerprintStep,
    LoadFailuresStep,
    LogFailuresStep,
    NextChunkStep,
    PerceptualHashStep,
    PersistStep,
    RecordChunkStep,
    RecordCopiesStep,
    SelectBatchStep,
    SkipCopiesStep,
    SkipKnownStep,
)

CAPABILITY_CHECK_TIMEOUT_S = 10.0


@contextmanager
def open_pipeline(settings: Settings) -> Iterator[PhotoPipeline]:
    """Open the database and exiftool, and give the photo pipeline that uses them.

    Used by ``raw-and-order process``. Everything opened here is closed when
    the ``with`` block ends, also if building the pipeline fails halfway::

        with open_pipeline(settings) as pipeline:
            summary = pipeline.run(source_dir)
    """
    with ExitStack() as resources:
        session_factory = _open_database(resources, settings)
        exif_reader = _start_exiftool(resources, settings)
        yield PhotoPipeline(_build_workflow(settings, session_factory, exif_reader))


@contextmanager
def open_exif_rereader(settings: Settings) -> Iterator[ExifRereader]:
    """Open the database and exiftool for ``process --reread-exif``.

    No LLM is built, so no model or API key is needed.
    """
    with ExitStack() as resources:
        session_factory = _open_database(resources, settings)
        exif_reader = _start_exiftool(resources, settings)
        yield ExifRereader(SqlAlchemyPhotoRepository(session_factory), exif_reader)


@contextmanager
def open_rehasher(settings: Settings) -> Iterator[PerceptualRehasher]:
    """Open the database for ``raw-and-order rehash``.

    Hashes come from the saved previews, so no exiftool, decoder or LLM is
    built.
    """
    with ExitStack() as resources:
        session_factory = _open_database(resources, settings)
        yield PerceptualRehasher(
            SqlAlchemyPhotoRepository(session_factory),
            PHasher(),
            _preview_store(settings),
        )


def _open_database(resources: ExitStack, settings: Settings) -> sessionmaker[Session]:
    """Connect to the database; the connection closes with ``resources``."""
    engine = create_db_engine(settings.database_url)
    resources.callback(engine.dispose)
    return create_session_factory(engine)


def _start_exiftool(resources: ExitStack, settings: Settings) -> PyExifToolReader:
    """Start the exiftool process; it stops with ``resources``."""
    date_resolver = CaptureDateResolver(
        build_date_sources(settings.date_sources), DateValidator()
    )
    return resources.enter_context(PyExifToolReader(ExifMapper(date_resolver)))


def _preview_store(settings: Settings) -> JpegPreviewStore:
    """Where previews are saved and read, sized as configured."""
    return JpegPreviewStore(
        settings.preview_dir,
        DatedPreviewLayout(),
        settings.preview_max_px,
        settings.preview_quality,
    )


def _build_workflow(
    settings: Settings,
    session_factory: sessionmaker[Session],
    exif_reader: PyExifToolReader,
) -> PhotoWorkflow:
    """Wire every workflow step to its collaborators (see workflow/runner.py)."""
    s = settings
    repository = SqlAlchemyPhotoRepository(session_factory)
    failures = SqlAlchemyFailureRepository(session_factory)
    preview_store = _preview_store(s)
    enable_heif_support()
    decoder = ExtensionRoutingDecoder(RawpyDecoder(), PillowDecoder(), s.raw_extensions)
    discoverer = FileSystemDiscoverer(s.raw_extensions | s.image_extensions)
    steps = WorkflowSteps(
        discover=DiscoverStep(discoverer, RawPairFilter(s.raw_extensions), exif_reader),
        load_failures=LoadFailuresStep(failures),
        fingerprint=FingerprintStep(Sha256FileHasher()),
        skip_known=SkipKnownStep(repository, failures),
        skip_copies=SkipCopiesStep(repository, Path.is_file),
        record_copies=RecordCopiesStep(SqlAlchemyCopyRepository(session_factory)),
        select_batch=SelectBatchStep(),
        log_planning_failures=LogFailuresStep(failures),
        next_chunk=NextChunkStep(),
        extract_exif=ExtractExifStep(exif_reader),
        decode=DecodeStep(decoder, preview_store),
        perceptual_hash=PerceptualHashStep(PHasher(), preview_store),
        annotate=AnnotateStep(
            build_annotator(s.llm, s.max_tags),
            preview_store,
            ExifContextFormatter(s.send_exif_to_llm, include_gps=not s.redact_gps),
            max_consecutive_failures=s.max_consecutive_failures,
        ),
        persist=PersistStep(repository, annotated_by=s.llm.label),
        log_failures=LogFailuresStep(failures),
        record_chunk=RecordChunkStep(),
    )
    return PhotoWorkflow(steps)


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
        AssumeVisionChecker().ensure_vision_support(llm.model)
        return
    base_url = llm.base_url or DEFAULT_OLLAMA_URL
    with httpx.Client(base_url=base_url, timeout=CAPABILITY_CHECK_TIMEOUT_S) as client:
        OllamaCapabilityChecker(client).ensure_vision_support(llm.model)


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
        favorites=SqlAlchemyFavoriteRepository(session_factory),
        thumbnailer=JpegThumbnailer(),
        cache_key=settings.database_url,
    )
