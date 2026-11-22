"""Single-series bar charts styled for light and dark themes.

Colors: one validated blue per theme (single series, so no legend - the
chart title names it); text and axes use recessive neutral inks.
"""

from dataclasses import dataclass
from typing import cast

import altair as alt
import pandas as pd

from raw_and_order.schemas.query import LabelCount

BAR_THICKNESS_PX = 18  # cap is 24px; leftover band space stays empty
ROW_HEIGHT_PX = 28
AXIS_HEIGHT_PX = 40  # room for the value axis under horizontal bars
BAND_PADDING = 0.3  # share of each row left empty, so bars never touch
CORNER_RADIUS_PX = 4


@dataclass(frozen=True)
class ChartTheme:
    """Colors for one Streamlit theme."""

    bar: str
    text: str
    muted: str
    grid: str
    baseline: str


LIGHT = ChartTheme(
    bar="#2a78d6", text="#52514e", muted="#898781", grid="#e1e0d9", baseline="#c3c2b7"
)
DARK = ChartTheme(
    bar="#3987e5", text="#c3c2b7", muted="#898781", grid="#2c2c2a", baseline="#383835"
)


def theme_for(theme_type: str | None) -> ChartTheme:
    """Pick the chart theme for Streamlit's ``"light"`` / ``"dark"``."""
    return DARK if theme_type == "dark" else LIGHT


def rows_frame(rows: list[LabelCount]) -> pd.DataFrame:
    """Turn :class:`LabelCount` rows into a ``label`` / ``count`` DataFrame."""
    return pd.DataFrame(
        {"label": [r.label for r in rows], "count": [r.count for r in rows]}
    )


def horizontal_bars(rows: list[LabelCount], theme: ChartTheme) -> alt.LayerChart:
    """Categories down the side, longest bar first, value at each bar's tip."""
    data = rows_frame(rows)
    order = alt.SortField("count", order="descending")
    base = alt.Chart(data).encode(
        y=alt.Y(
            "label:N",
            sort=order,
            title=None,
            axis=alt.Axis(grid=False),
            scale=alt.Scale(paddingInner=BAND_PADDING),
        ),
        x=alt.X(
            "count:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True)
        ),
        tooltip=[
            alt.Tooltip("label:N", title="Name"),
            alt.Tooltip("count:Q", title="Photos"),
        ],
    )
    bars = base.mark_bar(
        size=BAR_THICKNESS_PX, cornerRadiusEnd=CORNER_RADIUS_PX, color=theme.bar
    )
    labels = base.mark_text(align="left", dx=4, color=theme.text).encode(text="count:Q")
    height = len(rows) * ROW_HEIGHT_PX + AXIS_HEIGHT_PX
    return _style((bars + labels).properties(height=height), theme)


def columns_by_month(rows: list[LabelCount], theme: ChartTheme) -> alt.LayerChart:
    """Months left to right (oldest first), value on each column's cap."""
    return ordered_columns(rows, theme, x_title=None, x_name="Month")


def ordered_columns(
    rows: list[LabelCount],
    theme: ChartTheme,
    x_title: str | None,
    x_name: str,
) -> alt.LayerChart:
    """Columns for ordered categories, left to right in the order given.

    Args:
        rows: One column per row, in this order.
        theme: Colours for the current Streamlit theme.
        x_title: Title under the x axis, or ``None`` for none.
        x_name: Name of the category in the tooltip.
    """
    data = rows_frame(rows)
    base = alt.Chart(data).encode(
        x=alt.X(
            "label:O",
            sort=None,
            title=x_title,
            axis=alt.Axis(labelAngle=0, grid=False, titleColor=theme.muted),
        ),
        y=alt.Y(
            "count:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d", grid=True)
        ),
        tooltip=[
            alt.Tooltip("label:O", title=x_name),
            alt.Tooltip("count:Q", title="Photos"),
        ],
    )
    bars = base.mark_bar(
        size=BAR_THICKNESS_PX, cornerRadiusEnd=CORNER_RADIUS_PX, color=theme.bar
    )
    labels = base.mark_text(baseline="bottom", dy=-4, color=theme.text).encode(
        text="count:Q"
    )
    return _style((bars + labels).properties(height=240), theme)


def _style(chart: alt.LayerChart, theme: ChartTheme) -> alt.LayerChart:
    """Theme the axes and drop the chart's outer border."""
    styled = chart.configure_view(stroke=None).configure_axis(
        gridColor=theme.grid,
        gridWidth=1,
        domainColor=theme.baseline,
        tickColor=theme.baseline,
        labelColor=theme.muted,
        labelFontSize=12,
    )
    return cast(alt.LayerChart, styled)
