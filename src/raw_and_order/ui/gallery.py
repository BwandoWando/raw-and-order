"""Gallery tab: sort, page size, thumbnail grid and pagination.

Shows one page of the photos matching the sidebar filters as square tiles
sized to fill the window. Clicking a tile opens the photo details dialog
(``ui/detail.py``), which can step through the photos on this page and on
past either end of it, turning the page.
"""

from enum import StrEnum
from pathlib import Path

import streamlit as st

from raw_and_order.schemas import PhotoRecord
from raw_and_order.schemas.query import PAGE_SIZES, PhotoPage, PhotoQuery, SortOrder
from raw_and_order.ui.css import clickable_tile, keyed, keyed_prefix
from raw_and_order.ui.detail import (
    GalleryPage,
    PageTurn,
    details_open,
    open_details,
    take_page_turn,
)
from raw_and_order.ui.formatting import path_digest, thumbnail_tooltip
from raw_and_order.ui.grid import grid_shape, thumbnail_px
from raw_and_order.ui.library import PhotoLibrary

THUMB_KEY_PREFIX = "thumb-"  # container holding the image and the overlay
# The overlay's prefix must not contain the tile's: the CSS selects tiles with
# [class*="st-key-thumb-"], which would also match "thumb-open-".
OPEN_KEY_PREFIX = "thumbopen-"  # the overlay button itself
GRID_KEY = "gallery-grid"


class GalleryKey(StrEnum):
    """Session State keys of the gallery's controls and paging."""

    SORT = "g_sort"
    PAGE_SIZE = "g_page_size"  # also the URL query parameter: keep it stable
    PAGE = "g_page"
    PAGE_QUERY = "g_signature"  # the query the page number belongs to
    PREVIOUS = "g_prev"
    NEXT = "g_next"


# Height of everything on the page but the tiles (menu bar, title, tabs, sort
# row, "Showing" caption, pager and page padding), so the grid fills the rest.
# Measured with the padding in ui/theme.toml.
CHROME_REM = 25.25
ROW_GAP_REM = 0.25
# Fill around portrait and landscape photos in their square tile; a
# translucent grey reads as neutral on both the light and dark theme.
LETTERBOX = "rgba(128, 128, 128, 0.12)"


def thumbnail_css(rows: int) -> str:
    """CSS that sizes square tiles so ``rows`` rows fill the rest of the window.

    Tiles are square, as on Instagram; each photo is scaled to fit inside its
    tile whole (``object-fit: contain``), so portrait and landscape shots are
    letterboxed rather than cropped.

    Each tile is clickable through a transparent button laid over it (see
    :func:`~raw_and_order.ui.css.clickable_tile`).
    """
    tile_height = (
        f"calc((100vh - {CHROME_REM}rem - {rows - 1} * {ROW_GAP_REM}rem) / {rows})"
    )
    tile = keyed_prefix(THUMB_KEY_PREFIX)
    return f"""
<style>
{keyed(GRID_KEY)} {{ gap: {ROW_GAP_REM}rem; }}
{tile} img {{
    display: block;
    width: min(100%, {tile_height});
    height: auto;
    aspect-ratio: 1 / 1;
    margin-inline: auto;
    object-fit: contain;
    background: {LETTERBOX};
    border-radius: 0.375rem;
    transition: filter 120ms ease-in-out;
}}
{clickable_tile(tile, keyed_prefix(OPEN_KEY_PREFIX))}
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
        "Sort",
        list(SORT_LABELS),
        format_func=SORT_LABELS.__getitem__,
        key=GalleryKey.SORT,
    )
    page_size = size_col.selectbox(
        "Per page", PAGE_SIZES, key=GalleryKey.PAGE_SIZE, bind="query-params"
    )
    query = filters.model_copy(update={"sort": sort, "page_size": page_size})
    turn = take_page_turn()
    page_number = _current_page(query, turn)
    result = library.search(query.model_copy(update={"page": page_number}))

    if result.total == 0:
        st.info("No photos match these filters.")
        return
    first = (result.page - 1) * result.page_size + 1
    last = first + len(result.items) - 1
    st.caption(f"Showing {first}–{last} of {result.total} photos")
    page = gallery_page(result)
    _grid(result.items, query.page_size, page, library)
    if turn is not None and page.paths:
        _reopen_details(page, turn, library)
    _pager(page_number, result.pages)


def gallery_page(result: PhotoPage) -> GalleryPage:
    """The photos on ``result``'s page, and whether pages lie either side."""
    return GalleryPage(
        paths=tuple(record.path for record in result.items),
        has_previous=result.page > 1,
        has_next=result.page < result.pages,
    )


def chosen_sort(default: SortOrder) -> SortOrder:
    """The sort order picked in the gallery, or ``default`` before it is drawn."""
    sort = st.session_state.get(GalleryKey.SORT, default)
    return SortOrder(sort)


def thumbnail_key(path: Path | str) -> str:
    """Stable key of the container around a photo's thumbnail."""
    return f"{THUMB_KEY_PREFIX}{path_digest(path)}"


def open_button_key(path: Path | str) -> str:
    """Stable key of the invisible button laid over a photo's thumbnail."""
    return f"{OPEN_KEY_PREFIX}{path_digest(path)}"


def _grid(
    items: list[PhotoRecord],
    page_size: int,
    page: GalleryPage,
    library: PhotoLibrary,
) -> None:
    """Thumbnails only, sized so a full page fits the window.

    The shape comes from the page size, not the item count, so a short last
    page keeps the same tile size.
    """
    columns, rows = grid_shape(page_size)
    max_px = thumbnail_px(columns)
    st.html(thumbnail_css(rows))
    with st.container(key=GRID_KEY):
        for start in range(0, len(items), columns):
            cells = st.columns(columns, gap="xxsmall")
            for cell, record in zip(
                cells, items[start : start + columns], strict=False
            ):
                with cell:
                    _thumbnail(record, page, max_px, library)


def _thumbnail(
    record: PhotoRecord, page: GalleryPage, max_px: int, library: PhotoLibrary
) -> None:
    """The photo itself, clickable to open its details; date and scene on hover.

    ``page`` holds the photos on this page, which the details can step through.
    """
    with st.container(key=thumbnail_key(record.path)):
        image = library.thumbnail(record.preview_path, max_px)
        if image is None:
            st.caption("Preview missing")
        else:
            st.image(image, width="stretch")
        label = f"Open details for {record.path.name}"
        if st.button(
            label, key=open_button_key(record.path), help=thumbnail_tooltip(record)
        ):
            open_details(record.path, page, library)


def _reopen_details(page: GalleryPage, turn: PageTurn, library: PhotoLibrary) -> None:
    """Open the details again after they turned the page.

    Going forward shows the new page's first photo, going back its last.
    """
    path = page.paths[0] if turn is PageTurn.NEXT else page.paths[-1]
    open_details(path, page, library)


def _current_page(query: PhotoQuery, turn: PageTurn | None = None) -> int:
    """Keep the page number, but go back to page 1 when the query changes.

    ``query`` holds the filters, sort and page size (not the page), so a
    change to any of them starts again from page 1. A ``turn`` from the photo
    details moves one page back or forward.
    """
    signature = query.model_dump_json()
    if st.session_state.get(GalleryKey.PAGE_QUERY) != signature:
        st.session_state[GalleryKey.PAGE_QUERY] = signature
        st.session_state[GalleryKey.PAGE] = 1
    page = int(st.session_state.get(GalleryKey.PAGE, 1))
    if turn is not None:
        page = max(1, page + (1 if turn is PageTurn.NEXT else -1))
        st.session_state[GalleryKey.PAGE] = page
    return page


def _pager(page: int, pages: int) -> None:
    """Previous and next page buttons, also on the left and right arrow keys.

    While the photo details are open the arrow keys step photos instead, so
    these shortcuts are off then (Streamlit would fire both). The grid is
    drawn first, so a click that opens the details is already known here.
    """
    if pages <= 1:
        return
    keys_free = not details_open()
    previous_col, label_col, next_col = st.columns([1, 2, 1])
    previous_col.button(
        "Previous",
        key=GalleryKey.PREVIOUS,
        shortcut="Left" if keys_free else None,
        on_click=_go,
        args=(page - 1,),
        disabled=page <= 1,
        width="stretch",
    )
    label_col.markdown(
        f"<div style='text-align:center'>Page {page} of {pages}</div>",
        unsafe_allow_html=True,
    )
    next_col.button(
        "Next",
        key=GalleryKey.NEXT,
        shortcut="Right" if keys_free else None,
        on_click=_go,
        args=(page + 1,),
        disabled=page >= pages,
        width="stretch",
    )


def _go(page: int) -> None:
    st.session_state[GalleryKey.PAGE] = page
