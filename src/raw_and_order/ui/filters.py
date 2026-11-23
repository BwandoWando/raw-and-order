"""Sidebar filters, turned into a :class:`PhotoQuery`.

:func:`render_filters` runs first on every rerun; the query it returns is
handed to the Gallery, Tags and Export tabs. Other pages change a filter by
writing its Session State key (see :func:`show_tags`) from a callback.
"""

from datetime import date
from enum import StrEnum
from typing import Any

import streamlit as st

from raw_and_order.schemas.query import FilterOptions, PhotoQuery

RESET_KEY = "f_reset"


class FilterKey(StrEnum):
    """Session State key of each sidebar filter widget.

    The single list of filter keys: the widgets, :func:`filter_defaults` and
    Reset all use it. A new filter needs a member here and a default in
    :func:`filter_defaults`.
    """

    TEXT = "f_text"
    FILE_NAME = "f_file_name"
    FAVORITES = "f_favorites"
    TRASHED = "f_trashed"
    TAGS = "f_tags"
    CAMERAS = "f_cameras"
    LENSES = "f_lenses"
    DATES = "f_dates"
    ANNOTATED_BY = "f_annotated_by"


def tag_label(tag: str, counts: dict[str, int]) -> str:
    """``tag (photos)``, e.g. ``urban (1,204)``; just the tag if not counted."""
    count = counts.get(tag)
    return tag if count is None else f"{tag} ({count:,})"


def render_filters(options: FilterOptions) -> PhotoQuery:
    """Draw the sidebar filters and return a query (page 1, default sort).

    Defaults live in Session State only (not in the widgets' ``value`` or
    ``default``), because Reset writes them there too and Streamlit warns
    when a widget gets its value both ways.
    """
    for key, value in filter_defaults(options).items():
        st.session_state.setdefault(key, value)
    sidebar = st.sidebar
    sidebar.header("Filters")
    text = sidebar.text_input(
        "Search", key=FilterKey.TEXT, placeholder="description or tag"
    )
    file_name = sidebar.text_input(
        "File name",
        key=FilterKey.FILE_NAME,
        placeholder="e.g. DSC0812 or .jpg",
        help="Photos whose file name contains this, in any case. Folders are "
        "not searched.",
    )
    only_favorites = sidebar.toggle("Favorites only", key=FilterKey.FAVORITES)
    only_trashed = sidebar.toggle(
        "Marked for deletion only",
        key=FilterKey.TRASHED,
        help="Photos marked with the bin (or the Delete key) in the photo "
        "details. Nothing is deleted.",
    )
    tags = sidebar.multiselect(
        "Tags (all of)",
        options.tags,
        key=FilterKey.TAGS,
        placeholder="Most used first",
        format_func=lambda tag: tag_label(tag, options.tag_counts),
        help="Photos with every one of these tags. Clicking a cluster on the "
        "Tags tab fills this in.",
    )
    cameras = sidebar.multiselect("Camera", options.cameras, key=FilterKey.CAMERAS)
    lenses = sidebar.multiselect("Lens", options.lenses, key=FilterKey.LENSES)
    date_from, date_to = _date_range(options)
    annotators = sidebar.multiselect(
        "Annotated by", options.annotated_by, key=FilterKey.ANNOTATED_BY
    )
    sidebar.button(
        "Reset filters",
        key=RESET_KEY,
        on_click=_reset,
        args=(options,),
        width="stretch",
    )
    return PhotoQuery(
        text=text or None,
        file_name=file_name or None,
        tags=tuple(tags),
        cameras=tuple(cameras),
        lenses=tuple(lenses),
        date_from=date_from,
        date_to=date_to,
        only_favorites=only_favorites,
        only_trashed=only_trashed,
        annotated_by=tuple(annotators),
    )


def filter_defaults(options: FilterOptions) -> dict[str, object]:
    """Each sidebar filter's key and the value that means "no filter".

    The date filter exists only when the photos have capture dates to
    choose from.
    """
    defaults: dict[str, object] = {
        FilterKey.TEXT: "",
        FilterKey.FILE_NAME: "",
        FilterKey.FAVORITES: False,
        FilterKey.TRASHED: False,
        FilterKey.TAGS: [],
        FilterKey.CAMERAS: [],
        FilterKey.LENSES: [],
        FilterKey.ANNOTATED_BY: [],
    }
    if (dates := _date_bounds(options)) is not None:
        defaults[FilterKey.DATES] = dates
    return defaults


def _date_bounds(options: FilterOptions) -> tuple[date, date] | None:
    """Earliest and latest capture date, or ``None`` if no photo has one."""
    if options.earliest is None or options.latest is None:
        return None
    return options.earliest, options.latest


def _date_range(options: FilterOptions) -> tuple[date | None, date | None]:
    """The capture date filter; ``(None, None)`` when it does not narrow."""
    bounds = _date_bounds(options)
    if bounds is None:
        st.sidebar.caption("No capture dates yet.")
        return None, None
    picked: Any = st.sidebar.date_input(  # a range: Session State holds it
        "Capture date",
        min_value=bounds[0],
        max_value=bounds[1],
        key=FilterKey.DATES,
    )
    if isinstance(picked, tuple) and len(picked) == 2:
        start, end = picked
        return (None, None) if (start, end) == bounds else (start, end)
    return None, None  # mid-selection: only a start date picked so far


def show_tags(tags: list[str]) -> None:
    """Set the "Tags (all of)" filter to ``tags``; call it from a callback."""
    st.session_state[FilterKey.TAGS] = list(tags)


def _reset(options: FilterOptions) -> None:
    """Put every filter back to its default, on screen as well.

    Assigning the value (rather than deleting the key) is what makes
    Streamlit send it to the browser; a deleted key resets only the server
    side, and the browser keeps showing and re-sending the old value.
    """
    st.session_state.update(filter_defaults(options))
