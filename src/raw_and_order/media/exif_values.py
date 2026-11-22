"""Read single values out of exiftool's tag dictionary (pure helpers).

Tags come from ``exiftool -G``, keyed ``Group:Tag`` (e.g. ``EXIF:Make``).
Several groups often hold the same value, so readers take a tuple of keys
in order of preference.
"""

from collections.abc import Mapping
from typing import Any


def first_value(tags: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    """The value of the first key present and not empty, else ``None``."""
    return next((tags[key] for key in keys if tags.get(key) not in (None, "")), None)


def as_text(value: Any) -> str | None:
    """``value`` as stripped text; ``None`` if missing or only whitespace."""
    return None if value is None else str(value).strip() or None


def as_float(value: Any) -> float | None:
    """``value`` as a number; ``None`` if missing or not numeric."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    """``value`` as a whole number (truncated); ``None`` if not numeric."""
    number = as_float(value)
    return None if number is None else int(number)
