"""Pop-up with everything known about one photo, sized to fit one screen.

The photo comes first, then its description and camera settings. The longer
sections (similar photos, location, files) sit in tabs below, so nothing
needs scrolling on a normal screen. Buttons at the dialog's left and right
edges (and the arrow keys) step to the previous or next photo shown in the
gallery without closing the dialog. Clicking a similar photo shows it here;
it can only be stepped from if it is on the gallery page too. Clicking the
photo shows its preview full screen, on a layer over the dialog (Streamlit
allows only one dialog at a time).
"""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from raw_and_order.analysis.similarity import similarity
from raw_and_order.schemas import ExifData, PhotoRecord
from raw_and_order.schemas.query import NearDuplicate
from raw_and_order.ui.formatting import (
    camera_settings,
    capture_label,
    date_source_label,
    escape_markdown,
    path_digest,
)
from raw_and_order.ui.library import PhotoLibrary

DUPLICATE_COLUMNS = 6
TAB_HEIGHT_PX = 130  # fits a row of similar photos with captions
PHOTO_KEY = "detail-photo"
FRAME_KEY = "detail-frame"
PREVIOUS_KEY = "detail-previous"
NEXT_KEY = "detail-next"
SIMILAR_KEY = "detail-similar"
SIMILAR_TILE_PREFIX = "detail-sim-"  # image plus overlay button
SIMILAR_OPEN_PREFIX = "detail-simopen-"  # the overlay button (distinct prefix)
STEP_BUTTON_PX = 44
CURRENT_KEY = "detail_current"  # session state: path of the photo shown
OPEN_KEY = "detail_open"  # session state: True while the dialog is open
ZOOM_KEY = "detail_zoom"  # session state: True while the photo is full screen
ZOOM_TARGET_KEY = "detail-zoom-target"  # the photo plus its zoom-in button
ZOOM_IN_KEY = "detail-zoom-in"
FULL_SCREEN_KEY = "detail-full-screen"
ZOOM_OUT_KEY = "detail-zoom-out"  # click anywhere on the full-screen photo
CLOSE_FULL_SCREEN_KEY = "detail-full-screen-close"  # the visible x
FULL_SCREEN_Z = 1_000_100  # above Streamlit's dialog
# Room left for the dialog title, summary, camera row and tabs.
CHROME_REM = 41.5

DETAIL_CSS = f"""
<style>
.st-key-{FRAME_KEY} img {{
    max-height: calc(100vh - {CHROME_REM}rem);
    min-height: 7rem;
    width: auto !important;
    max-width: 100%;
    object-fit: contain;
    border-radius: 0.375rem;
}}
.st-key-{PREVIOUS_KEY}, .st-key-{NEXT_KEY} {{
    opacity: 0;
    transition: opacity 150ms ease-in-out;
}}
.st-key-{PHOTO_KEY}:hover .st-key-{PREVIOUS_KEY},
.st-key-{PHOTO_KEY}:hover .st-key-{NEXT_KEY},
.st-key-{PREVIOUS_KEY}:focus-within,
.st-key-{NEXT_KEY}:focus-within {{ opacity: 1; }}
.st-key-{PREVIOUS_KEY} button, .st-key-{NEXT_KEY} button {{
    width: {STEP_BUTTON_PX}px;
    height: {STEP_BUTTON_PX}px;
    border-radius: 50%;
}}
/* Icon-only look; label and shortcut stay readable by screen readers. */
.st-key-{PREVIOUS_KEY} [data-testid="stMarkdownContainer"],
.st-key-{NEXT_KEY} [data-testid="stMarkdownContainer"],
.st-key-{PREVIOUS_KEY} kbd,
.st-key-{NEXT_KEY} kbd {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
}}
.st-key-{SIMILAR_KEY} img {{
    height: 4.5rem;
    object-fit: cover;
    border-radius: 0.25rem;
    transition: filter 120ms ease-in-out;
}}
[class*="st-key-{SIMILAR_TILE_PREFIX}"] {{ position: relative; }}
[class*="st-key-{SIMILAR_TILE_PREFIX}"]:hover img {{ filter: brightness(0.85); }}
[class*="st-key-{SIMILAR_OPEN_PREFIX}"] {{
    position: absolute;
    inset: 0;
    z-index: 1;
}}
[class*="st-key-{SIMILAR_OPEN_PREFIX}"] * {{
    width: 100%;
    height: 100%;
}}
[class*="st-key-{SIMILAR_OPEN_PREFIX}"] button {{
    opacity: 0;
    cursor: pointer;
}}
[class*="st-key-{SIMILAR_TILE_PREFIX}"]:has(button:focus-visible) img {{
    outline: 3px solid #2a78d6;
    outline-offset: 2px;
}}
.st-key-{ZOOM_TARGET_KEY} {{ position: relative; }}
.st-key-{ZOOM_IN_KEY}, .st-key-{ZOOM_OUT_KEY} {{
    position: absolute;
    inset: 0;
    z-index: 1;
    width: 100% !important;  /* Streamlit sizes button wrappers to content */
    height: 100% !important;
}}
.st-key-{ZOOM_IN_KEY} *, .st-key-{ZOOM_OUT_KEY} * {{
    width: 100%;
    height: 100%;
}}
.st-key-{ZOOM_IN_KEY} button, .st-key-{ZOOM_OUT_KEY} button {{
    opacity: 0;
    cursor: zoom-in;
}}
.st-key-{ZOOM_OUT_KEY} button {{ cursor: zoom-out; }}
.st-key-{FULL_SCREEN_KEY} {{
    position: fixed;
    inset: 0;
    z-index: {FULL_SCREEN_Z};
    background: rgba(0, 0, 0, 0.92);
    display: flex;
    align-items: center;
    justify-content: center;
}}
.st-key-{FULL_SCREEN_KEY} [data-testid="stImage"],
.st-key-{FULL_SCREEN_KEY} [data-testid="stImage"] * {{
    width: 100vw;
    height: 100vh;
}}
.st-key-{FULL_SCREEN_KEY} img {{
    width: 100vw !important;
    height: 100vh !important;
    max-width: none;
    object-fit: contain;  /* as large as fits, no scrolling */
}}
.st-key-{ZOOM_OUT_KEY} {{ position: fixed; }}
.st-key-{CLOSE_FULL_SCREEN_KEY} {{
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 2;
    width: auto;
}}
.st-key-{CLOSE_FULL_SCREEN_KEY} button {{
    width: {STEP_BUTTON_PX}px;
    height: {STEP_BUTTON_PX}px;
    border-radius: 50%;
    border: none;
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
}}
.st-key-{CLOSE_FULL_SCREEN_KEY} button:hover {{
    background: rgba(255, 255, 255, 0.3);
    color: #fff;
}}
.st-key-{CLOSE_FULL_SCREEN_KEY} [data-testid="stMarkdownContainer"] {{
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
}}
</style>
"""


def neighbours(paths: Sequence[Path], current: Path) -> tuple[Path | None, Path | None]:
    """The photos before and after ``current`` in ``paths`` (None at the ends)."""
    if current not in paths:
        return None, None
    index = paths.index(current)
    previous = paths[index - 1] if index > 0 else None
    following = paths[index + 1] if index + 1 < len(paths) else None
    return previous, following


def open_details(path: Path, paths: Sequence[Path], library: PhotoLibrary) -> None:
    """Open the details of ``path``; ``paths`` are the photos one can step to.

    Pass the photos shown in the gallery (current filters, sort and page), so
    the dialog never steps to a photo the gallery does not show.
    """
    st.session_state[CURRENT_KEY] = str(path)
    st.session_state[OPEN_KEY] = True
    st.session_state[ZOOM_KEY] = False
    _details(tuple(paths), library)


def details_open() -> bool:
    """True while the photo details are open (they own the arrow keys then)."""
    return bool(st.session_state.get(OPEN_KEY, False))


def _closed() -> None:
    st.session_state[OPEN_KEY] = False
    st.session_state[ZOOM_KEY] = False


@st.dialog("Photo details", width="large", on_dismiss=_closed)
def _details(paths: tuple[Path, ...], library: PhotoLibrary) -> None:
    """Render the current photo. The step buttons rerun only this dialog."""
    current = Path(st.session_state[CURRENT_KEY])
    record = library.photo(current)
    st.html(DETAIL_CSS)
    _file_heading(current)
    previous, following = neighbours(paths, current)
    with st.container(
        key=PHOTO_KEY, horizontal=True, vertical_alignment="center", gap="small"
    ):
        _step_button("Previous photo", previous, PREVIOUS_KEY, "chevron_left", "Left")
        with st.container(key=FRAME_KEY, horizontal_alignment="center"):
            _photo(record.preview_path if record else None)
        _step_button("Next photo", following, NEXT_KEY, "chevron_right", "Right")
    if record is not None and st.session_state.get(ZOOM_KEY):
        _full_screen(record.preview_path)
    if record is None:
        st.warning("This photo is no longer in the database.")
        return
    _summary(record, paths.index(current) + 1 if current in paths else 0, len(paths))
    _camera(record.exif)
    _sections(record, library)


def _step_button(
    label: str, target: Path | None, key: str, icon: str, shortcut: str
) -> None:
    """A round button at the dialog's edge, shown on hover; also an arrow key.

    Past either end there is no button, only a spacer of the same width, so
    the photo stays centred.
    """
    if target is None:
        st.space(STEP_BUTTON_PX)
        return
    st.button(
        label,
        key=key,
        icon=f":material/{icon}:",
        shortcut=shortcut,
        on_click=_show,
        args=(target,),
    )


def _file_heading(path: Path) -> None:
    """The file name in bold with its folder after it, above the photo."""
    st.markdown(
        f"**{escape_markdown(path.name)}** :gray[{escape_markdown(str(path.parent))}]"
    )


def _show(path: Path) -> None:
    st.session_state[CURRENT_KEY] = str(path)


def _photo(preview_path: Path | None) -> None:
    """The preview; clicking it shows it full screen."""
    if preview_path is None or not preview_path.is_file():
        st.info("Preview file not found.")
        return
    with st.container(key=ZOOM_TARGET_KEY, width="content"):
        st.image(str(preview_path), width="content")
        st.button("Show full screen", key=ZOOM_IN_KEY, on_click=_zoom, args=(True,))


def _full_screen(preview_path: Path) -> None:
    """The preview as large as the window allows, over the dialog.

    A click on it or the x closes it; the arrow keys keep stepping photos.
    """
    if not preview_path.is_file():
        return
    with st.container(key=FULL_SCREEN_KEY):
        st.image(str(preview_path), width="content")
        st.button("Close full screen", key=ZOOM_OUT_KEY, on_click=_zoom, args=(False,))
        st.button(
            "Close full screen",
            key=CLOSE_FULL_SCREEN_KEY,
            icon=":material/close:",
            on_click=_zoom,
            args=(False,),
        )


def _zoom(full_screen: bool) -> None:
    st.session_state[ZOOM_KEY] = full_screen


def _summary(record: PhotoRecord, position: int, count: int) -> None:
    annotation = record.annotation
    st.markdown(f"**{annotation.description}**")
    st.markdown(" ".join(f"`{tag}`" for tag in annotation.tags) or "_No tags_")
    people = "yes" if annotation.contains_people else "no"
    source = date_source_label(record.exif.date_source)
    st.caption(
        f"Scene: {annotation.scene.value} · People: {people} · "
        f"Taken {capture_label(record)} (from {source}) · "
        f"Annotated by {record.annotated_by}"
        + (f" · Photo {position} of {count} on this page" if position else "")
    )


def _camera(exif: ExifData) -> None:
    rows = camera_settings(exif)
    if not rows:
        return
    with st.container(horizontal=True, gap="small"):
        for label, value in rows:
            st.markdown(f":small[:gray[{label}] **{value}**]", width="content")


def _sections(record: PhotoRecord, library: PhotoLibrary) -> None:
    """Tabs of equal height, so switching tabs never resizes the dialog."""
    names = ["Similar photos", "Files"]
    if record.exif.gps is not None:
        names.insert(1, "Location")
    tabs = dict(zip(names, st.tabs(names), strict=True))
    with tabs["Similar photos"], _panel():
        _near_duplicates(record.path, library)
    if "Location" in tabs:
        with tabs["Location"], _panel():
            _location(record)
    with tabs["Files"], _panel():
        _files(record, library.copies_of(record.path))


def _panel() -> DeltaGenerator:
    """A fixed-height tab body; longer content scrolls inside it."""
    return st.container(height=TAB_HEIGHT_PX, border=False)


def _location(record: PhotoRecord) -> None:
    gps = record.exif.gps
    if gps is None:
        return
    map_column, text_column = st.columns([4, 1])
    with map_column:
        st.map(
            pd.DataFrame({"lat": [gps.latitude], "lon": [gps.longitude]}),
            zoom=11,
            height=TAB_HEIGHT_PX,
        )
    with text_column:
        st.caption(f"{gps.latitude:.5f}, {gps.longitude:.5f}")


def _files(record: PhotoRecord, copies: list[Path]) -> None:
    st.code(
        f"File     {record.path}\n"
        f"SHA-256  {record.sha256 or '-'}\n"
        f"pHash    {record.phash or '-'}",
        language=None,
    )
    if copies:
        st.caption("Also stored at (exact copies, same SHA-256; not annotated again)")
        st.code("\n".join(str(p) for p in copies), language=None)


def _near_duplicates(path: Path, library: PhotoLibrary) -> None:
    """Up to a row of similar photos; clicking one shows it in this dialog."""
    matches = library.near_duplicates(path)[:DUPLICATE_COLUMNS]
    if not matches:
        st.caption("No similar photos found.")
        return
    with st.container(key=SIMILAR_KEY):
        columns = st.columns(DUPLICATE_COLUMNS, gap="small")
        for column, match in zip(columns, matches, strict=False):
            with column:
                _similar_tile(match)


def _similar_tile(match: NearDuplicate) -> None:
    record = match.record
    with st.container(key=f"{SIMILAR_TILE_PREFIX}{path_digest(record.path)}"):
        if record.preview_path.is_file():
            st.image(str(record.preview_path), width="stretch")
        st.button(
            f"Show {record.path.name}",
            key=similar_button_key(record.path),
            on_click=_show,
            args=(record.path,),
        )
    st.caption(f"{record.path.name} · {similarity(match.distance)}")


def similar_button_key(path: Path | str) -> str:
    """Stable key of the invisible button over a similar photo."""
    return f"{SIMILAR_OPEN_PREFIX}{path_digest(path)}"
