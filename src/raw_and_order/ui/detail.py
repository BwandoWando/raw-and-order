"""Pop-up with everything known about one photo, sized to fit one screen.

Under the file name, the photo sits on the left and its description, tags
and camera settings on the right. The longer sections (similar photos,
location, files) sit in tabs below, full width, so nothing needs scrolling
on a normal screen. Buttons either side of the photo (and the arrow keys)
step to the previous or next photo shown in the gallery without closing the
dialog. Clicking a similar photo shows it here; it can only be stepped from
if it is on the gallery page too. Clicking the photo shows its preview full
screen, on a layer over the dialog (Streamlit allows only one dialog at a
time).
"""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from raw_and_order.analysis.similarity import similarity
from raw_and_order.schemas import ExifData, PhotoRecord
from raw_and_order.schemas.query import SimilarPhoto
from raw_and_order.ui.css import (
    clickable_tile,
    keyed,
    keyed_prefix,
    visually_hidden,
)
from raw_and_order.ui.formatting import (
    camera_settings,
    capture_label,
    date_source_label,
    escape_markdown,
    path_digest,
)
from raw_and_order.ui.library import PhotoLibrary

SIMILAR_COLUMNS = 6
TAB_HEIGHT_PX = 130  # fits a row of similar photos with captions
PHOTO_KEY = "detail-photo"
FRAME_KEY = "detail-frame"
TEXT_KEY = "detail-text"  # description, tags and camera settings
PREVIOUS_KEY = "detail-previous"
NEXT_KEY = "detail-next"
SIMILAR_KEY = "detail-similar"
SIMILAR_TILE_PREFIX = "detail-sim-"  # image plus overlay button
# The overlay's prefix must not contain the tile's: the CSS selects tiles with
# [class*="st-key-detail-sim-"], which would also match "detail-sim-open-".
SIMILAR_OPEN_PREFIX = "detail-simopen-"  # the overlay button
STEP_BUTTON_PX = 44
CURRENT_KEY = "detail_current"  # session state: path of the photo shown
OPEN_KEY = "detail_open"  # session state: True while the dialog is open
ZOOM_KEY = "detail_zoom"  # session state: True while the photo is full screen
ZOOM_TARGET_KEY = "detail-zoom-target"  # the photo plus its zoom-in button
# The star in the photo's top-right corner; one key per state, for the CSS.
FAVORITE_PREFIX = "detail-favorite-"
FAVORITE_ON_KEY = f"{FAVORITE_PREFIX}on"
FAVORITE_OFF_KEY = f"{FAVORITE_PREFIX}off"
FAVORITE_GOLD = "#f5c518"
ZOOM_IN_KEY = "detail-zoom-in"
FULL_SCREEN_KEY = "detail-full-screen"
ZOOM_OUT_KEY = "detail-zoom-out"  # click anywhere on the full-screen photo
CLOSE_FULL_SCREEN_KEY = "detail-full-screen-close"  # the visible x
FULL_SCREEN_Z = 1_000_100  # above Streamlit's dialog
# Room left for the dialog title, file name and tabs (the description and
# camera settings sit beside the photo, so they take no height).
CHROME_REM = 30
# The photo row's fixed height, so the dialog keeps its size from photo to
# photo: portrait and landscape photos fit inside it, and longer text scrolls.
PHOTO_ROW_HEIGHT = f"max(7rem, calc(100vh - {CHROME_REM}rem))"
# Widths of the photo and text columns. Portrait photos are narrow, so the
# text gets more of the width beside them.
LANDSCAPE_SHARE = (3, 2)
PORTRAIT_SHARE = (2, 3)

_LABEL = '[data-testid="stMarkdownContainer"]'  # a button's text label
# Icon-only buttons: their label (and shortcut hint) stays for screen readers.
_ICON_ONLY_BUTTONS = visually_hidden(
    f"{keyed(PREVIOUS_KEY)} {_LABEL}",
    f"{keyed(NEXT_KEY)} {_LABEL}",
    f"{keyed(PREVIOUS_KEY)} kbd",
    f"{keyed(NEXT_KEY)} kbd",
    f"{keyed(CLOSE_FULL_SCREEN_KEY)} {_LABEL}",
    f"{keyed_prefix(FAVORITE_PREFIX)} {_LABEL}",
)
_SIMILAR_TILES = clickable_tile(
    keyed_prefix(SIMILAR_TILE_PREFIX), keyed_prefix(SIMILAR_OPEN_PREFIX)
)

DETAIL_CSS = f"""
<style>
/* min-height, not height: Streamlit sizes this flex item with flex-basis. */
.st-key-{PHOTO_KEY} {{ min-height: {PHOTO_ROW_HEIGHT}; }}
.st-key-{TEXT_KEY} {{
    max-height: {PHOTO_ROW_HEIGHT};
    overflow-y: auto;
}}
.st-key-{FRAME_KEY} img {{
    max-height: {PHOTO_ROW_HEIGHT};
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
.st-key-{SIMILAR_KEY} img {{
    height: 4.5rem;
    object-fit: cover;
    border-radius: 0.25rem;
    transition: filter 120ms ease-in-out;
}}
{_SIMILAR_TILES}
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
/* The favorite star: over the photo's top-right corner, above the zoom-in
   button laid over the whole photo. */
{keyed_prefix(FAVORITE_PREFIX)} {{
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    z-index: 2;
    width: auto;
}}
{keyed_prefix(FAVORITE_PREFIX)} button {{
    width: {STEP_BUTTON_PX}px;
    height: {STEP_BUTTON_PX}px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.45);
    color: #fff;
}}
{keyed_prefix(FAVORITE_PREFIX)} button:hover {{ background: rgba(0, 0, 0, 0.65); }}
/* The star is a text character, so it can be outlined or filled (the icon
   font has no filled star). Its label stays for screen readers. */
{keyed_prefix(FAVORITE_PREFIX)} button::before {{
    font-size: 1.5rem;
    line-height: 1;
}}
.st-key-{FAVORITE_OFF_KEY} button::before {{ content: "☆"; }}
.st-key-{FAVORITE_ON_KEY} button::before {{
    content: "★";
    color: {FAVORITE_GOLD};
}}
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
{_ICON_ONLY_BUTTONS}
</style>
"""


def column_share(size: tuple[int, int] | None) -> tuple[int, int]:
    """Photo and text column widths for a preview of ``size`` (width, height).

    Portrait photos get the narrow column; landscape, square and unknown
    sizes get the wide one.
    """
    if size is not None and size[1] > size[0]:
        return PORTRAIT_SHARE
    return LANDSCAPE_SHARE


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
    size = library.preview_size(record.preview_path) if record else None
    photo_column, text_column = st.columns(column_share(size), gap="medium")
    with photo_column:
        _stepper(paths, current, record, library)
    if record is not None and st.session_state.get(ZOOM_KEY):
        _full_screen(record.preview_path)
    if record is None:
        st.warning("This photo is no longer in the database.")
        return
    with text_column, st.container(key=TEXT_KEY):
        position = paths.index(current) + 1 if current in paths else 0
        _summary(record, position, len(paths))
        _camera(record.exif, size)
    _sections(record, library)


def _stepper(
    paths: tuple[Path, ...],
    current: Path,
    record: PhotoRecord | None,
    library: PhotoLibrary,
) -> None:
    """The photo between its previous and next buttons."""
    previous, following = neighbours(paths, current)
    with st.container(
        key=PHOTO_KEY, horizontal=True, vertical_alignment="center", gap="small"
    ):
        _step_button("Previous photo", previous, PREVIOUS_KEY, "chevron_left", "Left")
        with st.container(key=FRAME_KEY, horizontal_alignment="center"):
            _photo(record, library)
        _step_button("Next photo", following, NEXT_KEY, "chevron_right", "Right")


def _step_button(
    label: str, target: Path | None, key: str, icon: str, shortcut: str
) -> None:
    """A round button beside the photo, shown on hover; also an arrow key.

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


def _photo(record: PhotoRecord | None, library: PhotoLibrary) -> None:
    """The preview with its favorite star; clicking the photo shows it full screen."""
    if record is None or not record.preview_path.is_file():
        st.info("Preview file not found.")
        return
    with st.container(key=ZOOM_TARGET_KEY, width="content"):
        st.image(str(record.preview_path), width="content")
        st.button("Show full screen", key=ZOOM_IN_KEY, on_click=_zoom, args=(True,))
        _favorite_star(record.path, library)


def _favorite_star(path: Path, library: PhotoLibrary) -> None:
    """A star that marks the photo as a favorite, or unmarks it, on click.

    Filled and gold for a favorite, outlined otherwise (drawn by the CSS);
    the label (read by screen readers, shown as a tooltip) says what a click
    will do.
    """
    favorite = library.is_favorite(path)
    label = "Remove from favorites" if favorite else "Add to favorites"
    st.button(
        label,
        key=FAVORITE_ON_KEY if favorite else FAVORITE_OFF_KEY,
        help=label,
        on_click=library.set_favorite,
        args=(path, not favorite),
    )


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


def _camera(exif: ExifData, preview_size: tuple[int, int] | None) -> None:
    rows = camera_settings(exif, preview_size)
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
        _similar_photos(record.path, library)
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


def _similar_photos(path: Path, library: PhotoLibrary) -> None:
    """Up to a row of similar photos; clicking one shows it in this dialog."""
    matches = library.similar_photos(path)[:SIMILAR_COLUMNS]
    if not matches:
        st.caption("No similar photos found.")
        return
    with st.container(key=SIMILAR_KEY):
        columns = st.columns(SIMILAR_COLUMNS, gap="small")
        for column, match in zip(columns, matches, strict=False):
            with column:
                _similar_tile(match)


def _similar_tile(match: SimilarPhoto) -> None:
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
