import pytest
from pydantic import SecretStr, ValidationError

from my_agent.config import LLMProvider, LLMSettings, Settings
from my_agent.llm.factory import build_model_kwargs, create_chat_model
from my_agent.schemas import DateSource


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


def test_date_sources_parse_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATE_SOURCES", "filename, exif_original")

    settings = Settings(_env_file=None)

    assert settings.date_sources == [DateSource.FILENAME, DateSource.EXIF_ORIGINAL]


def test_date_sources_reject_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATE_SOURCES", "exif_original,none")

    with pytest.raises(ValidationError, match="not a date source"):
        Settings(_env_file=None)


def test_default_date_source_order() -> None:
    assert Settings(_env_file=None).date_sources == [
        DateSource.EXIF_ORIGINAL,
        DateSource.XMP,
        DateSource.EXIF_CREATE,
        DateSource.FILENAME,
    ]


def test_max_photos_per_run_defaults_to_500() -> None:
    assert Settings(_env_file=None).max_photos_per_run == 500


@pytest.mark.parametrize("value", ["0", "2001"])
def test_max_photos_per_run_outside_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_PHOTOS_PER_RUN", value)

    with pytest.raises(ValidationError, match="max_photos_per_run"):
        Settings(_env_file=None)
