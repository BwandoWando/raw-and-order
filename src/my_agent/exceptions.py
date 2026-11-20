"""Domain exception hierarchy.

Adapters catch third-party exceptions at the boundary and re-raise one of
these with ``raise ... from exc`` so callers only depend on domain errors.
"""

from pathlib import Path


class MyAgentError(Exception):
    """Base class for all application errors."""


class FatalRunError(MyAgentError):
    """Marker: the whole run must stop (a setup problem, not a bad photo).

    Per-photo error handling re-raises these instead of logging the photo as
    failed, so photos are not blamed for an outage.
    """


class ConfigurationError(MyAgentError):
    """Settings are invalid or a required external tool is unavailable."""


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


class ModelUnavailableError(AnnotationError, FatalRunError):
    """The LLM cannot be used at all: unreachable, model missing, bad key..."""


class ModelRejectedError(AnnotationError):
    """The LLM refused this particular image (e.g. HTTP 400/413); logged per photo."""


class TooManyFailuresError(FatalRunError):
    """Too many photos in a row failed annotation; something is likely wrong."""


class RunAbortedError(MyAgentError):
    """The run stopped early because of a :class:`FatalRunError`."""

    def __init__(self, cause: FatalRunError, saved: int | None) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.saved = saved


class InvalidModelOutputError(AnnotationError):
    """The LLM response did not match the expected schema after retries."""


class PersistenceError(MyAgentError):
    """A database operation failed."""
