import sys
from pathlib import Path

import pytest

from raw_and_order.exceptions import ConfigurationError, ExifReadError
from raw_and_order.media.capture_date import (
    CaptureDateResolver,
    DateValidator,
    build_date_sources,
)
from raw_and_order.media.exif import PyExifToolReader
from raw_and_order.media.exif_mapping import ExifMapper
from raw_and_order.schemas import DateSource


def _mapper() -> ExifMapper:
    sources = build_date_sources([DateSource.EXIF_ORIGINAL])
    return ExifMapper(CaptureDateResolver(sources, DateValidator()))


def test_missing_exiftool_raises_configuration_error() -> None:
    with (
        pytest.raises(ConfigurationError, match="exiftool not found"),
        PyExifToolReader(_mapper(), executable="/nonexistent/exiftool"),
    ):
        pass


def test_read_before_start_raises_domain_error() -> None:
    with pytest.raises(ExifReadError, match="not running"):
        PyExifToolReader(_mapper()).read(Path("x.nef"))


FAKE_OLD_EXIFTOOL = """#!{python}
# Minimal stand-in for exiftool's -stay_open protocol that reports 11.88.
import sys

args = []
for line in sys.stdin:
    line = line.rstrip("\\n")
    if line.startswith("-execute"):
        seq = line[len("-execute"):]
        if "-echo4" in args:
            sys.stderr.write(args[args.index("-echo4") + 1] + "\\n")
            sys.stderr.flush()
        sys.stdout.write("11.88\\n{{ready" + seq + "}}\\n")
        sys.stdout.flush()
        args = []
    else:
        args.append(line)
"""


def test_old_exiftool_raises_configuration_error(tmp_path: Path) -> None:
    fake = tmp_path / "exiftool"
    fake.write_text(FAKE_OLD_EXIFTOOL.format(python=sys.executable))
    fake.chmod(0o755)

    with (
        pytest.raises(ConfigurationError, match=r"12\.15\+ is required"),
        PyExifToolReader(_mapper(), executable=str(fake)),
    ):
        pass
