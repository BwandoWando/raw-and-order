"""Drive the Streamlit app headless with AppTest against a seeded database."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

from raw_and_order.db.base import Base
from raw_and_order.db.failure_repository import SqlAlchemyFailureRepository
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.db.session import create_db_engine, create_session_factory
from raw_and_order.schemas import (
    Annotation,
    ExifData,
    GpsCoordinate,
    PhotoRecord,
    SceneType,
    WhiteBalanceSource,
)
from raw_and_order.schemas.query import FilterOptions, SortOrder
from raw_and_order.ui.filters import RESET_KEY, FilterKey, filter_defaults
from raw_and_order.ui.gallery import GalleryKey, open_button_key
from raw_and_order.ui.launcher import APP_PATH

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
                phash="0000000000000000",
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

    assert [tab.label for tab in app.tabs] == [
        "Gallery",
        "Tags",
        "Failures",
        "Stats",
        "Export",
    ]
    assert "Showing 1–3 of 3 photos" in _captions(app)
    assert [m.value for m in app.metric] == [
        "3",
        "1",
        "1",
        "0",
        "1",
    ]  # photos, GPS, people, copies, failures
    assert len(app.dataframe) >= 1  # failure log table


def test_search_filter_narrows_results(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)

    app.text_input(key=FilterKey.TEXT).input("sunset").run()

    assert not app.exception
    assert "Showing 1–1 of 1 photos" in _captions(app)


def test_page_size_and_pagination(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(30)
    assert "Showing 1–24 of 30 photos" in _captions(app)

    app.button(key=GalleryKey.NEXT).click().run()

    assert not app.exception
    assert "Showing 25–30 of 30 photos" in _captions(app)

    app.selectbox(key=GalleryKey.PAGE_SIZE).select(48).run()
    assert "Showing 1–30 of 30 photos" in _captions(app)


def test_details_dialog_opens(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)

    app.button(key=open_button_key(tmp_path / "IMG_0.ARW")).click().run()

    assert not app.exception
    assert "**Sunset over the sea.**" in [m.value for m in app.markdown]
    assert "No similar photos found." in _captions(app)  # same pHash, other tags


def test_details_list_tag_matches(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)

    app.button(key=open_button_key(tmp_path / "IMG_1.ARW")).click().run()

    assert not app.exception
    assert "IMG_2.ARW · Identical" in _captions(app)  # both tagged "city"


def test_empty_database_shows_hint(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(0)

    assert any("No photos" in i.value for i in app.info)


def test_white_balance_slider_filters(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)  # 5000, 5100 and 5200 K

    assert app.slider(key=FilterKey.KELVIN).value == (5000, 5200)
    app.slider(key=FilterKey.KELVIN).set_range(5100, 5200).run()

    assert not app.exception
    assert "Showing 1–2 of 2 photos" in _captions(app)
    app.button(key=open_button_key(tmp_path / "IMG_1.ARW")).click().run()
    assert not app.exception


def test_clicking_the_thumbnail_opens_details(app_with, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    app = app_with(2)
    photo = tmp_path / "IMG_0.ARW"

    app.button(key=open_button_key(photo)).click().run()

    assert not app.exception
    assert "**Sunset over the sea.**" in [m.value for m in app.markdown]


def test_thumbnail_button_is_labelled_for_screen_readers(
    app_with: Callable[[int], AppTest], tmp_path: Path
) -> None:
    app = app_with(1)

    button = app.button(key=open_button_key(tmp_path / "IMG_0.ARW"))

    assert button.label == "Open details for IMG_0.ARW"


def test_page_sizes_and_tooltips_show_captions(
    app_with: Callable[[int], AppTest], tmp_path: Path
) -> None:
    app = app_with(3)

    assert list(app.selectbox(key=GalleryKey.PAGE_SIZE).options) == [
        "24",
        "48",
        "72",
        "99",
    ]
    app.selectbox(key=GalleryKey.PAGE_SIZE).select(99).run()
    assert "Showing 1–3 of 3 photos" in _captions(app)
    button = app.button(key=open_button_key(tmp_path / "IMG_0.ARW"))
    assert button.help == "2026-01-11 · landscape"


def _sidebar_filters(app: AppTest) -> dict[str, object]:
    """Key and value of every filter widget in the sidebar."""
    widgets = [
        *app.sidebar.text_input,
        *app.sidebar.multiselect,
        *app.sidebar.button_group,
        *app.sidebar.date_input,
        *app.sidebar.checkbox,
        *app.sidebar.toggle,
        *app.sidebar.slider,
    ]
    return {str(w.key): w.value for w in widgets}


def test_reset_filters_restores_every_filter(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(6)
    untouched = _sidebar_filters(app)
    app.text_input(key=FilterKey.TEXT).input("photo").run()
    for key, value in [
        (FilterKey.SCENES, "street"),
        (FilterKey.TAGS, "city"),
        (FilterKey.CAMERAS, "ILCE-6400"),
        (FilterKey.LENSES, "Sigma 17-40mm F1.8 DC | A"),
        (FilterKey.ANNOTATED_BY, "ollama:gemma3:12b"),
    ]:
        app.multiselect(key=key).select(value).run()
    app.button_group(key=FilterKey.PEOPLE).set_value("Yes").run()
    app.checkbox(key=FilterKey.GPS).check().run()
    app.toggle(key=FilterKey.FAVORITES).set_value(True).run()
    app.slider(key=FilterKey.KELVIN).set_range(5100, 5300).run()
    day = date(2026, 1, 11)
    app.date_input(key=FilterKey.DATES).set_value((day, day)).run()
    assert "Showing 1–6 of 6 photos" not in _captions(app)

    app.button(key=RESET_KEY).click().run()

    assert not app.exception
    assert _sidebar_filters(app) == untouched
    assert "Showing 1–6 of 6 photos" in _captions(app)


def test_reset_covers_every_sidebar_filter(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)
    options = FilterOptions(
        scenes=[],
        tags=[],
        cameras=[],
        lenses=[],
        annotated_by=[],
        earliest=date(2026, 1, 1),
        latest=date(2026, 2, 1),
        kelvin_min=5000,
        kelvin_max=5200,
    )

    assert set(_sidebar_filters(app)) == set(filter_defaults(options))
    assert set(_sidebar_filters(app)) == set(FilterKey)


def _export_first_file(app: AppTest) -> str:
    table = next(d.value for d in app.dataframe if "file_name" in d.value)
    return str(table["file_name"].iloc[0])


def test_export_follows_the_gallery_sort(app_with) -> None:  # type: ignore[no-untyped-def]
    app = app_with(3)  # IMG_1 is the newest capture, IMG_0 the oldest
    assert _export_first_file(app) == "IMG_1.ARW"

    app.selectbox(key=GalleryKey.SORT).select(SortOrder.CAPTURED_OLDEST).run()

    assert not app.exception
    assert _export_first_file(app) == "IMG_0.ARW"
