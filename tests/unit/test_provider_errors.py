import httpx
import ollama
import pytest

from raw_and_order.exceptions import (
    FatalRunError,
    ModelRejectedError,
    ModelUnavailableError,
)
from raw_and_order.llm.annotator import LLMAnnotator
from raw_and_order.llm.errors import is_unavailable, status_code
from raw_and_order.workflow.state import PhotoItem, Stage, StepFailure
from raw_and_order.workflow.steps._per_item import apply_step
from raw_and_order.workflow.steps.annotate import next_streak
from tests.fakes import SAMPLE_ANNOTATION, ScriptedChatModel


class StatusError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"status {status}")
        self.status_code = status


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://localhost/api/chat")
    return httpx.HTTPStatusError(
        "error", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.parametrize(
    ("exc", "unavailable"),
    [
        (httpx.ConnectError("refused"), True),  # no status: connection problem
        (ConnectionError("Failed to connect to Ollama"), True),  # ollama client
        (StatusError(401), True),
        (StatusError(403), True),
        (StatusError(404), True),  # model not found
        (StatusError(429), True),  # still rate-limited after retries
        (StatusError(500), True),
        (StatusError(503), True),
        (StatusError(400), False),  # about this image
        (StatusError(413), False),
        (StatusError(422), False),
        (_http_status_error(404), True),  # status on .response
        (_http_status_error(400), False),
    ],
)
def test_is_unavailable(exc: Exception, unavailable: bool) -> None:
    assert is_unavailable(exc) is unavailable


def test_status_code_reads_attribute_or_response() -> None:
    assert status_code(StatusError(404)) == 404
    assert status_code(_http_status_error(413)) == 413
    assert status_code(ValueError("x")) is None


def _annotator(error: Exception) -> LLMAnnotator:
    return LLMAnnotator(ScriptedChatModel(script=[error]), "system", max_retries=1)


def test_ollama_model_not_found_is_unavailable() -> None:
    error = ollama.ResponseError("model 'gemma3:27b' not found", status_code=404)

    with pytest.raises(ModelUnavailableError, match=r"not found.*404"):
        _annotator(error).annotate(b"jpeg", None)


def test_ollama_bad_request_is_a_rejection_of_the_image() -> None:
    error = ollama.ResponseError("image too large", status_code=400)

    with pytest.raises(ModelRejectedError, match="400"):
        _annotator(error).annotate(b"jpeg", None)


def test_unavailable_is_fatal_and_rejection_is_not() -> None:
    assert issubclass(ModelUnavailableError, FatalRunError)
    assert not issubclass(ModelRejectedError, FatalRunError)


def _item(**fields: object) -> PhotoItem:
    return PhotoItem.model_validate({"path": "/a.nef", **fields})


def test_apply_step_reraises_fatal_errors() -> None:
    def step(item: PhotoItem) -> PhotoItem:
        raise ModelUnavailableError("down")

    with pytest.raises(ModelUnavailableError):
        apply_step([_item()], Stage.ANNOTATE, step)


def test_apply_step_still_isolates_per_photo_errors() -> None:
    def step(item: PhotoItem) -> PhotoItem:
        raise ModelRejectedError("rejected")

    [item] = apply_step([_item()], Stage.ANNOTATE, step)

    assert item.error is not None
    assert item.error.error_type == "ModelRejectedError"


def test_next_streak() -> None:
    def failed(stage: Stage) -> PhotoItem:
        return _item(error=StepFailure(stage=stage, error_type="E", message="m"))

    ok = _item(annotation=SAMPLE_ANNOTATION)
    annotate_fail = failed(Stage.ANNOTATE)
    decode_fail = failed(Stage.DECODE)  # failed an earlier step: neutral

    assert next_streak(0, annotate_fail) == 1
    assert next_streak(2, annotate_fail) == 3
    assert next_streak(3, decode_fail) == 3
    assert next_streak(5, ok) == 0


def test_status_is_not_repeated_when_already_in_the_message() -> None:
    error = ollama.ResponseError("model 'x' not found", status_code=404)

    with pytest.raises(ModelUnavailableError) as caught:
        _annotator(error).annotate(b"jpeg", None)

    assert str(caught.value).count("404") == 1


def test_status_is_added_when_missing_from_the_message() -> None:
    class Bare(httpx.HTTPError):
        status_code = 503

    with pytest.raises(ModelUnavailableError, match=r"\(HTTP 503\)"):
        _annotator(Bare("overloaded")).annotate(b"jpeg", None)
