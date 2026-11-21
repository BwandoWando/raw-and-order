"""Gallery tab: sort, page size, thumbnail grid and pagination."""

import hashlib
from pathlib import Path

import streamlit as st

from my_agent.schemas import PhotoRecord
from my_agent.schemas.query import PAGE_SIZES, PhotoQuery, SortOrder
from my_agent.ui.detail import open_details
from my_agent.ui.formatting import card_caption
from my_agent.ui.grid import grid_shape, thumbnail_px
from my_agent.ui.library import PhotoLibrary

THUMB_KEY_PREFIX = "thumb-"  # container holding the image and the overlay
OPEN_KEY_PREFIX = "thumbopen-"  # the overlay button itself (distinct prefix)
GRID_KEY = "gallery-grid"
# Height of everything on the page that is not the grid (title, tabs, sort
# row, "Showing" caption, pager and page padding), so the grid fills the rest.
# Measured at 371 px with the padding set in .streamlit/config.toml.
CHROME_REM = 23.5
ROW_GAP_REM = 0.25


def thumbnail_css(rows: int) -> str:
    """CSS that sizes tiles so ``rows`` rows fill the rest of the window.

    Each tile is a keyed container holding the image and a transparent, real
    button laid over it. Streamlit gives keyed elements the class
    st-key-<key>, so the overlay is targeted by its own key (the image has a
    hidden fullscreen button too). Being a real button, it is keyboard- and
    screen-reader-accessible.
    """
    tile_height = (
        f"calc((100vh - {CHROME_REM}rem - {rows - 1} * {ROW_GAP_REM}rem) / {rows})"
    )
    return f"""
<style>
.st-key-{GRID_KEY} {{ gap: {ROW_GAP_REM}rem; }}
[class*="st-key-{THUMB_KEY_PREFIX}"] {{ position: relative; }}
[class*="st-key-{THUMB_KEY_PREFIX}"] img {{
    height: {tile_height};
    width: 100%;
    object-fit: cover;
    border-radius: 0.375rem;
    transition: filter 120ms ease-in-out;
}}
[class*="st-key-{THUMB_KEY_PREFIX}"]:hover img {{ filter: brightness(0.85); }}
[class*="st-key-{OPEN_KEY_PREFIX}"] {{
    position: absolute;
    inset: 0;
    z-index: 1;
}}
[class*="st-key-{OPEN_KEY_PREFIX}"] * {{
    width: 100%;
    height: 100%;
}}
[class*="st-key-{OPEN_KEY_PREFIX}"] button {{
    opacity: 0;
    cursor: pointer;
}}
[class*="st-key-{THUMB_KEY_PREFIX}"]:has(button:focus-visible) img {{
    outline: 3px solid #2a78d6;
    outline-offset: 2px;
}}
</style>
"""


SORT_LABELS = {
    SortOrder.CAPTURED_NEWEST: "Capture date, newest first",
    SortOrder.CAPTURED_OLDEST: "Capture date, oldest first",
    SortOrder.PROCESSED_NEWEST: "Recently processed",
}


def render_gallery(filters: PhotoQuery, library: PhotoLibrary) -> None:
    """Draw the gallery for the given filters."""
    sort_col, size_col, _ = st.columns([2, 1, 3])
    sort = sort_col.selectbox(
        "Sort", list(SORT_LABELS), format_func=SORT_LABELS.__getitem__, key="g_sort"
    )
    page_size = size_col.selectbox(
        "Per page", PAGE_SIZES, key="g_page_size", bind="query-params"
    )
    query = filters.model_copy(update={"sort": sort, "page_size": page_size})
    page_number = _current_page(query)
    result = library.search(query.model_copy(update={"page": page_number}))

    if result.total == 0:
        st.info("No photos match these filters.")
        return
    first = (result.page - 1) * result.page_size + 1
    last = first + len(result.items) - 1
    st.caption(f"Showing {first}–{last} of {result.total} photos")
    _grid(result.items, query.page_size, library)
    _pager(result.pages)


def _digest(path: Path | str) -> str:
    return hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:16]


def thumbnail_key(path: Path | str) -> str:
    """Stable key of the container around a photo's thumbnail."""
    return f"{THUMB_KEY_PREFIX}{_digest(path)}"


def open_button_key(path: Path | str) -> str:
    """Stable key of the invisible button laid over a photo's thumbnail."""
    return f"{OPEN_KEY_PREFIX}{_digest(path)}"


def _grid(items: list[PhotoRecord], page_size: int, library: PhotoLibrary) -> None:
    """Thumbnails only, sized so a full page fits the window.

    The shape comes from the page size, not the item count, so a short last
    page keeps the same tile size.
    """
    columns, rows = grid_shape(page_size)
    max_px = thumbnail_px(columns)
    paths = [record.path for record in items]
    st.html(thumbnail_css(rows))
    with st.container(key=GRID_KEY):
        for start in range(0, len(items), columns):
            cells = st.columns(columns, gap="xxsmall")
            for cell, record in zip(
                cells, items[start : start + columns], strict=False
            ):
                with cell:
                    _thumbnail(record, paths, max_px, library)


def _thumbnail(
    record: PhotoRecord, paths: list[Path], max_px: int, library: PhotoLibrary
) -> None:
    """The photo itself, clickable to open its details; caption on hover.

    ``paths`` are the photos on this page, which the details can step through.
    """
    with st.container(key=thumbnail_key(record.path)):
        image = library.thumbnail(record.preview_path, max_px)
        if image is None:
            st.caption("Preview missing")
        else:
            st.image(image, width="stretch")
        label = f"Open details for {record.path.name}"
        if st.button(
            label, key=open_button_key(record.path), help=card_caption(record)
        ):
            open_details(record.path, paths, library)


def _current_page(query: PhotoQuery) -> int:
    """Keep the page number, but go back to page 1 when filters change."""
    signature = query.model_dump_json()
    if st.session_state.get("g_signature") != signature:
        st.session_state["g_signature"] = signature
        st.session_state["g_page"] = 1
    return int(st.session_state.get("g_page", 1))


def _pager(pages: int) -> None:
    if pages <= 1:
        return
    page = int(st.session_state.get("g_page", 1))
    previous, label, following = st.columns([1, 2, 1])
    previous.button(
        "← Previous",
        key="g_prev",
        on_click=_go,
        args=(page - 1,),
        disabled=page <= 1,
        width="stretch",
    )
    label.markdown(
        f"<div style='text-align:center'>Page {page} of {pages}</div>",
        unsafe_allow_html=True,
    )
    following.button(
        "Next →",
        key="g_next",
        on_click=_go,
        args=(page + 1,),
        disabled=page >= pages,
        width="stretch",
    )


def _go(page: int) -> None:
    st.session_state["g_page"] = page
