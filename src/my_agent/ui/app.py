"""Streamlit entry point and the UI's composition root.

Start with ``my-agent ui`` or ``streamlit run src/my_agent/ui/app.py``.
"""

from collections.abc import Callable
from functools import partial

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from my_agent.bootstrap import build_ui_library
from my_agent.config import load_settings
from my_agent.exceptions import MyAgentError
from my_agent.ui.failures import render_failures
from my_agent.ui.filters import render_filters
from my_agent.ui.gallery import render_gallery
from my_agent.ui.library import PhotoLibrary
from my_agent.ui.stats import render_stats
from my_agent.ui.tags import render_tags


@st.cache_resource(show_spinner=False)
def _library() -> PhotoLibrary:
    """Build the library once per UI process."""
    return build_ui_library(load_settings())


def main(library: PhotoLibrary) -> None:
    """Draw the whole app from the given library."""
    st.title("📷 Photo library")
    try:
        options = library.filter_options()
    except MyAgentError as exc:
        st.error(f"Could not open the photo database: {exc}")
        st.stop()
    st.sidebar.button("↻ Refresh data", on_click=library.refresh, width="stretch")
    filters = render_filters(options)

    gallery_tab, tags_tab, failures_tab, stats_tab = st.tabs(
        ["Gallery", "Tags", "Failures", "Stats"]
    )
    renderers: list[tuple[DeltaGenerator, Callable[[], None]]] = [
        (gallery_tab, partial(render_gallery, filters, library)),
        (tags_tab, partial(render_tags, filters, library)),
        (failures_tab, partial(render_failures, library)),
        (stats_tab, partial(render_stats, library)),
    ]
    for tab, render in renderers:
        with tab:
            try:
                render()
            except MyAgentError as exc:
                st.error(str(exc))


def run() -> None:
    """Configure the page, build the library and draw the app."""
    st.set_page_config(page_title="my-agent photos", page_icon="📷", layout="wide")
    try:
        library = _library()
    except MyAgentError as exc:
        st.error(f"Could not open the photo database: {exc}")
        st.stop()
    main(library)


if __name__ == "__main__":  # Streamlit runs the script as __main__
    run()
