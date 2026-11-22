"""Work out when a photo was taken, trying several sources in order.

The sources are, by default: EXIF ``DateTimeOriginal``, XMP dates, EXIF
``CreateDate``, then a date in the file name; the order comes from the
settings (see :func:`build_date_sources`). Each source yields candidate dates,
best first. The first candidate that passes :class:`DateValidator` wins, so an
implausible date (e.g. from a camera whose clock was never set) falls through
to the next candidate or source.

Times are kept as recorded (camera local time, no timezone conversion) so
the date matches the day the photo was taken.
"""

import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from raw_and_order.media.exif_values import ExifTags
from raw_and_order.schemas.exif import DateSource

EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"
EXIF_DATE_FORMAT = "%Y:%m:%d"
# Length of a value in each format; anything after it (sub-seconds, a time
# zone offset) is ignored.
EXIF_DATETIME_LENGTH = len("2000:01:01 00:00:00")
EXIF_DATE_LENGTH = len("2000:01:01")

DATE_TIME_ORIGINAL_KEYS = ("EXIF:DateTimeOriginal",)
XMP_DATE_KEYS = ("XMP:DateCreated", "XMP:DateTimeOriginal")
CREATE_DATE_KEYS = ("EXIF:CreateDate",)

# Defaults many cameras fall back to when their clock was never set.
CAMERA_RESET_DATES = frozenset({date(2000, 1, 1), date(2001, 1, 1), date(2010, 1, 1)})
MIN_PLAUSIBLE_YEAR = 1990
FUTURE_TOLERANCE = timedelta(days=1)

_YEAR = r"((?:19|20)\d{2})"
# Tried in this order, so a date with a time is preferred over a bare date.
# (?<!\d) stops a match starting inside a longer number; (?!\d) stops the
# date-only patterns ending inside one. Trailing digits after a full time
# (e.g. milliseconds) are allowed.
FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    # IMG_20240501_183000, PXL_20240501_183000123, 20240501-183000
    re.compile(rf"(?<!\d){_YEAR}(\d{{2}})(\d{{2}})[_\-T]?(\d{{2}})(\d{{2}})(\d{{2}})"),
    # Screenshot 2024-05-01 at 18.30.00, 2024-05-01 18-30-00
    re.compile(
        rf"(?<!\d){_YEAR}-(\d{{2}})-(\d{{2}})[ _T]+(?:at[ _]+)?"
        r"(\d{1,2})[.:\-](\d{2})[.:\-](\d{2})"
    ),
    # IMG-20240501-WA0001, Screenshot_20240501
    re.compile(rf"(?<!\d){_YEAR}(\d{{2}})(\d{{2}})(?!\d)"),
    # 2024-05-01
    re.compile(rf"(?<!\d){_YEAR}-(\d{{2}})-(\d{{2}})(?!\d)"),
)


@dataclass(frozen=True)
class CaptureDate:
    """A resolved capture date and where it came from."""

    value: datetime
    source: DateSource


class CaptureDateSource(Protocol):
    """One place a capture date can come from."""

    @property
    def kind(self) -> DateSource:
        """Identifies this source in :class:`CaptureDate`."""
        ...

    def candidates(self, tags: ExifTags, path: Path) -> Iterator[datetime]:
        """Yield every date this source can find, best first."""
        ...


def parse_exif_datetime(value: Any) -> datetime | None:
    """Parse ``YYYY:MM:DD HH:MM:SS`` or ``YYYY:MM:DD``; ignore suffixes and junk.

    Sub-seconds and timezone offsets (``.123``, ``+02:00``) are dropped so the
    time stays as recorded.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt, length in (
        (EXIF_DATETIME_FORMAT, EXIF_DATETIME_LENGTH),
        (EXIF_DATE_FORMAT, EXIF_DATE_LENGTH),
    ):
        try:  # only the leading date part, so suffixes are ignored
            return datetime.strptime(text[:length], fmt)
        except ValueError:
            continue
    return None


class ExifTagDate:
    """Reads a capture date from one or more exiftool tags.

    Args:
        source: Reported as :attr:`CaptureDate.source` when this source wins.
        keys: Exiftool keys to read, in order of preference.
    """

    def __init__(self, source: DateSource, keys: Sequence[str]) -> None:
        self._source = source
        self._keys = tuple(keys)

    @property
    def kind(self) -> DateSource:
        """Identifies this source in :class:`CaptureDate`."""
        return self._source

    def candidates(self, tags: ExifTags, path: Path) -> Iterator[datetime]:
        """Yield each parseable date among the configured tags."""
        for key in self._keys:
            parsed = parse_exif_datetime(tags.get(key))
            if parsed is not None:
                yield parsed


class FilenameDate:
    """Finds a date embedded in the file name, using strict patterns.

    Args:
        patterns: Regexes whose groups are year, month, day[, h, m, s].
    """

    def __init__(self, patterns: Sequence[re.Pattern[str]] = FILENAME_PATTERNS) -> None:
        self._patterns = tuple(patterns)

    @property
    def kind(self) -> DateSource:
        """Identifies this source in :class:`CaptureDate`."""
        return DateSource.FILENAME

    def candidates(self, tags: ExifTags, path: Path) -> Iterator[datetime]:
        """Yield each real calendar date found in ``path``'s name (no extension).

        Plausibility is checked later by :class:`DateValidator`.
        """
        for pattern in self._patterns:
            for match in pattern.finditer(path.stem):
                parsed = _datetime_from_groups(match.groups())
                if parsed is not None:
                    yield parsed


def _datetime_from_groups(groups: Sequence[str]) -> datetime | None:
    """Build a date from regex groups: year, month, day[, hour, minute, second].

    A missing time means midnight; an impossible date (e.g. month 13) gives
    None instead of raising.
    """
    year, month, day, *time_parts = (int(part) for part in groups)
    hour, minute, second = (*time_parts, 0, 0, 0)[:3]  # pad a missing time with 0
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


class DateValidator:
    """Rejects dates that are almost certainly wrong.

    A date is rejected if it is before ``min_year`` (default 1990), falls on a
    camera's factory-default date (1 January 2000, 2001 or 2010), or is more
    than ``future_tolerance`` (default one day) after now; the tolerance
    leaves room for, e.g., a camera clock set to a time zone ahead of ours.

    Args:
        clock: Returns "now" in local time; injectable for tests.
        min_year: Earliest plausible year.
        reset_dates: Camera factory-default dates to reject.
        future_tolerance: How far past "now" a date may be.
    """

    def __init__(
        self,
        clock: Callable[[], datetime] = datetime.now,
        min_year: int = MIN_PLAUSIBLE_YEAR,
        reset_dates: Iterable[date] = CAMERA_RESET_DATES,
        future_tolerance: timedelta = FUTURE_TOLERANCE,
    ) -> None:
        self._clock = clock
        self._min_year = min_year
        self._reset_dates = frozenset(reset_dates)
        self._future_tolerance = future_tolerance

    def is_plausible(self, value: datetime) -> bool:
        """True if ``value`` could be a real capture time."""
        return (
            value.year >= self._min_year
            and value.date() not in self._reset_dates
            and value <= self._clock() + self._future_tolerance
        )


class CaptureDateResolver:
    """Returns the first plausible date from sources tried in order.

    Args:
        sources: Date sources, in order of preference.
        validator: Rejects implausible dates.
    """

    def __init__(
        self, sources: Sequence[CaptureDateSource], validator: DateValidator
    ) -> None:
        self._sources = tuple(sources)
        self._validator = validator

    def resolve(self, tags: ExifTags, path: Path) -> CaptureDate | None:
        """Return the capture date of ``path``, or ``None`` if none is plausible."""
        for source in self._sources:
            for value in source.candidates(tags, path):
                if self._validator.is_plausible(value):
                    return CaptureDate(value=value, source=source.kind)
        return None


def build_date_sources(order: Sequence[DateSource]) -> list[CaptureDateSource]:
    """Create date sources in the configured order.

    Args:
        order: The sources to try, most trusted first.

    Raises:
        ValueError: If ``order`` contains :attr:`DateSource.NOT_FOUND`.
    """
    factories: dict[DateSource, Callable[[], CaptureDateSource]] = {
        DateSource.EXIF_ORIGINAL: lambda: ExifTagDate(
            DateSource.EXIF_ORIGINAL, DATE_TIME_ORIGINAL_KEYS
        ),
        DateSource.XMP: lambda: ExifTagDate(DateSource.XMP, XMP_DATE_KEYS),
        DateSource.EXIF_CREATE: lambda: ExifTagDate(
            DateSource.EXIF_CREATE, CREATE_DATE_KEYS
        ),
        DateSource.FILENAME: FilenameDate,
    }
    if DateSource.NOT_FOUND in order:
        raise ValueError("'none' is not a date source")
    return [factories[source]() for source in order]
