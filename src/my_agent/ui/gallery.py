"""Gallery tab: sort, page size, thumbnail grid and pagination."""

import streamlit as st

from my_agent.schemas import PhotoRecord
from my_agent.schemas.query import PAGE_SIZES, PhotoQuery, SortOrder
from my_agent.ui import services
from my_agent.ui.detail import show_details
from my_agent.ui.formatting import card_caption

GRID_COLUMNS = 4
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


def _grid(items: list[PhotoRecord]) -> None:
    for start in range(0, len(items), GRID_COLUMNS):
        columns = st.columns(GRID_COLUMNS)
        for column, record in zip(
            columns, items[start : start + GRID_COLUMNS], strict=False
        ):
            with column, st.container(border=True):
                if record.preview_path.is_file():
                    st.image(str(record.preview_path), width="stretch")
                else:
                    st.caption("Preview missing")
                st.caption(card_caption(record))
                if st.button("Details", key=f"details-{record.path}", width="stretch"):
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
