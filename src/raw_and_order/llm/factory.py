"""Create a LangChain chat model for the configured provider.

This is the only module that knows about concrete provider classes. Provider
packages are optional extras, so they are imported lazily.
"""

import importlib
from typing import Any

from langchain_core.language_models import BaseChatModel

from raw_and_order.config import LLMProvider, LLMSettings
from raw_and_order.exceptions import ConfigurationError

_PROVIDER_CLASSES: dict[LLMProvider, tuple[str, str, str]] = {
    # provider: (module, class name, pip extra)
    LLMProvider.OLLAMA: ("langchain_ollama", "ChatOllama", "ollama"),
    LLMProvider.OPENAI: ("langchain_openai", "ChatOpenAI", "openai"),
    LLMProvider.ANTHROPIC: ("langchain_anthropic", "ChatAnthropic", "anthropic"),
}


def create_chat_model(settings: LLMSettings) -> BaseChatModel:
    """Return a chat model for ``settings.provider``.

    Raises:
        ConfigurationError: If the provider package is not installed.
    """
    model_class = _load_model_class(settings.provider)
    return model_class(**build_model_kwargs(settings))  # type: ignore[no-any-return]


def build_model_kwargs(settings: LLMSettings) -> dict[str, Any]:
    """Translate :class:`LLMSettings` into constructor arguments.

    ``ChatOllama`` takes the timeout through ``client_kwargs`` (passed to its
    HTTP client); the other chat classes take a ``timeout`` argument.
    """
    kwargs: dict[str, Any] = {"model": settings.model}
    if settings.temperature is not None:
        kwargs["temperature"] = settings.temperature
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    if settings.api_key is not None:
        kwargs["api_key"] = settings.api_key.get_secret_value()
    if settings.provider is LLMProvider.OLLAMA:
        kwargs["client_kwargs"] = {"timeout": settings.timeout_seconds}
    else:
        kwargs["timeout"] = settings.timeout_seconds
    return kwargs


def _load_model_class(provider: LLMProvider) -> Any:
    module_name, class_name, extra = _PROVIDER_CLASSES[provider]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigurationError(
            f"Provider '{provider}' needs the '{extra}' extra: "
            f'pip install -e ".[{extra}]"'
        ) from exc
    return getattr(module, class_name)
