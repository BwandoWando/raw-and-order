"""Test doubles injected through constructors instead of monkeypatching."""

import hashlib
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from PIL import Image
from pydantic import PrivateAttr

from my_agent.analysis.tag_graph import build_tag_graph
from my_agent.exceptions import ExifReadError, FingerprintError
from my_agent.schemas import (
    Annotation,
    ExifData,
    FailureRecord,
    PhotoCopy,
    PhotoRecord,
    SceneType,
)
from my_agent.schemas.query import (
    FilterOptions,
    NearDuplicate,
    PhotoPage,
    PhotoQuery,
    PhotoStats,
)
from my_agent.schemas.tags import TagGraph

SAMPLE_ANNOTATION = Annotation(
    description="A mountain lake at sunset.",
    tags=["mountain", "lake", "sunset"],
    scene=SceneType.LANDSCAPE,
    contains_people=False,
)


class FakeExifReader:
    """Returns fixed EXIF, or fails for paths listed in ``fail_for``."""

    def __init__(self, exif: ExifData, fail_for: Sequence[str] = ()) -> None:
        self._exif = exif
        self._fail_for = set(fail_for)

    def read(self, path: Path) -> ExifData:
        if path.name in self._fail_for:
            raise ExifReadError(f"corrupt: {path.name}")
        return self._exif


class FakeCaptureTimes:
    """Capture times by file name; records which files were asked about."""

    def __init__(
        self, times: dict[str, datetime] | None = None, fail: bool = False
    ) -> None:
        self._times = times or {}
        self._fail = fail
        self.asked: list[Path] = []

    def capture_times(self, paths: Sequence[Path]) -> dict[Path, datetime | None]:
        self.asked.extend(paths)
        if self._fail:
            raise ExifReadError("exiftool crashed")
        return {path: self._times.get(path.name) for path in paths}


class InMemoryCopies:
    """In-memory :class:`~my_agent.db.copy_repository.CopyRepository`."""

    def __init__(self) -> None:
        self.copies: dict[Path, PhotoCopy] = {}

    def record(self, copies: Iterable[PhotoCopy], when: datetime) -> None:
        self.copies.update((copy.path, copy) for copy in copies)

    def remove(self, paths: Iterable[Path]) -> None:
        for path in paths:
            self.copies.pop(path, None)

    def copies_under(self, folder: Path) -> list[Path]:
        return sorted(p for p in self.copies if p.is_relative_to(folder))


class FakeFileHasher:
    """SHA-256 like the real hasher, but fails for names in ``fail_for``."""

    def __init__(self, fail_for: Sequence[str] = ()) -> None:
        self._fail_for = set(fail_for)

    def hash_file(self, path: Path) -> str:
        if path.name in self._fail_for:
            raise FingerprintError(f"unreadable: {path.name}")
        return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeImageDecoder:
    """Returns a small solid-colour image and records decoded paths."""

    def __init__(self, size: tuple[int, int] = (64, 48)) -> None:
        self._size = size
        self.decoded: list[Path] = []

    def decode(self, path: Path) -> Image.Image:
        self.decoded.append(path)
        return Image.new("RGB", self._size, color=(200, 120, 40))


class FakeAnnotator:
    """Returns a fixed annotation and records what it was given.

    ``crash_on_call`` simulates the run dying (not a domain error) on that
    call; ``errors`` raises the given exception on those call numbers;
    ``always`` raises on every call.
    """

    def __init__(
        self,
        annotation: Annotation = SAMPLE_ANNOTATION,
        crash_on_call: int | None = None,
        errors: dict[int, Exception] | None = None,
        always: Exception | None = None,
    ) -> None:
        self._annotation = annotation
        self._crash_on_call = crash_on_call
        self._errors = errors or {}
        self._always = always
        self.calls: list[tuple[bytes, str | None]] = []

    def annotate(self, image_jpeg: bytes, context: str | None) -> Annotation:
        self.calls.append((image_jpeg, context))
        call = len(self.calls)
        if self._crash_on_call == call:
            raise RuntimeError("simulated crash")
        if self._always is not None:
            raise self._always
        if call in self._errors:
            raise self._errors[call]
        return self._annotation


class ScriptedChatModel(BaseChatModel):
    """Chat model whose structured output follows a script.

    Each script entry is returned in turn; exceptions are raised instead.
    """

    script: list[Any]
    _responses: Iterator[Any] = PrivateAttr()
    _received: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def model_post_init(self, context: Any) -> None:
        self._responses = iter(self.script)

    @property
    def received(self) -> list[list[BaseMessage]]:
        return self._received

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self, messages: list[BaseMessage], *args: Any, **kw: Any
    ) -> ChatResult:
        raise NotImplementedError

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable[Any, Any]:
        return RunnableLambda(self._respond)

    def _respond(self, messages: list[BaseMessage]) -> Any:
        self._received.append(list(messages))
        response = next(self._responses)
        if isinstance(response, BaseException):
            raise response
        return response


class FakePhotoLibrary:
    """In-memory :class:`~my_agent.ui.library.PhotoLibrary` for UI tests.

    Search ignores filters and sort; it only pages through ``records``.
    """

    def __init__(
        self,
        records: Sequence[PhotoRecord] = (),
        failures: Sequence[FailureRecord] = (),
        copies: dict[Path, list[Path]] | None = None,
    ) -> None:
        self._records = list(records)
        self._failures = list(failures)
        self._copies = copies or {}
        self.refreshes = 0

    def search(self, query: PhotoQuery) -> PhotoPage:
        start = (query.page - 1) * query.page_size
        return PhotoPage(
            items=self._records[start : start + query.page_size],
            total=len(self._records),
            page=query.page,
            page_size=query.page_size,
        )

    def filter_options(self) -> FilterOptions:
        return FilterOptions(
            scenes=[],
            tags=[],
            cameras=[],
            lenses=[],
            annotated_by=[],
            earliest=None,
            latest=None,
        )

    def photo(self, path: Path) -> PhotoRecord | None:
        return next((r for r in self._records if r.path == path), None)

    def near_duplicates(self, path: Path) -> list[NearDuplicate]:
        return []

    def copies_of(self, path: Path) -> list[Path]:
        return self._copies.get(path, [])

    def stats(self) -> PhotoStats:
        return PhotoStats(
            total=len(self._records),
            with_gps=sum(r.exif.gps is not None for r in self._records),
            with_people=sum(r.annotation.contains_people for r in self._records),
            by_scene=[],
            by_lens=[],
            by_camera=[],
            by_month=[],
            copies=sum(len(paths) for paths in self._copies.values()),
        )

    def tag_graph(
        self, filters: PhotoQuery, top_n: int, min_strength: float
    ) -> TagGraph:
        tag_lists = [r.annotation.tags for r in self._records]
        return build_tag_graph(tag_lists, top_n, min_strength)

    def failures(self) -> list[FailureRecord]:
        return list(self._failures)

    def refresh(self) -> None:
        self.refreshes += 1
