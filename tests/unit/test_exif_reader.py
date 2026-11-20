from pathlib import Path

import pytest

from my_agent.exceptions import ConfigurationError, ExifReadError
from my_agent.media.exif import PyExifToolReader


def test_missing_exiftool_raises_configuration_error() -> None:
    with (
        pytest.raises(ConfigurationError, match="exiftool not found"),
        PyExifToolReader(executable="/nonexistent/exiftool"),
    ):
        pass


def test_read_before_start_raises_domain_error() -> None:
    with pytest.raises(ExifReadError, match="not running"):
        PyExifToolReader().read(Path("x.nef"))
