"""Annotate a preview image with a vision-capable chat model."""

import base64
import logging
from typing import Any, Protocol

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from my_agent.exceptions import InvalidModelOutputError, ModelUnavailableError
from my_agent.llm.errors import provider_errors, transient_errors
from my_agent.schemas.annotation import Annotation

logger = logging.getLogger(__name__)

_OUTPUT_ERRORS = (ValidationError, OutputParserException)


class Annotator(Protocol):
    """Produces an :class:`Annotation` for an image."""

    def annotate(self, image_jpeg: bytes, context: str | None) -> Annotation:
        """Describe ``image_jpeg``; ``context`` is optional extra text."""
        ...


def build_messages(
    system_prompt: str, image_jpeg: bytes, context: str | None
) -> list[BaseMessage]:
    """Build the system + user messages, with the image as a data URL."""
    encoded = base64.b64encode(image_jpeg).decode("ascii")
    content: list[str | dict[str, Any]] = [
        {"type": "text", "text": "Annotate this photo."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
        },
    ]
    if context:
        content.append({"type": "text", "text": f"Camera metadata:\n{context}"})
    return [SystemMessage(system_prompt), HumanMessage(content=content)]


class LLMAnnotator:
    """:class:`Annotator` backed by any LangChain chat model.

    Args:
        chat_model: A vision-capable chat model.
        system_prompt: Instructions for the model.
        max_retries: Attempts for transient provider errors.
        max_output_fix_attempts: Attempts to get schema-valid output.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        system_prompt: str,
        max_retries: int = 3,
        max_output_fix_attempts: int = 2,
    ) -> None:
        self._system_prompt = system_prompt
        self._max_output_fix_attempts = max_output_fix_attempts
        self._runnable = self._build_runnable(chat_model, max_retries)

    def annotate(self, image_jpeg: bytes, context: str | None) -> Annotation:
        """Return an annotation, asking the model to fix invalid output.

        Raises:
            ModelUnavailableError: If the provider fails after retries.
            InvalidModelOutputError: If output never matches the schema.
        """
        messages = build_messages(self._system_prompt, image_jpeg, context)
        for attempt in range(1, self._max_output_fix_attempts + 1):
            try:
                return self._invoke(messages)
            except _OUTPUT_ERRORS as exc:
                logger.warning("Invalid model output (attempt %d): %s", attempt, exc)
                messages = [*messages, _correction_message(exc)]
        raise InvalidModelOutputError(
            f"No valid annotation after {self._max_output_fix_attempts} attempts"
        )

    def _invoke(self, messages: list[BaseMessage]) -> Annotation:
        try:
            result = self._runnable.invoke(messages)
        except provider_errors() as exc:
            raise ModelUnavailableError(f"LLM request failed: {exc}") from exc
        if not isinstance(result, Annotation):
            raise OutputParserException(f"Expected Annotation, got {type(result)}")
        return result

    @staticmethod
    def _build_runnable(
        chat_model: BaseChatModel, max_retries: int
    ) -> Runnable[list[BaseMessage], Any]:
        structured = chat_model.with_structured_output(Annotation)
        retryable = transient_errors()
        if not retryable or max_retries <= 1:
            return structured
        return structured.with_retry(
            retry_if_exception_type=retryable,
            stop_after_attempt=max_retries,
            wait_exponential_jitter=True,
        )


def _correction_message(error: Exception) -> HumanMessage:
    return HumanMessage(
        "Your previous answer did not match the required schema:\n"
        f"{error}\nReply again with only valid fields."
    )
