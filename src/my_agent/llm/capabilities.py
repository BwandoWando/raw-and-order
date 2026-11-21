"""Check that the configured model can accept images."""

from typing import Protocol

import httpx

from my_agent.exceptions import ConfigurationError

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class CapabilityChecker(Protocol):
    """Verifies a model supports what the pipeline needs."""

    def ensure_vision_support(self, model: str) -> None:
        """Raise :class:`ConfigurationError` if ``model`` cannot read images."""
        ...


class OllamaCapabilityChecker:
    """Asks a running Ollama server whether a model supports vision.

    Args:
        client: HTTP client pointed at the Ollama server.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def ensure_vision_support(self, model: str) -> None:
        """Raise if Ollama is unreachable, lacks the model, or it has no vision.

        Raises:
            ConfigurationError: If the model cannot be used for annotation.
        """
        capabilities = self._fetch_capabilities(model)
        if "vision" not in capabilities:
            raise ConfigurationError(
                f"Ollama model '{model}' does not support images. "
                "Use a vision model such as gemma3, qwen2.5vl or llava."
            )

    def _fetch_capabilities(self, model: str) -> list[str]:
        try:
            response = self._client.post("/api/show", json={"model": model})
        except httpx.TransportError as exc:
            raise ConfigurationError(
                f"Cannot reach Ollama at {self._client.base_url}. Is it running?"
            ) from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise ConfigurationError(
                f"Ollama model '{model}' is not installed. Run `ollama pull {model}`."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConfigurationError(f"Ollama returned an error: {exc}") from exc
        capabilities: list[str] = response.json().get("capabilities", [])
        return capabilities


class AssumeVisionChecker:
    """For cloud providers, where vision support cannot be queried cheaply."""

    def ensure_vision_support(self, model: str) -> None:
        """Accept any model; provider errors surface on the first request."""
