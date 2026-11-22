"""Streamlit entry point and the UI's composition root.

Start with ``raw-and-order ui`` or ``streamlit run src/raw_and_order/ui/app.py``.
"""

from collections.abc import Callable
from functools import partial

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from raw_and_order.bootstrap import build_ui_library
from raw_and_order.config import load_settings
from raw_and_order.exceptions import RawAndOrderError
from raw_and_order.ui.css import PINNED_MULTISELECT_BUTTONS
from raw_and_order.ui.export import render_export
from raw_and_order.ui.failures import render_failures
from raw_and_order.ui.filters import render_filters
from raw_and_order.ui.gallery import render_gallery
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.ui.stats import render_stats
from raw_and_order.ui.tags import render_tags


@st.cache_resource(show_spinner=False)
def _library() -> PhotoLibrary:
    """Build the library once per UI process."""
    return build_ui_library(load_settings())


def main(library: PhotoLibrary) -> None:
    """Draw the whole app from the given library."""
    st.html(PINNED_MULTISELECT_BUTTONS)
    st.title("📷 Raw and Order")
    try:
        options = library.filter_options()
    except RawAndOrderError as exc:
        st.error(f"Could not open the photo database: {exc}")
        st.stop()
    st.sidebar.button("↻ Refresh data", on_click=library.refresh, width="stretch")
    filters = render_filters(options)

    gallery_tab, tags_tab, failures_tab, stats_tab, export_tab = st.tabs(
        ["Gallery", "Tags", "Failures", "Stats", "Export"]
    )
    renderers: list[tuple[DeltaGenerator, Callable[[], None]]] = [
        (gallery_tab, partial(render_gallery, filters, library)),
        (tags_tab, partial(render_tags, filters, library)),
        (failures_tab, partial(render_failures, library)),
        (stats_tab, partial(render_stats, library)),
        (export_tab, partial(render_export, filters, library)),
    ]
    for tab, render in renderers:
        with tab:
            try:
                render()
            except RawAndOrderError as exc:
                st.error(str(exc))


def run() -> None:
    """Configure the page, build the library and draw the app."""
    st.set_page_config(page_title="Raw and Order", page_icon="📷", layout="wide")
    try:
        library = _library()
    except RawAndOrderError as exc:
        st.error(f"Could not open the photo database: {exc}")
        st.stop()
    main(library)


if __name__ == "__main__":  # Streamlit runs the script as __main__
    run()
