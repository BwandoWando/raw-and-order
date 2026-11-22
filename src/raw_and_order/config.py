"""Application settings loaded from environment variables and ``.env``.

:func:`load_settings` is called once per command (and by the Alembic
environment); the resulting :class:`Settings` is passed down to
:mod:`raw_and_order.bootstrap`, which builds everything from it. Nested LLM
settings use a double underscore, e.g. ``LLM__MODEL=gemma3:12b``.
"""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from raw_and_order.exceptions import ConfigurationError
from raw_and_order.schemas.annotation import DEFAULT_MAX_TAGS, MAX_TAGS_LIMIT
from raw_and_order.schemas.exif import DateSource

DEFAULT_RAW_EXTENSIONS = frozenset(
    {".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2", ".dng"}
)
DEFAULT_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif"}
)
DEFAULT_MAX_PHOTOS_PER_RUN = 500
MAX_PHOTOS_HARD_LIMIT = 5000
DEFAULT_CHUNK_SIZE = 25

DEFAULT_DATE_SOURCES = (
    DateSource.EXIF_ORIGINAL,
    DateSource.XMP,
    DateSource.EXIF_CREATE,
    DateSource.FILENAME,
)


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LLMSettings(BaseModel):
    """Which model to use and how to reach it.

    ``model`` has no default on purpose: a run must never fall back to a
    model you did not choose, so a missing ``LLM__MODEL`` stops at startup.
    """

    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = Field(min_length=1)
    base_url: str | None = None
    api_key: SecretStr | None = None
    temperature: float | None = None
    timeout_seconds: float = 120.0
    max_retries: int = Field(default=3, ge=1)
    max_output_fix_attempts: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def _require_api_key_for_cloud(self) -> "LLMSettings":
        if self.provider is not LLMProvider.OLLAMA and self.api_key is None:
            raise ValueError(f"LLM__API_KEY is required for provider '{self.provider}'")
        return self

    @property
    def label(self) -> str:
        """Short identifier stored with each annotation, e.g. ``ollama:llava``."""
        return f"{self.provider}:{self.model}"


class Settings(BaseSettings):
    """Top-level application settings.

    Each field is read from the environment variable of the same name in
    upper case (``CHUNK_SIZE``, ``DATE_SOURCES``...), or from ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    log_level: str = "INFO"
    database_url: str = "sqlite:///data/app.db"
    preview_dir: Path = Path("data/previews")
    preview_max_px: int = Field(default=1024, ge=64)
    preview_quality: int = Field(default=85, ge=1, le=100)
    raw_extensions: frozenset[str] = DEFAULT_RAW_EXTENSIONS
    image_extensions: frozenset[str] = DEFAULT_IMAGE_EXTENSIONS
    date_sources: Annotated[list[DateSource], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_DATE_SOURCES),
        description="Capture-date sources in order, e.g. exif_original,xmp.",
    )
    max_photos_per_run: int = Field(
        default=DEFAULT_MAX_PHOTOS_PER_RUN,
        ge=1,
        le=MAX_PHOTOS_HARD_LIMIT,
        description="Process at most this many photos per run; the rest wait.",
    )
    chunk_size: int = Field(
        default=DEFAULT_CHUNK_SIZE,
        ge=1,
        le=MAX_PHOTOS_HARD_LIMIT,
        description="Photos processed and saved together; limits interrupted work.",
    )
    max_consecutive_failures: int = Field(
        default=10,
        ge=0,
        description="Stop a run after this many annotation failures in a row "
        "(0 = never).",
    )
    max_tags: int = Field(
        default=DEFAULT_MAX_TAGS,
        ge=1,
        le=MAX_TAGS_LIMIT,
        description="Most tags the LLM may give one photo.",
    )
    send_exif_to_llm: bool = True
    redact_gps: bool = True
    llm: LLMSettings  # required: LLM__MODEL must be set (see LLMSettings)

    @field_validator("date_sources", mode="before")
    @classmethod
    def _split_date_sources(cls, value: Any) -> Any:
        """Accept ``DATE_SOURCES=exif_original,xmp`` (``NoDecode``: not JSON)."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("date_sources")
    @classmethod
    def _reject_none_source(cls, value: list[DateSource]) -> list[DateSource]:
        """``none`` (NOT_FOUND) marks a photo without a date; it cannot be read."""
        if DateSource.NOT_FOUND in value:
            raise ValueError("'none' is not a date source; leave it out instead")
        return value


def load_settings() -> Settings:
    """Load settings, converting validation failures into a domain error.

    Raises:
        ConfigurationError: If any setting is missing or invalid.
    """
    try:
        return Settings()
    except ValidationError as exc:
        if _model_missing(exc):
            raise ConfigurationError(MODEL_REQUIRED) from exc
        raise ConfigurationError(f"Invalid configuration:\n{exc}") from exc


MODEL_REQUIRED = (
    "An LLM model is required: set LLM__MODEL in .env (e.g. "
    "LLM__MODEL=gemma3:27b), or as an environment variable. See .env.example."
)


def _model_missing(exc: ValidationError) -> bool:
    """True if validation failed because no model (or no LLM section) was set.

    Without any ``LLM__`` variable the whole ``llm`` section is missing; with
    some but no ``LLM__MODEL`` (or an empty one) only ``llm.model`` is.
    """
    return any(
        error["loc"] in (("llm",), ("llm", "model"))
        and error["type"] in ("missing", "string_too_short")
        for error in exc.errors()
    )
