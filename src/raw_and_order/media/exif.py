"""EXIF reader backed by the ``exiftool`` command-line program."""

import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import exiftool
from exiftool.exceptions import ExifToolException, ExifToolVersionError

from raw_and_order.exceptions import ConfigurationError, ExifReadError
from raw_and_order.media.capture_date import parse_exif_datetime
from raw_and_order.media.exif_mapping import REQUESTED_TAGS, ExifMapper
from raw_and_order.schemas.exif import ExifData

logger = logging.getLogger(__name__)

# -G: prefix keys with their group (EXIF:, XMP:, ...). No -n: numeric tags are
# requested individually with "#" so text tags (e.g. lens names) stay readable.
EXIFTOOL_ARGS = ["-G"]
CAPTURE_TIME_TAG = "EXIF:DateTimeOriginal"
CAPTURE_TIME_BATCH = 500  # files per exiftool call
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
        mapper: Turns exiftool tags into :class:`ExifData`.
        executable: Path to ``exiftool``; ``None`` searches ``PATH``.
    """

    def __init__(self, mapper: ExifMapper, executable: str | None = None) -> None:
        self._mapper = mapper
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
        return self._mapper.map(self._read_tags(path), path)

    def capture_times(self, paths: Sequence[Path]) -> dict[Path, datetime | None]:
        """Return each path's ``DateTimeOriginal``; ``None`` if it has none.

        Reads only that one tag, in batches, so it is fast for many files.

        Raises:
            ExifReadError: If exiftool fails.
        """
        times: dict[Path, datetime | None] = {}
        for start in range(0, len(paths), CAPTURE_TIME_BATCH):
            batch = paths[start : start + CAPTURE_TIME_BATCH]
            by_name = {str(path): path for path in batch}
            for tags in self._get_tags(list(by_name), [CAPTURE_TIME_TAG]):
                path = by_name.get(str(tags.get("SourceFile")))
                if path is not None:
                    times[path] = parse_exif_datetime(tags.get(CAPTURE_TIME_TAG))
        return {path: times.get(path) for path in paths}

    def _get_tags(self, files: list[str], tags: list[str]) -> list[dict[str, Any]]:
        if self._helper is None:
            raise ExifReadError("exiftool is not running; call start() first")
        try:
            results: list[dict[str, Any]] = self._helper.get_tags(files, tags)
        except ExifToolException as exc:
            raise ExifReadError(
                f"exiftool failed on {len(files)} file(s): {exc}"
            ) from exc
        return results

    def _read_tags(self, path: Path) -> dict[str, Any]:
        if self._helper is None:
            raise ExifReadError("exiftool is not running; call start() first")
        try:
            results: list[dict[str, Any]] = self._helper.get_tags(
                str(path), list(REQUESTED_TAGS)
            )
        except ExifToolException as exc:
            raise ExifReadError(f"exiftool failed on {path}: {exc}") from exc
        if not results:
            raise ExifReadError(f"exiftool returned no metadata for {path}")
        return results[0]
