"""Drive the Streamlit app headless with AppTest against a seeded database."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

from my_agent.db.base import Base
from my_agent.db.failure_repository import SqlAlchemyFailureRepository
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.db.session import create_db_engine, create_session_factory
from my_agent.schemas import (
    Annotation,
    ExifData,
    GpsCoordinate,
    PhotoRecord,
    SceneType,
    WhiteBalanceSource,
)
from my_agent.ui.launcher import APP_PATH

TIMEOUT_S = 30


def _seed(tmp_path: Path, photos: int) -> str:
    url = f"sqlite:///{tmp_path / 'ui.db'}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = SqlAlchemyPhotoRepository(factory)
    scenes = [SceneType.LANDSCAPE, SceneType.STREET, SceneType.PORTRAIT]
    for i in range(photos):
        preview = tmp_path / f"p{i}.jpg"
        Image.new("RGB", (40, 30), (60 * i % 255, 120, 200)).save(preview)
        repository.upsert(
            PhotoRecord(
                path=tmp_path / f"IMG_{i}.ARW",
                sha256=f"sha{i}",
                dhash="0000000000000000",
                exif=ExifData(
                    model="ILCE-6400",
                    lens_model="Sigma 17-40mm F1.8 DC | A",
                    captured_at=datetime(2026, 1 + i % 2, 11, 14, i),
                    gps=GpsCoordinate(latitude=14.6, longitude=121.0)
                    if i == 0
                    else None,
                    white_balance="Auto",
                    white_balance_k=5000 + 100 * i,
                    white_balance_k_source=WhiteBalanceSource.ESTIMATED,
                ),
                annotation=Annotation(
                    description="Sunset over the sea." if i == 0 else f"Photo {i}.",
                    tags=["sunset"] if i == 0 else ["city"],
                    scene=scenes[i % 3],
                    contains_people=i % 2 == 1,
                ),
                preview_path=preview,
                annotated_by="ollama:gemma3:12b",
                processed_at=datetime(2026, 11, 20, tzinfo=UTC),
            )
        )
    SqlAlchemyFailureRepository(factory).record(
        tmp_path / "bad.jpg",
        None,
        "decode",
        "UnsupportedFormatError",
        "Not an image",
        datetime(2026, 11, 20, tzinfo=UTC),
    )
    engine.dispose()
    return url


@pytest.fixture
def app_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    def start(photos: int) -> AppTest:
        monkeypatch.setenv("DATABASE_URL", _seed(tmp_path, photos))
        st.cache_resource.clear()
        st.cache_data.clear()
        app = AppTest.from_file(str(APP_PATH), default_timeout=TIMEOUT_S)
        app.run()
        assert not app.exception, app.exception
        return app

    yield start
    st.cache_resource.clear()
    st.cache_data.clear()


def _captions(app: AppTest) -> list[str]:
    return [c.value for c in app.caption]


def test_gallery_lists_photos_and_all_tabs_render(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)

    assert [tab.label for tab in app.tabs] == ["Gallery", "Failures", "Stats"]
    assert "Showing 1–3 of 3 photos" in _captions(app)
    assert [m.value for m in app.metric] == [
        "3",
        "1",
        "1",
        "1",
    ]  # photos, GPS, people, failures
    assert len(app.dataframe) >= 1  # failure log table


def test_search_filter_narrows_results(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)

    app.text_input(key="f_text").input("sunset").run()

    assert not app.exception
    assert "Showing 1–1 of 1 photos" in _captions(app)


def test_page_size_and_pagination(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(30)
    assert "Showing 1–24 of 30 photos" in _captions(app)

    app.button(key="g_next").click().run()

    assert not app.exception
    assert "Showing 25–30 of 30 photos" in _captions(app)

    app.selectbox(key="g_page_size").select(48).run()
    assert "Showing 1–30 of 30 photos" in _captions(app)


def test_details_dialog_opens(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(2)

    app.button(key=f"details-{tmp_path / 'IMG_0.ARW'}").click().run()

    assert not app.exception
    texts = [m.value for m in app.markdown]
    assert "**Sunset over the sea.**" in texts
    assert any("distance" in c or "identical" in c for c in _captions(app))  # near-dup


def test_empty_database_shows_hint(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(0)

    assert any("No photos" in i.value for i in app.info)


def test_white_balance_slider_filters(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)  # 5000, 5100 and 5200 K

    assert app.slider(key="f_kelvin").value == (5000, 5200)
    app.slider(key="f_kelvin").set_range(5100, 5200).run()

    assert not app.exception
    assert "Showing 1–2 of 2 photos" in _captions(app)
    app.button(key=f"details-{tmp_path / 'IMG_1.ARW'}").click().run()
    assert not app.exception
