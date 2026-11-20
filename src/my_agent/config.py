"""Application settings loaded from environment variables and ``.env``."""

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

from my_agent.exceptions import ConfigurationError
from my_agent.schemas.annotation import DEFAULT_MAX_TAGS, MAX_TAGS_LIMIT
from my_agent.schemas.exif import DateSource

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
    """Which model to use and how to reach it."""

    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = "llama3.2-vision"
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
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    log_level: str = "INFO"
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///data/app.db"
    checkpoint_db_path: Path | None = Path("data/checkpoints.db")
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
    max_tags: int = Field(
        default=DEFAULT_MAX_TAGS,
        ge=1,
        le=MAX_TAGS_LIMIT,
        description="Most tags the LLM may give one photo.",
    )
    send_exif_to_llm: bool = True
    redact_gps: bool = True
    llm: LLMSettings = Field(default_factory=LLMSettings)

    @field_validator("date_sources", mode="before")
    @classmethod
    def _split_date_sources(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("date_sources")
    @classmethod
    def _reject_none_source(cls, value: list[DateSource]) -> list[DateSource]:
        if DateSource.NONE in value:
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
        raise ConfigurationError(f"Invalid configuration:\n{exc}") from exc
