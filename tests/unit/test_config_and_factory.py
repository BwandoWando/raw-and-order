from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from raw_and_order.config import (
    MAX_PHOTOS_HARD_LIMIT,
    MODEL_REQUIRED,
    LLMProvider,
    LLMSettings,
    Settings,
    load_settings,
)
from raw_and_order.exceptions import ConfigurationError
from raw_and_order.llm.factory import build_model_kwargs, create_chat_model
from raw_and_order.schemas import DateSource


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
    assert kwargs["max_retries"] == 0  # only the annotator retries


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

    model = create_chat_model(settings)

    assert type(model).__name__ == class_name
    if provider is not LLMProvider.OLLAMA:  # the SDK's own retries are off
        assert model.model_dump()["max_retries"] == 0


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


@pytest.mark.parametrize("value", ["0", str(MAX_PHOTOS_HARD_LIMIT + 1)])
def test_max_photos_per_run_outside_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_PHOTOS_PER_RUN", value)

    with pytest.raises(ValidationError, match="max_photos_per_run"):
        Settings(_env_file=None)


def test_chunk_size_defaults_to_25() -> None:
    assert Settings(_env_file=None).chunk_size == 25


@pytest.mark.parametrize("value", ["0", str(MAX_PHOTOS_HARD_LIMIT + 1)])
def test_chunk_size_outside_range_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("CHUNK_SIZE", value)

    with pytest.raises(ValidationError, match="chunk_size"):
        Settings(_env_file=None)


@pytest.fixture
def no_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run from an empty folder, so the real ``.env`` cannot supply a model."""
    monkeypatch.chdir(tmp_path)


@pytest.mark.usefixtures("no_env_file")
@pytest.mark.parametrize(
    "unset",
    [
        ["LLM__MODEL"],  # other LLM__ settings present, model missing
        ["LLM__MODEL", "LLM__PROVIDER", "LLM__BASE_URL"],  # no LLM__ at all
    ],
)
def test_a_missing_model_says_a_model_is_required(
    monkeypatch: pytest.MonkeyPatch, unset: list[str]
) -> None:
    for name in unset:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError) as caught:
        load_settings()

    assert str(caught.value) == MODEL_REQUIRED
    assert "LLM__MODEL" in MODEL_REQUIRED and "required" in MODEL_REQUIRED


@pytest.mark.usefixtures("no_env_file")
def test_an_empty_model_is_also_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__MODEL", "")

    with pytest.raises(ConfigurationError, match="An LLM model is required"):
        load_settings()


@pytest.mark.usefixtures("no_env_file")
def test_other_invalid_settings_keep_the_full_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHUNK_SIZE", "0")

    with pytest.raises(ConfigurationError, match="Invalid configuration") as caught:
        load_settings()

    assert "chunk_size" in str(caught.value)
