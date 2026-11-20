"""Domain exception hierarchy.

Adapters catch third-party exceptions at the boundary and re-raise one of
these with ``raise ... from exc`` so callers only depend on domain errors.
"""

from pathlib import Path


class MyAgentError(Exception):
    """Base class for all application errors."""


class ConfigurationError(MyAgentError):
    """Settings are invalid or a required external tool is unavailable."""


class BatchLimitExceededError(MyAgentError):
    """More photos need processing than the per-run limit allows."""

    def __init__(self, count: int, limit: int) -> None:
        super().__init__(
            f"Found {count} photos to process, which is more than the limit of "
            f"{limit}. Nothing was processed."
        )
        self.count = count
        self.limit = limit


class MediaError(MyAgentError):
    """A photo file could not be discovered, read or decoded."""


class SourceDirectoryError(MediaError):
    """The directory to scan does not exist or is not a directory."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Source directory not found: {path}")
        self.path = path


class UnsupportedFormatError(MediaError):
    """The file format is not supported by the decoder."""


class ImageDecodeError(MediaError):
    """A raw or regular image file could not be decoded."""


class ExifReadError(MediaError):
    """EXIF metadata could not be read from a file."""


class FingerprintError(MediaError):
    """A file or image hash could not be computed."""


class PreviewError(MediaError):
    """A preview image could not be written or read."""


class AnnotationError(MyAgentError):
    """The LLM could not annotate an image."""


class ModelUnavailableError(AnnotationError):
    """The LLM provider could not be reached or rejected the request."""


class InvalidModelOutputError(AnnotationError):
    """The LLM response did not match the expected schema after retries."""


class PersistenceError(MyAgentError):
    """A database operation failed."""
