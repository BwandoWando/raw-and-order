"""Annotate a preview image with a vision-capable chat model."""

import base64
import logging
from typing import Any, Protocol

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from raw_and_order.exceptions import (
    InvalidModelOutputError,
    ModelRejectedError,
    ModelUnavailableError,
)
from raw_and_order.llm.errors import (
    is_unavailable,
    provider_errors,
    status_code,
    transient_errors,
)
from raw_and_order.schemas.annotation import Annotation

logger = logging.getLogger(__name__)

# Raised when the model's reply does not fit the schema; answered with a
# correction message (see LLMAnnotator.annotate), not with a plain retry.
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
        output_schema: Schema the model must fill (e.g. with the tag limit).
        max_retries: Total tries per request when the provider fails
            transiently, the first one included (1 = no retry).
        max_output_fix_attempts: Total tries to get schema-valid output, the
            first one included; each retry tells the model what was wrong.
            Each try has its own transient retries, so one photo can make up
            to ``max_retries * max_output_fix_attempts`` requests.
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        system_prompt: str,
        output_schema: type[Annotation] = Annotation,
        max_retries: int = 3,
        max_output_fix_attempts: int = 2,
    ) -> None:
        self._system_prompt = system_prompt
        self._max_output_fix_attempts = max_output_fix_attempts
        self._runnable = self._build_runnable(chat_model, output_schema, max_retries)

    def annotate(self, image_jpeg: bytes, context: str | None) -> Annotation:
        """Return an annotation, asking the model to fix invalid output.

        Raises:
            ModelUnavailableError: If the provider cannot be used (outage,
                auth, missing model, rate limit), after transient retries.
            ModelRejectedError: If the provider refused this request (other
                4xx, e.g. the image is too large).
            InvalidModelOutputError: If the output never matched the schema.
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
        """Call the model once (with transient retries) and return the result.

        A reply that is not an :class:`Annotation` (e.g. ``None`` when the
        model returned no structured answer) raises
        ``OutputParserException``, so :meth:`annotate` asks for a fix.
        """
        try:
            result = self._runnable.invoke(messages)
        except provider_errors() as exc:
            raise _classify(exc) from exc
        if not isinstance(result, Annotation):
            raise OutputParserException(f"Expected Annotation, got {type(result)}")
        # The schema is a subclass with the tag limit (annotation_schema());
        # convert back to plain Annotation, the type that is stored.
        return Annotation.model_validate(result.model_dump())

    @staticmethod
    def _build_runnable(
        chat_model: BaseChatModel, output_schema: type[Annotation], max_retries: int
    ) -> Runnable[list[BaseMessage], Any]:
        """Wrap the model so it returns ``output_schema`` and retries outages.

        Only :func:`transient_errors` are retried, with exponential backoff
        and jitter; ``max_retries`` is the total number of tries.
        """
        structured = chat_model.with_structured_output(output_schema)
        retryable = transient_errors()
        if not retryable or max_retries <= 1:
            return structured
        return structured.with_retry(
            retry_if_exception_type=retryable,
            stop_after_attempt=max_retries,
            wait_exponential_jitter=True,
        )


def _classify(exc: Exception) -> ModelUnavailableError | ModelRejectedError:
    """Outage (stops the run) or a rejection of this image (logged per photo)."""
    status = status_code(exc)
    text = str(exc)
    suffix = f" (HTTP {status})" if status and str(status) not in text else ""
    if is_unavailable(exc):
        return ModelUnavailableError(f"the LLM is unavailable - {text}{suffix}")
    return ModelRejectedError(f"the LLM rejected this image - {text}{suffix}")


def _correction_message(error: Exception) -> HumanMessage:
    return HumanMessage(
        "Your previous answer did not match the required schema:\n"
        f"{error}\nReply again with only valid fields."
    )
