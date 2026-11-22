"""Stats tab: headline numbers and simple breakdowns.

Each breakdown is a chart from ``ui/charts.py`` with its numbers in a table
below it.
"""

from collections.abc import Callable

import altair as alt
import streamlit as st

from raw_and_order.schemas.query import (
    KELVIN_BAND_K,
    UNKNOWN_LABEL,
    LabelCount,
    PhotoStats,
)
from raw_and_order.ui.charts import (
    ChartTheme,
    columns_by_month,
    horizontal_bars,
    ordered_columns,
    rows_frame,
    theme_for,
)
from raw_and_order.ui.library import PhotoLibrary

TOP_LENSES = 10


def render_stats(library: PhotoLibrary) -> None:
    """Draw the headline numbers, then the breakdown charts."""
    summary = library.stats()
    _metrics(summary, failed=len(library.failures()))
    if summary.total == 0:
        st.info("No photos yet.")
        return
    theme = theme_for(getattr(st.context.theme, "type", None))
    _section(
        "Photos by scene", summary.by_scene, lambda rows: horizontal_bars(rows, theme)
    )
    _section(
        f"Photos by lens (top {TOP_LENSES})",
        summary.by_lens[:TOP_LENSES],
        lambda rows: horizontal_bars(rows, theme),
    )
    _by_month(summary, theme)
    _by_white_balance(summary, theme)


def _metrics(summary: PhotoStats, failed: int) -> None:
    """One row of headline numbers."""
    metrics = [
        ("Photos", summary.total),
        ("With GPS", summary.with_gps),
        ("With people", summary.with_people),
        ("Copies skipped", summary.copies),
        ("Logged failures", failed),
    ]
    for column, (label, value) in zip(st.columns(len(metrics)), metrics, strict=True):
        column.metric(label, value)


def _by_month(summary: PhotoStats, theme: ChartTheme) -> None:
    """Photos per capture month; undated photos are counted below the chart."""
    dated = [row for row in summary.by_month if row.label != UNKNOWN_LABEL]
    undated = sum(row.count for row in summary.by_month if row.label == UNKNOWN_LABEL)
    _section(
        "Photos by capture month", dated, lambda rows: columns_by_month(rows, theme)
    )
    if undated:
        st.caption(
            f"{undated} photo(s) have no capture date and are not shown by month."
        )


def _by_white_balance(summary: PhotoStats, theme: ChartTheme) -> None:
    """Photos per white balance band; photos without one are counted below."""
    _section(
        f"Photos by white balance ({KELVIN_BAND_K} K bands, warm to cool light)",
        summary.by_white_balance,
        lambda rows: ordered_columns(
            rows, theme, x_title="Band start (K)", x_name="Band from (K)"
        ),
    )
    unknown = summary.total - sum(row.count for row in summary.by_white_balance)
    if unknown:
        st.caption(f"{unknown} photo(s) have no white balance temperature.")


def _section(
    title: str,
    rows: list[LabelCount],
    chart: Callable[[list[LabelCount]], alt.LayerChart],
) -> None:
    """A titled chart of ``rows`` and the same rows as a table in an expander."""
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
