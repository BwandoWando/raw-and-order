"""Gallery tab: sort, page size, thumbnail grid and pagination."""

import hashlib
from pathlib import Path

import streamlit as st

from my_agent.schemas import PhotoRecord
from my_agent.schemas.query import PAGE_SIZES, PhotoQuery, SortOrder
from my_agent.ui import services
from my_agent.ui.detail import show_details
from my_agent.ui.formatting import card_caption

GRID_COLUMNS = 4
THUMB_KEY_PREFIX = "thumb-"  # container holding the image and the overlay
OPEN_KEY_PREFIX = "thumbopen-"  # the overlay button itself (distinct prefix)

# Makes each thumbnail clickable: a transparent, real button is laid over the
# image inside a keyed container. Streamlit gives keyed elements the class
# st-key-<key>, so the overlay is targeted by its own key (the image element
# has a hidden fullscreen button too, so "contains a button" is not enough).
# Being a real button, it is keyboard- and screen-reader-accessible.
THUMBNAIL_CSS = f"""
<style>
[class*="st-key-{THUMB_KEY_PREFIX}"] {{ position: relative; }}
[class*="st-key-{THUMB_KEY_PREFIX}"] img {{ transition: filter 120ms ease-in-out; }}
[class*="st-key-{THUMB_KEY_PREFIX}"]:hover img {{ filter: brightness(0.9); }}
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


def render_gallery(filters: PhotoQuery) -> None:
    """Draw the gallery for the given filters."""
    sort_col, size_col, _ = st.columns([2, 1, 3])
    sort = sort_col.selectbox(
        "Sort", list(SORT_LABELS), format_func=SORT_LABELS.__getitem__, key="g_sort"
    )
    page_size = size_col.selectbox("Per page", PAGE_SIZES, key="g_page_size")
    query = filters.model_copy(update={"sort": sort, "page_size": page_size})
    page_number = _current_page(query)
    result = services.search(
        query.model_copy(update={"page": page_number}).model_dump_json()
    )

    if result.total == 0:
        st.info("No photos match these filters.")
        return
    first = (result.page - 1) * result.page_size + 1
    last = first + len(result.items) - 1
    st.caption(f"Showing {first}–{last} of {result.total} photos")
    _grid(result.items)
    _pager(result.pages)


def _digest(path: Path | str) -> str:
    return hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:16]


def thumbnail_key(path: Path | str) -> str:
    """Stable key of the container around a photo's thumbnail."""
    return f"{THUMB_KEY_PREFIX}{_digest(path)}"


def open_button_key(path: Path | str) -> str:
    """Stable key of the invisible button laid over a photo's thumbnail."""
    return f"{OPEN_KEY_PREFIX}{_digest(path)}"


def _grid(items: list[PhotoRecord]) -> None:
    st.html(THUMBNAIL_CSS)
    for start in range(0, len(items), GRID_COLUMNS):
        columns = st.columns(GRID_COLUMNS)
        for column, record in zip(
            columns, items[start : start + GRID_COLUMNS], strict=False
        ):
            with column, st.container(border=True):
                _thumbnail(record)
                st.caption(card_caption(record))
                if st.button("Details", key=f"details-{record.path}", width="stretch"):
                    show_details(str(record.path))


def _thumbnail(record: PhotoRecord) -> None:
    """The photo itself, clickable to open its details."""
    with st.container(key=thumbnail_key(record.path)):
        if record.preview_path.is_file():
            st.image(str(record.preview_path), width="stretch")
        else:
            st.caption("Preview missing")
        label = f"Open details for {record.path.name}"
        if st.button(label, key=open_button_key(record.path)):
            show_details(str(record.path))


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
