"""Sidebar filters -> :class:`PhotoQuery` fields."""

from datetime import date
from enum import StrEnum
from typing import Any

import streamlit as st

from raw_and_order.schemas.query import FilterOptions, PhotoQuery

PEOPLE_CHOICES = {"Any": None, "Yes": True, "No": False}
KELVIN_STEP = 50
RESET_KEY = "f_reset"


class FilterKey(StrEnum):
    """Session State key of each sidebar filter widget.

    The single list of filters: the widgets, :func:`filter_defaults` and Reset
    all go through it, so a filter cannot be drawn without a default.
    """

    TEXT = "f_text"
    SCENES = "f_scenes"
    TAGS = "f_tags"
    PEOPLE = "f_people"
    CAMERAS = "f_cameras"
    LENSES = "f_lenses"
    DATES = "f_dates"
    GPS = "f_gps"
    KELVIN = "f_kelvin"
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
    scenes = sidebar.multiselect("Scene", options.scenes, key=FilterKey.SCENES)
    tags = sidebar.multiselect(
        "Tags (all of)",
        options.tags,
        key=FilterKey.TAGS,
        placeholder="Most used first",
        format_func=lambda tag: tag_label(tag, options.tag_counts),
    )
    people = sidebar.segmented_control(
        "People", list(PEOPLE_CHOICES), key=FilterKey.PEOPLE
    )
    cameras = sidebar.multiselect("Camera", options.cameras, key=FilterKey.CAMERAS)
    lenses = sidebar.multiselect("Lens", options.lenses, key=FilterKey.LENSES)
    date_from, date_to = _date_range(options)
    only_gps = sidebar.checkbox("Only photos with GPS", key=FilterKey.GPS)
    kelvin_min, kelvin_max = _kelvin_range(options)
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
        scenes=tuple(scenes),
        tags=tuple(tags),
        contains_people=PEOPLE_CHOICES.get(people or "Any"),
        cameras=tuple(cameras),
        lenses=tuple(lenses),
        date_from=date_from,
        date_to=date_to,
        only_with_gps=only_gps,
        kelvin_min=kelvin_min,
        kelvin_max=kelvin_max,
        annotated_by=tuple(annotators),
    )


def filter_defaults(options: FilterOptions) -> dict[str, object]:
    """Each sidebar filter's key and the value that means "no filter".

    The date and white balance filters exist only when the photos have a
    range of those values to choose from.
    """
    defaults: dict[str, object] = {
        FilterKey.TEXT: "",
        FilterKey.SCENES: [],
        FilterKey.TAGS: [],
        FilterKey.PEOPLE: "Any",
        FilterKey.CAMERAS: [],
        FilterKey.LENSES: [],
        FilterKey.GPS: False,
        FilterKey.ANNOTATED_BY: [],
    }
    if (dates := _date_bounds(options)) is not None:
        defaults[FilterKey.DATES] = dates
    if (kelvin := _kelvin_bounds(options)) is not None:
        defaults[FilterKey.KELVIN] = kelvin
    return defaults


def _date_bounds(options: FilterOptions) -> tuple[date, date] | None:
    """Earliest and latest capture date, or ``None`` if no photo has one."""
    if options.earliest is None or options.latest is None:
        return None
    return options.earliest, options.latest


def _kelvin_bounds(options: FilterOptions) -> tuple[int, int] | None:
    """Lowest and highest white balance, or ``None`` if there is no range."""
    low, high = options.kelvin_min, options.kelvin_max
    if low is None or high is None or low == high:
        return None
    return low, high


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


def _kelvin_range(options: FilterOptions) -> tuple[int | None, int | None]:
    """The white balance filter; ``(None, None)`` when it does not narrow."""
    bounds = _kelvin_bounds(options)
    if bounds is None:
        return None, None  # nothing to choose between
    picked: Any = st.sidebar.slider(  # a range: Session State holds (low, high)
        "White balance (K)",
        min_value=bounds[0],
        max_value=bounds[1],
        step=KELVIN_STEP,
        key=FilterKey.KELVIN,
        help="Colour temperature; most values are estimated from the camera's "
        "Auto white balance.",
    )
    start, end = picked
    return (None, None) if (start, end) == bounds else (start, end)


def _reset(options: FilterOptions) -> None:
    """Put every filter back to its default, on screen as well.

    Assigning the value (rather than deleting the key) is what makes
    Streamlit send it to the browser; a deleted key resets only the server
    side, and the browser keeps showing and re-sending the old value.
    """
    st.session_state.update(filter_defaults(options))
