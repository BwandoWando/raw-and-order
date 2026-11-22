"""Stats tab: headline numbers and simple breakdowns."""

from collections.abc import Callable

import altair as alt
import streamlit as st

from raw_and_order.schemas.query import KELVIN_BAND_K, UNKNOWN_LABEL, LabelCount
from raw_and_order.ui.charts import (
    columns_by_month,
    horizontal_bars,
    ordered_columns,
    rows_frame,
    theme_for,
)
from raw_and_order.ui.library import PhotoLibrary

TOP_LENSES = 10


def render_stats(library: PhotoLibrary) -> None:
    """Draw the metrics row and the three breakdown charts."""
    summary = library.stats()
    failed = len(library.failures())
    a, b, c, d, e = st.columns(5)
    a.metric("Photos", summary.total)
    b.metric("With GPS", summary.with_gps)
    c.metric("With people", summary.with_people)
    d.metric("Copies skipped", summary.copies)
    e.metric("Logged failures", failed)
    if summary.total == 0:
        st.info("No photos yet.")
        return

    theme = theme_for(getattr(st.context.theme, "type", None))
    _section(
        "Photos by scene", summary.by_scene, lambda rows: horizontal_bars(rows, theme)
    )
    lenses = summary.by_lens[:TOP_LENSES]
    _section(
        f"Photos by lens (top {TOP_LENSES})",
        lenses,
        lambda rows: horizontal_bars(rows, theme),
    )
    dated = [row for row in summary.by_month if row.label != UNKNOWN_LABEL]
    undated = sum(row.count for row in summary.by_month if row.label == UNKNOWN_LABEL)
    _section(
        "Photos by capture month", dated, lambda rows: columns_by_month(rows, theme)
    )
    if undated:
        st.caption(
            f"{undated} photo(s) have no capture date and are not shown by month."
        )
    _section(
        f"Photos by white balance ({KELVIN_BAND_K} K bands, warm to cool light)",
        summary.by_white_balance,
        lambda rows: ordered_columns(
            rows, theme, x_title="Band start (K)", x_name="Band from (K)"
        ),
    )
    unknown_wb = summary.total - sum(row.count for row in summary.by_white_balance)
    if unknown_wb:
        st.caption(f"{unknown_wb} photo(s) have no white balance temperature.")


def _section(
    title: str,
    rows: list[LabelCount],
    chart: Callable[[list[LabelCount]], alt.LayerChart],
) -> None:
    st.subheader(title, divider="gray")
    if not rows:
        st.caption("No data.")
        return
    st.altair_chart(chart(rows), width="stretch", theme=None)
    with st.expander("Show as table"):
        st.dataframe(
            rows_frame(rows).rename(columns={"label": "Name", "count": "Photos"}),
            hide_index=True,
            width="stretch",
        )
