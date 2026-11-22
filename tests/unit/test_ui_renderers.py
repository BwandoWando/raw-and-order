"""Render the UI against an injected in-memory library (no database)."""

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from raw_and_order.schemas import (
    Annotation,
    ExifData,
    FailureRecord,
    GpsCoordinate,
    PhotoRecord,
    SceneType,
)
from raw_and_order.schemas.query import NearDuplicate
from raw_and_order.ui.css import PINNED_MULTISELECT_BUTTONS
from raw_and_order.ui.detail import (
    FAVORITE_OFF_KEY,
    FAVORITE_ON_KEY,
    similar_button_key,
)
from raw_and_order.ui.filters import FilterKey
from raw_and_order.ui.gallery import GalleryKey, open_button_key
from raw_and_order.ui.library import PhotoLibrary
from tests.fakes import SAMPLE_ANNOTATION, FakePhotoLibrary

TIMEOUT_S = 30
WHEN = datetime(2026, 11, 20, tzinfo=UTC)


def _record(i: int, annotation: Annotation = SAMPLE_ANNOTATION) -> PhotoRecord:
    return PhotoRecord(
        path=Path(f"/photos/IMG_{i}.DNG"),
        exif=ExifData(model="GR IV"),
        annotation=annotation,
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
        from raw_and_order.ui.app import main

        main(library)

    app = AppTest.from_function(script, args=(library,), default_timeout=TIMEOUT_S)
    app.run()
    assert not app.exception, app.exception
    return app


def test_gallery_pages_through_the_injected_library() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))

    assert "Showing 1–24 of 30 photos" in [c.value for c in app.caption]
    app.button(key=GalleryKey.NEXT).click().run()
    assert "Showing 25–30 of 30 photos" in [c.value for c in app.caption]


def test_details_dialog_reads_from_the_library() -> None:
    app = _app(FakePhotoLibrary([_record(0)]))

    app.button(key=open_button_key(Path("/photos/IMG_0.DNG"))).click().run()

    assert not app.exception
    assert f"**{SAMPLE_ANNOTATION.description}**" in [m.value for m in app.markdown]


def test_details_put_long_sections_in_tabs() -> None:
    gps = GpsCoordinate(latitude=14.6, longitude=121.0)
    located = _record(1).model_copy(update={"exif": ExifData(gps=gps)})
    app = _app(FakePhotoLibrary([_record(0), located]))

    app.button(key=open_button_key(_record(0).path)).click().run()
    assert [t.label for t in app.tabs][-2:] == ["Similar photos", "Files"]
    app.button(key=open_button_key(located.path)).click().run()
    assert [t.label for t in app.tabs][-3:] == ["Similar photos", "Location", "Files"]


def test_failures_and_stats_tabs_use_the_library() -> None:
    app = _app(FakePhotoLibrary([_record(0)], failures=[_failure()]))

    assert [m.value for m in app.metric] == ["1", "0", "0", "0", "1"]
    assert len(app.dataframe) >= 1


def test_refresh_button_asks_the_library_to_refresh() -> None:
    library = FakePhotoLibrary()
    app = _app(library)

    app.sidebar.button[0].click().run()

    assert library.refreshes == 1


def _tagged(i: int, *tags: str) -> PhotoRecord:
    annotation = Annotation(
        description=f"Photo {i}.",
        tags=list(tags),
        scene=SceneType.STREET,
        contains_people=False,
    )
    return _record(i, annotation)


def test_tags_tab_draws_the_network_and_clusters() -> None:
    photos = [_tagged(i, "city", "night", "neon") for i in range(3)]
    photos += [_tagged(i + 3, "sea", "sand") for i in range(3)]
    app = _app(FakePhotoLibrary(photos))

    tags_tab = app.tabs[1]
    assert tags_tab.label == "Tags"
    assert "**city · neon · night**" in [m.value for m in tags_tab.markdown]
    assert any("5 most-used tags across 6 photos" in c.value for c in tags_tab.caption)


def test_tags_tab_without_tags_shows_a_hint() -> None:
    app = _app(FakePhotoLibrary([_tagged(0)]))

    assert any("No tagged photos" in i.value for i in app.tabs[1].info)


def test_tags_sliders_rebuild_the_graph() -> None:
    photos = [_tagged(i, "a", "b") for i in range(3)] + [_tagged(9, "a", "c")]
    app = _app(FakePhotoLibrary(photos))

    app.slider(key="t_strength").set_value(0.5).run()

    assert not app.exception
    assert "**a · b**" in [m.value for m in app.tabs[1].markdown]


def test_details_list_exact_copies() -> None:
    copy = Path("/backup/IMG_0.DNG")
    app = _app(FakePhotoLibrary([_record(0)], copies={_record(0).path: [copy]}))

    app.button(key=open_button_key(Path("/photos/IMG_0.DNG"))).click().run()

    assert not app.exception
    assert any(c.value.startswith("Also stored at") for c in app.caption)
    assert str(copy) in [c.value for c in app.code]
    assert [m.value for m in app.metric][3] == "1"  # copies skipped


def test_details_offer_steps_only_within_the_page() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(3)]))

    app.button(key=open_button_key(_record(0).path)).click().run()
    keys = {b.key for b in app.button}
    assert "detail-next" in keys and "detail-previous" not in keys
    assert any("Photo 1 of 3" in c.value for c in app.caption)

    app.button(key=open_button_key(_record(2).path)).click().run()
    keys = {b.key for b in app.button}
    assert "detail-previous" in keys and "detail-next" not in keys
    assert any("Photo 3 of 3" in c.value for c in app.caption)


def test_similar_photos_show_a_bucket_not_a_distance() -> None:
    near = [NearDuplicate(record=_record(1), distance=0)]
    near.append(NearDuplicate(record=_record(2), distance=10))
    app = _app(
        FakePhotoLibrary(
            [_record(i) for i in range(3)], similar={_record(0).path: near}
        )
    )

    app.button(key=open_button_key(_record(0).path)).click().run()

    captions = [c.value for c in app.caption]
    assert "IMG_1.DNG · Identical" in captions
    assert "IMG_2.DNG · Similar" in captions
    assert app.button(key=similar_button_key(_record(1).path))


def test_details_show_the_file_name_first() -> None:
    app = _app(FakePhotoLibrary([_record(0)]))

    app.button(key=open_button_key(_record(0).path)).click().run()

    assert r"**IMG\_0\.DNG** :gray[/photos]" in [m.value for m in app.markdown]


def test_tag_filter_shows_photo_counts() -> None:
    sea = SAMPLE_ANNOTATION.model_copy(update={"tags": ["sea", "sky"]})
    only_sea = SAMPLE_ANNOTATION.model_copy(update={"tags": ["sea"]})
    app = _app(FakePhotoLibrary([_record(0, sea), _record(1, only_sea)]))

    tags = app.multiselect(key=FilterKey.TAGS)
    assert list(tags.options) == ["sea (2)", "sky (1)"]
    tags.select("sea").run()
    assert app.multiselect(key=FilterKey.TAGS).value == ["sea"]  # the plain tag


def test_details_photo_opens_full_screen_on_click(tmp_path: Path) -> None:
    preview = tmp_path / "p0.jpg"
    Image.new("RGB", (40, 30), (60, 120, 200)).save(preview)
    record = _record(0).model_copy(update={"preview_path": preview})
    app = _app(FakePhotoLibrary([record]))

    app.button(key=open_button_key(record.path)).click().run()

    assert app.button(key="detail-zoom-in").label == "Show full screen"
    assert not [b for b in app.button if b.key == "detail-full-screen-close"]


def test_the_star_marks_and_unmarks_a_favorite(tmp_path: Path) -> None:
    preview = tmp_path / "p0.jpg"
    Image.new("RGB", (40, 30), (60, 120, 200)).save(preview)
    record = _record(0).model_copy(update={"preview_path": preview})
    library = FakePhotoLibrary([record])
    app = _app(library)
    # AppTest does not keep a dialog open between runs (a browser does), so
    # the details are reopened from the gallery after each click.
    open_details = app.button(key=open_button_key(record.path))

    open_details.click().run()
    assert app.button(key=FAVORITE_OFF_KEY).label == "Add to favorites"
    app.button(key=FAVORITE_OFF_KEY).click().run()
    assert library.favorites == {record.path}

    app.button(key=open_button_key(record.path)).click().run()
    assert app.button(key=FAVORITE_ON_KEY).label == "Remove from favorites"
    app.button(key=FAVORITE_ON_KEY).click().run()
    assert library.favorites == set()


def test_export_tab_counts_previews_and_offers_a_download() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(3)]))

    assert "**All 3 photos** (no filters set; narrow them in the sidebar)." in [
        m.value for m in app.markdown
    ]
    assert app.segmented_control(key="x_format").value == "xlsx"
    assert any(len(d.value) == 3 for d in app.dataframe if "file_name" in d.value)


def test_the_app_pins_the_multiselect_buttons() -> None:
    # Works around Streamlit's clear-all x missing clicks (see ui/css.py).
    app = _app(FakePhotoLibrary([_record(0)]))

    bodies = [element.proto.body for element in app.get("html")]

    assert PINNED_MULTISELECT_BUTTONS.strip() in bodies
