"""EXIF reader backed by the ``exiftool`` command-line program."""

import logging
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import exiftool
from exiftool.exceptions import ExifToolException, ExifToolVersionError

from my_agent.exceptions import ConfigurationError, ExifReadError
from my_agent.media.exif_mapping import map_exif
from my_agent.schemas.exif import ExifData

logger = logging.getLogger(__name__)

EXIFTOOL_ARGS = ["-G", "-n"]
MIN_EXIFTOOL_VERSION = "12.15"  # required by pyexiftool
INSTALL_HINT = (
    "Install a current release from https://exiftool.org "
    "(distro packages on older Ubuntu releases are too old)."
)


class PyExifToolReader:
    """Reads EXIF through one long-running ``exiftool`` process.

    Use as a context manager so the process is started once per run and
    always stopped.

    Args:
        executable: Path to ``exiftool``; ``None`` searches ``PATH``.
    """

    def __init__(self, executable: str | None = None) -> None:
        self._executable = executable
        self._helper: exiftool.ExifToolHelper | None = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        """Start the exiftool process.

        Raises:
            ConfigurationError: If exiftool is missing or too old.
        """
        try:
            helper = exiftool.ExifToolHelper(
                executable=self._executable, common_args=EXIFTOOL_ARGS
            )
        except FileNotFoundError as exc:
            raise ConfigurationError(f"exiftool not found. {INSTALL_HINT}") from exc
        try:
            helper.run()
        except ExifToolVersionError as exc:
            raise ConfigurationError(
                f"exiftool {MIN_EXIFTOOL_VERSION}+ is required "
                f"(check with `exiftool -ver`). {INSTALL_HINT}"
            ) from exc
        self._helper = helper

    def close(self) -> None:
        """Stop the exiftool process if it is running."""
        if self._helper is not None and self._helper.running:
            self._helper.terminate()
        self._helper = None

    def read(self, path: Path) -> ExifData:
        """Return the EXIF metadata of ``path``.

        Raises:
            ExifReadError: If exiftool fails on this file.
        """
        return map_exif(self._read_tags(path))

    def _read_tags(self, path: Path) -> dict[str, Any]:
        if self._helper is None:
            raise ExifReadError("exiftool is not running; call start() first")
        try:
            results: list[dict[str, Any]] = self._helper.get_metadata(str(path))
        except ExifToolException as exc:
            raise ExifReadError(f"exiftool failed on {path}: {exc}") from exc
        if not results:
            raise ExifReadError(f"exiftool returned no metadata for {path}")
        return results[0]
