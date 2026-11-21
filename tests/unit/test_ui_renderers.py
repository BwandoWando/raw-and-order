"""Render the UI against an injected in-memory library (no database)."""

from datetime import UTC, datetime
from pathlib import Path

from streamlit.testing.v1 import AppTest

from my_agent.schemas import ExifData, FailureRecord, PhotoRecord
from my_agent.ui.library import PhotoLibrary
from tests.fakes import SAMPLE_ANNOTATION, FakePhotoLibrary

TIMEOUT_S = 30
WHEN = datetime(2026, 11, 20, tzinfo=UTC)


def _record(i: int) -> PhotoRecord:
    return PhotoRecord(
        path=Path(f"/photos/IMG_{i}.DNG"),
        exif=ExifData(model="GR IV"),
        annotation=SAMPLE_ANNOTATION,
        preview_path=Path(f"/missing/p{i}.jpg"),
        annotated_by="fake",
        processed_at=WHEN,
    )


def _failure() -> FailureRecord:
    return FailureRecord(
        path=Path("/photos/bad.jpg"),
        sha256=None,
        stage="decode",
        error_type="ImageDecodeError",
        message="truncated",
        attempts=2,
        first_failed_at=WHEN,
        last_failed_at=WHEN,
    )


def _app(library: PhotoLibrary) -> AppTest:
    def script(library: "PhotoLibrary") -> None:  # quoted: runs standalone
        from my_agent.ui.app import main

        main(library)

    app = AppTest.from_function(script, args=(library,), default_timeout=TIMEOUT_S)
    app.run()
    assert not app.exception, app.exception
    return app


def test_gallery_pages_through_the_injected_library() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))

    assert "Showing 1–24 of 30 photos" in [c.value for c in app.caption]
    app.button(key="g_next").click().run()
    assert "Showing 25–30 of 30 photos" in [c.value for c in app.caption]


def test_details_dialog_reads_from_the_library() -> None:
    app = _app(FakePhotoLibrary([_record(0)]))

    app.button(key="details-/photos/IMG_0.DNG").click().run()

    assert not app.exception
    assert f"**{SAMPLE_ANNOTATION.description}**" in [m.value for m in app.markdown]


def test_failures_and_stats_tabs_use_the_library() -> None:
    app = _app(FakePhotoLibrary([_record(0)], failures=[_failure()]))

    assert [m.value for m in app.metric] == ["1", "0", "0", "1"]
    assert len(app.dataframe) >= 1


def test_refresh_button_asks_the_library_to_refresh() -> None:
    library = FakePhotoLibrary()
    app = _app(library)

    app.sidebar.button[0].click().run()

    assert library.refreshes == 1
