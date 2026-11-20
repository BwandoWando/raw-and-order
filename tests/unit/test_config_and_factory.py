import pytest
from pydantic import SecretStr, ValidationError

from my_agent.config import LLMProvider, LLMSettings
from my_agent.llm.factory import build_model_kwargs, create_chat_model


def test_cloud_provider_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="API_KEY"):
        LLMSettings(provider=LLMProvider.OPENAI, model="any")


def test_ollama_kwargs_use_client_timeout_and_no_key() -> None:
    kwargs = build_model_kwargs(
        LLMSettings(model="llava", base_url="http://host:11434", timeout_seconds=5)
    )

    assert kwargs == {
        "model": "llava",
        "base_url": "http://host:11434",
        "client_kwargs": {"timeout": 5},
    }


def test_cloud_kwargs_include_key_and_timeout() -> None:
    kwargs = build_model_kwargs(
        LLMSettings(
            provider=LLMProvider.ANTHROPIC,
            model="m",
            api_key=SecretStr("secret"),
            temperature=0.0,
        )
    )

    assert kwargs["api_key"] == "secret"
    assert kwargs["temperature"] == 0.0
    assert "timeout" in kwargs


@pytest.mark.parametrize(
    ("provider", "class_name"),
    [
        (LLMProvider.OLLAMA, "ChatOllama"),
        (LLMProvider.OPENAI, "ChatOpenAI"),
        (LLMProvider.ANTHROPIC, "ChatAnthropic"),
    ],
)
def test_factory_builds_each_provider(provider: LLMProvider, class_name: str) -> None:
    settings = LLMSettings(provider=provider, model="m", api_key=SecretStr("k"))

    assert type(create_chat_model(settings)).__name__ == class_name
