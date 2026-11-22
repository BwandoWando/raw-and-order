"""Gallery tab: sort, page size, thumbnail grid and pagination.

Shows one page of the photos matching the sidebar filters as square tiles
sized to fill the window. Clicking a tile opens the photo details dialog
(``ui/detail.py``), which can step through the photos on this page and on
past either end of it, turning the page. Clicking a similar photo there turns
to the page that photo is on.
"""

from enum import StrEnum
from pathlib import Path

import streamlit as st

from raw_and_order.schemas import PhotoRecord
from raw_and_order.schemas.query import PAGE_SIZES, PhotoPage, PhotoQuery, SortOrder
from raw_and_order.ui.css import clickable_tile, keyed, keyed_prefix, visually_hidden
from raw_and_order.ui.detail import (
    GalleryPage,
    GalleryRequest,
    PageTurn,
    details_open,
    open_details,
    take_gallery_request,
)
from raw_and_order.ui.formatting import path_digest, thumbnail_tooltip
from raw_and_order.ui.grid import grid_shape, thumbnail_px
from raw_and_order.ui.library import PhotoLibrary

THUMB_KEY_PREFIX = "thumb-"  # container holding the image and the overlay
# The overlay's prefix must not contain the tile's: the CSS selects tiles with
# [class*="st-key-thumb-"], which would also match "thumb-open-".
OPEN_KEY_PREFIX = "thumbopen-"  # the overlay button itself
GRID_KEY = "gallery-grid"
PAGER_KEY = "gallery-pager"
PAGE_KEY_PREFIX = "g-page-"  # a page number button: g-page-<n>
CURRENT_PAGE_KEY = f"{PAGE_KEY_PREFIX}current"  # the page shown, a filled circle
PAGE_WINDOW = 10  # page numbers shown at once


class GalleryKey(StrEnum):
    """Session State keys of the gallery's controls and paging."""

    SORT = "g_sort"
    PAGE_SIZE = "g_page_size"  # also the URL query parameter: keep it stable
    PAGE = "g_page"
    PAGE_QUERY = "g_signature"  # the query the page number belongs to
    PREVIOUS = "g_prev"
    NEXT = "g_next"


# The current page is a filled circle in the text colour, with the page
# number in the background colour, so it inverts with the theme.
CURRENT_PAGE_COLOURS = {  # theme: (circle, number); from ui/theme.toml
    "light": ("#2F2D2B", "#FFFFFF"),
    "dark": ("#E6E6E6", "#1E1E1E"),
}
_LABEL = '[data-testid="stMarkdownContainer"]'  # a button's text label


def pager_css(theme_type: str | None) -> str:
    """Round page buttons, the current page filled; arrows show only their icon.

    The arrows' labels and shortcut hints stay for screen readers.
    """
    circle, number = CURRENT_PAGE_COLOURS.get(
        theme_type or "light", CURRENT_PAGE_COLOURS["light"]
    )
    arrows = (keyed(GalleryKey.PREVIOUS), keyed(GalleryKey.NEXT))
    hidden = [f"{arrow} {part}" for arrow in arrows for part in (_LABEL, "kbd")]
    return f"""
<style>
{keyed(PAGER_KEY)} button {{
    min-width: 2.25rem;
    height: 2.25rem;
    min-height: 2.25rem;
    padding: 0 0.5rem;
    border-radius: 999px;  /* a circle, or a pill for long numbers */
    justify-content: center;
}}
{keyed(CURRENT_PAGE_KEY)} button,
{keyed(CURRENT_PAGE_KEY)} button:hover {{
    background: {circle};
    border-color: {circle};
    color: {number};
}}
{visually_hidden(*hidden)}
</style>
"""


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
    request = take_gallery_request()
    page_number = _requested_page(request, _current_page(query), query, library)
    result = library.search(query.model_copy(update={"page": page_number}))

    if result.total == 0:
        st.info("No photos match these filters.")
        return
    first = (result.page - 1) * result.page_size + 1
    last = first + len(result.items) - 1
    st.caption(f"Showing {first}–{last} of {result.total} photos")
    page = gallery_page(result, query)
    _grid(result.items, query.page_size, page, library)
    if request is not None:
        _reopen_details(request, page, library)
    _pager(page_number, result.pages)


def gallery_page(result: PhotoPage, query: PhotoQuery) -> GalleryPage:
    """What the photo details need to know about the page shown.

    The photos on ``result``'s page, whether pages lie either side, and the
    filters and sort (``query``) that chose them.
    """
    return GalleryPage(
        paths=tuple(record.path for record in result.items),
        has_previous=result.page > 1,
        has_next=result.page < result.pages,
        query=query,
    )


def page_of(position: int, page_size: int) -> int:
    """The page (from 1) showing the photo at ``position`` (from 1)."""
    return (position - 1) // page_size + 1


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


def _reopen_details(
    request: GalleryRequest, page: GalleryPage, library: PhotoLibrary
) -> None:
    """Open the details again after they asked for another page.

    A page turned forward shows its first photo, one turned back its last; a
    similar photo clicked is shown itself.
    """
    if isinstance(request, Path):
        open_details(request, page, library)
    elif page.paths:
        path = page.paths[0] if request is PageTurn.NEXT else page.paths[-1]
        open_details(path, page, library)


def _requested_page(
    request: GalleryRequest | None,
    page: int,
    query: PhotoQuery,
    library: PhotoLibrary,
) -> int:
    """The page to show after a request from the photo details.

    A turn moves one page; a photo moves to the page it is on under the
    current filters and sort (or stays, if it no longer matches them).
    """
    if request is None:
        return page
    if isinstance(request, PageTurn):
        page = max(1, page + (1 if request is PageTurn.NEXT else -1))
    else:
        position = library.position(request, query)
        page = page if position is None else page_of(position, query.page_size)
    st.session_state[GalleryKey.PAGE] = page
    return page


def _current_page(query: PhotoQuery) -> int:
    """Keep the page number, but go back to page 1 when the query changes.

    ``query`` holds the filters, sort and page size (not the page), so a
    change to any of them starts again from page 1.
    """
    signature = query.model_dump_json()
    if st.session_state.get(GalleryKey.PAGE_QUERY) != signature:
        st.session_state[GalleryKey.PAGE_QUERY] = signature
        st.session_state[GalleryKey.PAGE] = 1
    return int(st.session_state.get(GalleryKey.PAGE, 1))


def page_window(page: int, pages: int, size: int = PAGE_WINDOW) -> range:
    """The page numbers to show: ``size`` of them around ``page``.

    ``page`` sits just right of the middle (14 shows 9-18), and the window
    slides rather than shrinks near either end.
    """
    first = max(1, min(page - size // 2, pages - size + 1))
    return range(first, min(pages, first + size - 1) + 1)


def page_button_key(page: int) -> str:
    """Stable key of the button for page ``page`` (not the current page)."""
    return f"{PAGE_KEY_PREFIX}{page}"


def _pager(page: int, pages: int) -> None:
    """Arrows either side of a row of page numbers, the current one filled.

    The arrows are also the left and right arrow keys. While the photo
    details are open the arrow keys step photos instead, so these shortcuts
    are off then (Streamlit would fire both). The grid is drawn first, so a
    click that opens the details is already known here.
    """
    if pages <= 1:
        return
    st.html(pager_css(getattr(st.context.theme, "type", None)))
    keys_free = not details_open()
    with st.container(
        key=PAGER_KEY,
        horizontal=True,
        horizontal_alignment="center",
        vertical_alignment="center",
        gap="xsmall",
    ):
        _arrow(
            "Previous page",
            GalleryKey.PREVIOUS,
            "arrow_back",
            "Left",
            page - 1,
            page <= 1,
            keys_free,
        )
        for number in page_window(page, pages):
            current = number == page
            st.button(
                str(number),
                key=CURRENT_PAGE_KEY if current else page_button_key(number),
                type="primary" if current else "tertiary",
                on_click=_go,
                args=(number,),
            )
        _arrow(
            "Next page",
            GalleryKey.NEXT,
            "arrow_forward",
            "Right",
            page + 1,
            page >= pages,
            keys_free,
        )


def _arrow(
    label: str,
    key: str,
    icon: str,
    shortcut: str,
    target: int,
    disabled: bool,
    keys_free: bool,
) -> None:
    """An icon-only arrow button that goes to page ``target``."""
    st.button(
        label,
        key=key,
        icon=f":material/{icon}:",
        type="tertiary",
        shortcut=shortcut if keys_free else None,
        on_click=_go,
        args=(target,),
        disabled=disabled,
    )


def _go(page: int) -> None:
    st.session_state[GalleryKey.PAGE] = page
