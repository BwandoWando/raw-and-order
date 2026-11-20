import httpx
import pytest
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from my_agent.exceptions import InvalidModelOutputError, ModelUnavailableError
from my_agent.llm.annotator import LLMAnnotator, build_messages
from my_agent.schemas import Annotation
from tests.fakes import SAMPLE_ANNOTATION, ScriptedChatModel


def _validation_error() -> ValidationError:
    try:
        Annotation.model_validate({"description": ""})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a validation error")


def _annotator(
    *script: object, fix_attempts: int = 2
) -> tuple[LLMAnnotator, ScriptedChatModel]:
    model = ScriptedChatModel(script=list(script))
    annotator = LLMAnnotator(
        model, "system", max_retries=1, max_output_fix_attempts=fix_attempts
    )
    return annotator, model


def test_returns_annotation() -> None:
    annotator, _ = _annotator(SAMPLE_ANNOTATION)

    assert annotator.annotate(b"jpeg", None) == SAMPLE_ANNOTATION


def test_retries_with_correction_after_invalid_output() -> None:
    annotator, model = _annotator(_validation_error(), SAMPLE_ANNOTATION)

    assert annotator.annotate(b"jpeg", None) == SAMPLE_ANNOTATION
    second_call = model.received[1]
    assert isinstance(second_call[-1], HumanMessage)
    assert "did not match the required schema" in str(second_call[-1].content)


def test_raises_after_repeated_invalid_output() -> None:
    annotator, _ = _annotator(None, _validation_error(), fix_attempts=2)

    with pytest.raises(InvalidModelOutputError):
        annotator.annotate(b"jpeg", None)


def test_provider_error_becomes_model_unavailable() -> None:
    annotator, _ = _annotator(httpx.ConnectError("refused"))

    with pytest.raises(ModelUnavailableError):
        annotator.annotate(b"jpeg", None)


def test_build_messages_embeds_image_and_context() -> None:
    messages = build_messages("sys", b"\xff\xd8", "make: Nikon")
    content = messages[1].content

    assert isinstance(content, list)
    image_block, context_block = content[1], content[2]
    assert isinstance(image_block, dict)
    assert isinstance(context_block, dict)
    assert image_block["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert context_block["text"].endswith("make: Nikon")
