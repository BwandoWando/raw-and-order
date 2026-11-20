from my_agent.llm.context import ExifContextFormatter
from my_agent.schemas import ExifData


def test_gps_is_redacted_by_default(sample_exif: ExifData) -> None:
    context = ExifContextFormatter().format(sample_exif)

    assert context is not None
    assert "Nikon" in context
    assert "46.5" not in context


def test_gps_included_when_allowed(sample_exif: ExifData) -> None:
    context = ExifContextFormatter(include_gps=True).format(sample_exif)

    assert context is not None
    assert "gps: 46.50000, 8.10000" in context


def test_nothing_sent_when_disabled(sample_exif: ExifData) -> None:
    assert ExifContextFormatter(enabled=False).format(sample_exif) is None
