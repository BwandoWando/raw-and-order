"""Composition root: the only place that builds concrete objects.

Everything else receives its dependencies through constructors.
"""

import sqlite3
from contextlib import ExitStack
from types import TracebackType
from typing import Self

import httpx
from langgraph.checkpoint.sqlite import SqliteSaver

from my_agent.config import LLMProvider, LLMSettings, Settings
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.db.session import create_db_engine, create_session_factory
from my_agent.graph.builder import PhotoGraph, PipelineNodes, build_graph
from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    PersistNode,
)
from my_agent.llm.annotator import LLMAnnotator
from my_agent.llm.capabilities import (
    DEFAULT_OLLAMA_URL,
    AssumeVisionChecker,
    CapabilityChecker,
    OllamaCapabilityChecker,
)
from my_agent.llm.context import ExifContextFormatter
from my_agent.llm.factory import create_chat_model
from my_agent.llm.prompts import load_prompt
from my_agent.media.discovery import FileSystemDiscoverer
from my_agent.media.exif import PyExifToolReader
from my_agent.media.heif import enable_heif_support
from my_agent.media.pairing import RawPairFilter
from my_agent.media.pillow_decoder import PillowDecoder
from my_agent.media.previews import DatedPreviewLayout, JpegPreviewStore
from my_agent.media.raw import RawpyDecoder
from my_agent.media.routing import ExtensionRoutingDecoder
from my_agent.pipeline import PhotoPipeline

CAPABILITY_CHECK_TIMEOUT_S = 10.0


class Application:
    """Owns long-lived resources and exposes the wired pipeline.

    Use as a context manager so the exiftool process, database engine and
    checkpoint connection are always closed.

    Args:
        settings: Validated application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._stack = ExitStack()
        self.pipeline: PhotoPipeline | None = None

    def __enter__(self) -> Self:
        try:
            self.pipeline = PhotoPipeline(self._build_graph())
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

    def _build_graph(self) -> PhotoGraph:
        s = self._settings
        engine = create_db_engine(s.database_url)
        self._stack.callback(engine.dispose)
        repository = SqlAlchemyPhotoRepository(create_session_factory(engine))
        exif_reader = self._stack.enter_context(PyExifToolReader())
        preview_store = JpegPreviewStore(
            s.preview_dir, DatedPreviewLayout(), s.preview_max_px, s.preview_quality
        )
        enable_heif_support()
        decoder = ExtensionRoutingDecoder(
            RawpyDecoder(), PillowDecoder(), s.raw_extensions
        )
        discoverer = FileSystemDiscoverer(s.raw_extensions | s.image_extensions)
        nodes = PipelineNodes(
            discover=DiscoverNode(
                discoverer, RawPairFilter(s.raw_extensions), repository
            ),
            extract_exif=ExtractExifNode(exif_reader),
            decode=DecodeNode(decoder, preview_store),
            annotate=AnnotateNode(
                build_annotator(s.llm),
                preview_store,
                ExifContextFormatter(s.send_exif_to_llm, include_gps=not s.redact_gps),
            ),
            persist=PersistNode(repository, annotated_by=s.llm.label),
        )
        return build_graph(nodes, self._open_checkpointer())

    def _open_checkpointer(self) -> SqliteSaver | None:
        path = self._settings.checkpoint_db_path
        if path is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        self._stack.callback(connection.close)
        return SqliteSaver(connection)


def build_annotator(llm: LLMSettings) -> LLMAnnotator:
    """Create the chat model and wrap it in an :class:`LLMAnnotator`."""
    return LLMAnnotator(
        create_chat_model(llm),
        load_prompt("annotate_system"),
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
