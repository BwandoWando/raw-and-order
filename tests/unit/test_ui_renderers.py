"""Render the UI against an injected in-memory library (no database)."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from raw_and_order.analysis.tag_graph import build_tag_graph
from raw_and_order.schemas import (
    Annotation,
    ExifData,
    FailureRecord,
    GpsCoordinate,
    PhotoRecord,
    SceneType,
)
from raw_and_order.schemas.query import SimilarPhoto
from raw_and_order.ui.css import PINNED_MULTISELECT_BUTTONS
from raw_and_order.ui.detail import (
    BACKDROP,
    FAVORITE_OFF_KEY,
    FAVORITE_ON_KEY,
    TRASH_OFF_KEY,
    TRASH_ON_KEY,
    similar_button_key,
)
from raw_and_order.ui.filters import FilterKey
from raw_and_order.ui.gallery import (
    CURRENT_PAGE_KEY,
    GalleryKey,
    open_button_key,
    page_button_key,
)
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.ui.navigation import TABS_KEY
from raw_and_order.ui.tags import cluster_open_key, tags_to_show
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


def test_hovering_a_thumbnail_shows_its_name_and_description() -> None:
    app = _app(FakePhotoLibrary([_record(0)]))

    tooltip = app.button(key=open_button_key(_record(0).path)).help

    assert tooltip.startswith(r"**IMG\_0\.DNG**")
    assert SAMPLE_ANNOTATION.description.replace(".", r"\.") in tooltip


def test_the_pager_shows_ten_page_numbers_and_jumps_to_one() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(300)]))  # 13 pages

    numbers = [b.label for b in app.button if (b.key or "").startswith("g-page-")]
    assert numbers == [str(n) for n in range(1, 11)]
    assert app.button(key=CURRENT_PAGE_KEY).label == "1"
    assert app.button(key=GalleryKey.PREVIOUS).disabled

    app.button(key=page_button_key(9)).click().run()

    assert "Showing 193–216 of 300 photos" in [c.value for c in app.caption]
    assert app.button(key=CURRENT_PAGE_KEY).label == "9"
    numbers = [b.label for b in app.button if (b.key or "").startswith("g-page-")]
    assert numbers == [str(n) for n in range(4, 14)]  # slid to keep 9 central


def test_the_pager_arrows_stop_at_the_last_page() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))  # 2 pages

    app.button(key=GalleryKey.NEXT).click().run()

    assert app.button(key=CURRENT_PAGE_KEY).label == "2"
    assert app.button(key=GalleryKey.NEXT).disabled
    assert not app.button(key=GalleryKey.PREVIOUS).disabled


def test_a_single_page_has_no_pager() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(3)]))

    assert not [b for b in app.button if (b.key or "").startswith("g-page-")]


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


def _with_previews(photos: list[PhotoRecord], folder: Path) -> list[PhotoRecord]:
    """``photos`` with a small real preview each, so thumbnails can be made."""
    saved = []
    for i, photo in enumerate(photos):
        preview = folder / f"p{i}.jpg"
        Image.new("RGB", (40, 30), (40 * i % 255, 90, 160)).save(preview)
        saved.append(photo.model_copy(update={"preview_path": preview}))
    return saved


def test_hovering_a_tag_shows_a_grid_of_its_photos(tmp_path: Path) -> None:
    photos = [_tagged(i, "city", "night", "neon") for i in range(12)]
    app = _app(FakePhotoLibrary(_with_previews(photos, tmp_path)))

    spec = json.loads(app.tabs[1].get("echarts_chart")[0].proto.spec)

    nodes = {node["name"]: node for node in spec["series"][0]["data"]}
    tooltip = nodes["city"]["tooltip"]["formatter"]
    assert tooltip.startswith("<b>city</b>: 12 photos")
    assert tooltip.count("data:image/jpeg;base64,") == 9


def test_the_tag_photos_hold_still_between_reruns(tmp_path: Path) -> None:
    photos = [_tagged(i, "city", "night") for i in range(12)]
    app = _app(FakePhotoLibrary(_with_previews(photos, tmp_path)))
    first = app.tabs[1].get("echarts_chart")[0].proto.spec

    app.run()

    assert app.tabs[1].get("echarts_chart")[0].proto.spec == first


def test_cluster_cards_show_a_photo_for_each_tag_in_the_name(tmp_path: Path) -> None:
    photos = [_tagged(i, "city", "night", "neon") for i in range(3)]
    photos += [_tagged(i + 3, "sea", "sand") for i in range(3)]
    app = _app(FakePhotoLibrary(_with_previews(photos, tmp_path)))

    html = "".join(h.proto.body for h in app.tabs[1].get("html"))
    alts = re.findall(r'<img src="data:image/jpeg;base64,[^"]+" alt="([^"]+)"', html)

    assert not app.tabs[1].get("image")  # st.image would add a full-screen button
    assert alts == [
        "A photo tagged city",
        "A photo tagged neon",
        "A photo tagged night",
        "A photo tagged sand",
        "A photo tagged sea",
    ]


def test_cluster_cards_without_previews_show_only_text() -> None:
    photos = [_tagged(i, "city", "night") for i in range(3)]  # previews missing
    app = _app(FakePhotoLibrary(photos))

    assert "<img" not in "".join(h.proto.body for h in app.tabs[1].get("html"))
    assert "**city · night**" in [m.value for m in app.tabs[1].markdown]


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


def _shown_position(app: AppTest) -> str:
    """The "Photo N of M on this page" part of the details caption."""
    caption = next(c.value for c in app.caption if "on this page" in c.value)
    return caption.rsplit(" · ", 1)[-1]


def test_next_on_the_last_photo_of_a_page_shows_the_next_page_first() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))  # pages of 24

    app.button(key=open_button_key(_record(23).path)).click().run()
    app.button(key="detail-next").click().run()

    # The dialog loaded page 2 itself; the gallery behind is still on page 1.
    assert not app.exception, app.exception
    assert r"**IMG\_24\.DNG** :gray[/photos]" in [m.value for m in app.markdown]
    assert _shown_position(app) == "Photo 1 of 6 on this page"
    assert "Showing 1–24 of 30 photos" in [c.value for c in app.caption]

    app.run()  # the next full run (e.g. closing the dialog): the gallery follows

    assert "Showing 25–30 of 30 photos" in [c.value for c in app.caption]
    assert _shown_position(app) == "Photo 1 of 6 on this page"  # still open


def test_previous_on_the_first_photo_of_a_page_shows_the_previous_page_last() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))
    app.button(key=GalleryKey.NEXT).click().run()

    app.button(key=open_button_key(_record(24).path)).click().run()
    app.button(key="detail-previous").click().run()

    assert not app.exception, app.exception
    assert r"**IMG\_23\.DNG** :gray[/photos]" in [m.value for m in app.markdown]
    assert _shown_position(app) == "Photo 24 of 24 on this page"
    app.run()
    assert "Showing 1–24 of 30 photos" in [c.value for c in app.caption]


def test_no_step_past_the_first_or_last_photo_of_all_pages() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(30)]))

    app.button(key=open_button_key(_record(0).path)).click().run()
    assert "detail-previous" not in {b.key for b in app.button}

    app.button(key=GalleryKey.NEXT).click().run()
    app.button(key=open_button_key(_record(29).path)).click().run()
    assert "detail-next" not in {b.key for b in app.button}


def test_a_similar_photo_on_another_page_opens_on_its_page() -> None:
    records = [_record(i) for i in range(30)]  # pages of 24
    similar = {records[0].path: [SimilarPhoto(record=records[27], distance=1)]}
    app = _app(FakePhotoLibrary(records, similar=similar))

    app.button(key=open_button_key(records[0].path)).click().run()
    app.button(key=similar_button_key(records[27].path)).click().run()

    assert not app.exception, app.exception
    assert r"**IMG\_27\.DNG** :gray[/photos]" in [m.value for m in app.markdown]
    assert _shown_position(app) == "Photo 4 of 6 on this page"
    keys = {b.key for b in app.button}
    assert "detail-previous" in keys and "detail-next" in keys
    app.run()
    assert "Showing 25–30 of 30 photos" in [c.value for c in app.caption]


def test_the_open_dialog_survives_a_full_rerun_and_closing_ends_it() -> None:
    app = _app(FakePhotoLibrary([_record(i) for i in range(3)]))
    app.button(key=open_button_key(_record(1).path)).click().run()

    app.run()  # a full rerun with no click: the dialog is drawn again in place

    assert _shown_position(app) == "Photo 2 of 3 on this page"
    app.session_state["detail_open"] = False  # what dismissing the dialog sets
    app.run()
    assert not [c for c in app.caption if "on this page" in c.value]


def test_similar_photos_hidden_by_the_filters_are_not_offered() -> None:
    street = SAMPLE_ANNOTATION.model_copy(update={"scene": SceneType.STREET})
    records = [_record(0), _record(1), _record(2, street)]
    similar = {
        records[0].path: [
            SimilarPhoto(record=records[1], distance=1),
            SimilarPhoto(record=records[2], distance=1),
        ]
    }
    app = _app(FakePhotoLibrary(records, similar=similar))
    app.multiselect(key=FilterKey.SCENES).select(SAMPLE_ANNOTATION.scene.value).run()

    app.button(key=open_button_key(records[0].path)).click().run()

    keys = {b.key for b in app.button}
    assert similar_button_key(records[1].path) in keys
    assert similar_button_key(records[2].path) not in keys


def test_similar_photos_show_a_bucket_not_a_distance() -> None:
    similar = [SimilarPhoto(record=_record(1), distance=0)]
    similar.append(SimilarPhoto(record=_record(2), distance=10))
    app = _app(
        FakePhotoLibrary(
            [_record(i) for i in range(3)], similar={_record(0).path: similar}
        )
    )

    app.button(key=open_button_key(_record(0).path)).click().run()

    captions = [c.value for c in app.caption]
    assert "IMG_1.DNG · Identical" in captions
    assert "IMG_2.DNG · Similar" in captions
    assert app.button(key=similar_button_key(_record(1).path))


def test_details_dim_the_app_behind_them() -> None:
    app = _app(FakePhotoLibrary([_record(0)]))
    assert not any(BACKDROP in h.proto.body for h in app.get("html"))

    app.button(key=open_button_key(_record(0).path)).click().run()

    assert any(BACKDROP in h.proto.body for h in app.get("html"))


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

    app.button(key=open_button_key(record.path)).click().run()
    assert app.button(key=FAVORITE_OFF_KEY).label == "Add to favorites"
    app.button(key=FAVORITE_OFF_KEY).click().run()
    assert library.favorites == {record.path}

    # The dialog stays open across the rerun, now showing the filled star.
    assert app.button(key=FAVORITE_ON_KEY).label == "Remove from favorites"
    app.button(key=FAVORITE_ON_KEY).click().run()
    assert library.favorites == set()


def test_the_bin_and_the_delete_key_mark_and_unmark_for_deletion(
    tmp_path: Path,
) -> None:
    preview = tmp_path / "p0.jpg"
    Image.new("RGB", (40, 30), (60, 120, 200)).save(preview)
    record = _record(0).model_copy(update={"preview_path": preview})
    library = FakePhotoLibrary([record])
    app = _app(library)
    app.button(key=open_button_key(record.path)).click().run()

    bin_button = app.button(key=TRASH_OFF_KEY)
    assert bin_button.label == "Mark for deletion"
    assert bin_button.proto.shortcut.lower() == "delete"  # the key presses it

    bin_button.click().run()  # first press: marked
    assert library.trashed == {record.path}
    marked = app.button(key=TRASH_ON_KEY)
    assert marked.label == "Unmark for deletion"
    assert marked.proto.shortcut.lower() == "delete"

    marked.click().run()  # second press: back to normal
    assert library.trashed == set()
    assert app.button(key=TRASH_OFF_KEY).label == "Mark for deletion"
    assert library.favorites == set()  # the star is untouched


def test_marked_for_deletion_only_lists_the_marked_photos(tmp_path: Path) -> None:
    library = FakePhotoLibrary(_with_previews([_record(i) for i in range(5)], tmp_path))
    app = _app(library)
    app.button(key=open_button_key(_record(3).path)).click().run()
    app.button(key=TRASH_OFF_KEY).click().run()

    app.toggle(key=FilterKey.TRASHED).set_value(True).run()

    assert not app.exception, app.exception
    assert "Showing 1–1 of 1 photos" in [c.value for c in app.caption]
    assert app.button(key=open_button_key(_record(3).path))


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


def test_clicking_a_cluster_shows_its_photos_in_the_gallery() -> None:
    photos = [_tagged(i, "city", "night", "neon") for i in range(3)]
    photos += [_tagged(i + 3, "sea", "sand") for i in range(3)]
    app = _app(FakePhotoLibrary(photos))

    app.button(key=cluster_open_key(0)).click().run()

    assert app.multiselect(key=FilterKey.TAGS).value == ["city", "neon", "night"]
    assert app.session_state[TABS_KEY] == "Gallery"


def test_a_clicked_tag_shows_its_cluster_or_just_itself() -> None:
    city = ["city", "night", "neon", "rain"]
    tag_lists = [city] * 3 + [["city", "night", "neon"]] + [["sea", "sand"]] * 3
    graph = build_tag_graph([*tag_lists, ["dog"]], top_n=10, min_strength=0.15)
    index = {node.tag: i for i, node in enumerate(graph.nodes)}

    # The tags in the cluster's name (its biggest three), not "rain" as well.
    assert tags_to_show(graph, index["rain"]) == ["city", "neon", "night"]
    assert tags_to_show(graph, index["dog"]) == ["dog"]  # in no cluster


class _PhotoDeletedLibrary(FakePhotoLibrary):
    """Lists the photo in the gallery, but it is gone when the details open."""

    def photo(self, path: Path) -> PhotoRecord | None:
        return None


def test_details_of_a_deleted_photo_say_so_once() -> None:
    app = _app(_PhotoDeletedLibrary([_record(0)]))

    app.button(key=open_button_key(_record(0).path)).click().run()

    assert [w.value for w in app.warning] == [
        "This photo is no longer in the database."
    ]
    assert not [i for i in app.info if "Preview file not found" in i.value]
