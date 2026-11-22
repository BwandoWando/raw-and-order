"""The app's tabs, and switching between them from code."""

from enum import StrEnum

import streamlit as st

TABS_KEY = "main_tab"  # Session State key holding the open tab's label


class Tab(StrEnum):
    """The app's tabs, in the order shown; each value is the tab's label."""

    GALLERY = "Gallery"
    TAGS = "Tags"
    FAILURES = "Failures"
    STATS = "Stats"
    EXPORT = "Export"


def open_tab(tab: Tab) -> None:
    """Show ``tab`` on the next run; call it from a widget callback.

    This works because the tabs are drawn with ``on_change="rerun"``, which
    lets Session State set the open tab.
    """
    st.session_state[TABS_KEY] = tab.value
