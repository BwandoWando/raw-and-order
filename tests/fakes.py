"""Test doubles injected through constructors instead of monkeypatching."""

import hashlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from PIL import Image
from pydantic import PrivateAttr

from my_agent.exceptions import ExifReadError, FingerprintError
from my_agent.schemas import Annotation, ExifData, SceneType

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

    ``crash_on_call`` simulates the run dying (not a per-file domain error)
    on that call number, e.g. to test what an interruption keeps.
    """

    def __init__(
        self,
        annotation: Annotation = SAMPLE_ANNOTATION,
        crash_on_call: int | None = None,
    ) -> None:
        self._annotation = annotation
        self._crash_on_call = crash_on_call
        self.calls: list[tuple[bytes, str | None]] = []

    def annotate(self, image_jpeg: bytes, context: str | None) -> Annotation:
        self.calls.append((image_jpeg, context))
        if self._crash_on_call == len(self.calls):
            raise RuntimeError("simulated crash")
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
