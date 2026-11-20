"""Turn EXIF data into prompt context, honouring privacy settings."""

from my_agent.schemas.exif import ExifData


class ExifContextFormatter:
    """Formats EXIF as short text for the LLM prompt.

    Args:
        enabled: If ``False``, no EXIF is sent to the model at all.
        include_gps: If ``False``, GPS coordinates are left out.
    """

    def __init__(self, enabled: bool = True, include_gps: bool = False) -> None:
        self._enabled = enabled
        self._include_gps = include_gps

    def format(self, exif: ExifData | None) -> str | None:
        """Return a ``key: value`` block, or ``None`` if nothing to send."""
        if not self._enabled or exif is None:
            return None
        lines = [f"{key}: {value}" for key, value in self._fields(exif).items()]
        return "\n".join(lines) or None

    def _fields(self, exif: ExifData) -> dict[str, object]:
        fields = exif.model_dump(exclude_none=True, exclude={"gps", "date_source"})
        if self._include_gps and exif.gps is not None:
            fields["gps"] = f"{exif.gps.latitude:.5f}, {exif.gps.longitude:.5f}"
        return fields
