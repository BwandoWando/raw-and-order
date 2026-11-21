"""Failures tab: the processing_failures log."""

import pandas as pd
import streamlit as st

from my_agent.ui.library import PhotoLibrary


def render_failures(library: PhotoLibrary) -> None:
    """Draw the failure log as a table."""
    records = library.failures()
    if not records:
        st.success("No logged failures.")
        return
    st.caption(
        f"{len(records)} file(s) failed. Retry them with "
        "`my-agent process <folder> --reprocess-failed`."
    )
    stages = sorted({r.stage for r in records})
    chosen = st.pills("Stage", stages, selection_mode="multi", key="fail_stages")
    shown = [r for r in records if not chosen or r.stage in chosen]
    frame = pd.DataFrame(
        {
            "File": [r.path.name for r in shown],
            "Stage": [r.stage for r in shown],
            "Error": [r.error_type for r in shown],
            "Message": [r.message for r in shown],
            "Attempts": [r.attempts for r in shown],
            "Last failed": [r.last_failed_at for r in shown],
            "Path": [str(r.path) for r in shown],
        }
    )
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "Last failed": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
            "Attempts": st.column_config.NumberColumn(format="%d"),
        },
    )
