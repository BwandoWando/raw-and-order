"""Enum values written to the database must never change.

The Python names may be renamed for readability (e.g. ``DateSource.NONE`` became
``DateSource.NOT_FOUND``), but the stored text must stay, or existing rows
would no longer match.
"""

from raw_and_order.schemas import DateSource
from raw_and_order.workflow.state import Stage


def test_date_source_values_are_stable() -> None:
    assert {source.value for source in DateSource} == {
        "exif_original",
        "xmp",
        "exif_create",
        "filename",
        "none",
    }
    assert DateSource.NOT_FOUND.value == "none"


def test_failure_stage_values_are_stable() -> None:
    assert {stage.value for stage in Stage} == {
        "fingerprint",
        "extract_exif",
        "decode",
        "perceptual_hash",
        "annotate",
        "persist",
    }
