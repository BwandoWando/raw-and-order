"""Streamlit entry point.

Start with ``my-agent ui`` or ``streamlit run src/my_agent/ui/app.py``.
"""

from collections.abc import Callable
from functools import partial

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from my_agent.exceptions import MyAgentError
from my_agent.ui import services
from my_agent.ui.failures import render_failures
from my_agent.ui.filters import render_filters
from my_agent.ui.gallery import render_gallery
from my_agent.ui.stats import render_stats


def main() -> None:
    """Draw the whole app."""
    st.set_page_config(page_title="my-agent photos", page_icon="📷", layout="wide")
    st.title("📷 Photo library")
    try:
        options = services.filter_options()
    except MyAgentError as exc:
        st.error(f"Could not open the photo database: {exc}")
        st.stop()
    st.sidebar.button("↻ Refresh data", on_click=services.refresh, width="stretch")
    filters = render_filters(options)

    gallery_tab, failures_tab, stats_tab = st.tabs(["Gallery", "Failures", "Stats"])
    renderers: list[tuple[DeltaGenerator, Callable[[], None]]] = [
        (gallery_tab, partial(render_gallery, filters)),
        (failures_tab, render_failures),
        (stats_tab, render_stats),
    ]
    for tab, render in renderers:
        with tab:
            try:
                render()
            except MyAgentError as exc:
                st.error(str(exc))


main()
