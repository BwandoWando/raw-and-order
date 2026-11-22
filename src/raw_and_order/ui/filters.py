"""Sidebar filters -> :class:`PhotoQuery` fields."""

from datetime import date
from typing import Any

import streamlit as st

from raw_and_order.schemas.query import FilterOptions, PhotoQuery

PEOPLE_CHOICES = {"Any": None, "Yes": True, "No": False}
KELVIN_STEP = 50
RESET_KEY = "f_reset"


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
    text = sidebar.text_input("Search", key="f_text", placeholder="description or tag")
    scenes = sidebar.multiselect("Scene", options.scenes, key="f_scenes")
    tags = sidebar.multiselect(
        "Tags (all of)",
        options.tags,
        key="f_tags",
        placeholder="Most used first",
        format_func=lambda tag: tag_label(tag, options.tag_counts),
    )
    people = sidebar.segmented_control("People", list(PEOPLE_CHOICES), key="f_people")
    cameras = sidebar.multiselect("Camera", options.cameras, key="f_cameras")
    lenses = sidebar.multiselect("Lens", options.lenses, key="f_lenses")
    date_from, date_to = _date_range(options)
    only_gps = sidebar.checkbox("Only photos with GPS", key="f_gps")
    kelvin_min, kelvin_max = _kelvin_range(options)
    models = sidebar.multiselect("Annotated by", options.annotated_by, key="f_models")
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
        annotated_by=tuple(models),
    )


def _date_range(options: FilterOptions) -> tuple[date | None, date | None]:
    if options.earliest is None or options.latest is None:
        st.sidebar.caption("No capture dates yet.")
        return None, None
    picked: Any = st.sidebar.date_input(
        "Capture date",
        min_value=options.earliest,
        max_value=options.latest,
        key="f_dates",
    )
    if isinstance(picked, tuple) and len(picked) == 2:
        start, end = picked
        full_range = (start, end) == (options.earliest, options.latest)
        return (None, None) if full_range else (start, end)
    return None, None  # mid-selection: only a start date picked so far


def _kelvin_range(options: FilterOptions) -> tuple[int | None, int | None]:
    low, high = options.kelvin_min, options.kelvin_max
    if low is None or high is None or low == high:
        return None, None  # nothing to choose between
    picked: Any = st.sidebar.slider(  # a range: Session State holds (low, high)
        "White balance (K)",
        min_value=low,
        max_value=high,
        step=KELVIN_STEP,
        key="f_kelvin",
        help="Colour temperature; most values are estimated from the camera's "
        "Auto white balance.",
    )
    start, end = picked
    return (None, None) if (start, end) == (low, high) else (start, end)


def filter_defaults(options: FilterOptions) -> dict[str, Any]:
    """Each sidebar widget's key and the value that means "no filter"."""
    defaults: dict[str, Any] = {
        "f_text": "",
        "f_scenes": [],
        "f_tags": [],
        "f_people": "Any",
        "f_cameras": [],
        "f_lenses": [],
        "f_gps": False,
        "f_models": [],
    }
    if options.earliest is not None and options.latest is not None:
        defaults["f_dates"] = (options.earliest, options.latest)
    low, high = options.kelvin_min, options.kelvin_max
    if low is not None and high is not None and low != high:
        defaults["f_kelvin"] = (low, high)
    return defaults


def _reset(options: FilterOptions) -> None:
    """Put every filter back to its default, on screen as well.

    Assigning the value (rather than deleting the key) is what makes
    Streamlit send it to the browser; a deleted key resets only the server
    side, and the browser keeps showing and re-sending the old value.
    """
    st.session_state.update(filter_defaults(options))
