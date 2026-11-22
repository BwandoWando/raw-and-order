"""Tags tab: the tag network, its clusters and a table view.

Clicking a cluster card shows the cluster's photos in the Gallery: it sets
the "Tags (any of)" filter to the cluster's tags and opens the Gallery tab.
"""

import pandas as pd
import streamlit as st

from raw_and_order.analysis.tag_graph import top_partners
from raw_and_order.schemas.query import PhotoQuery
from raw_and_order.schemas.tags import TagGraph
from raw_and_order.ui.charts import theme_for
from raw_and_order.ui.css import FOCUS_RING, keyed_prefix, overlay_button
from raw_and_order.ui.filters import show_any_of_tags
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.ui.navigation import Tab, open_tab
from raw_and_order.ui.tag_network import OTHER, network_spec

TOP_N_RANGE = (20, 100)
TOP_N_DEFAULT = 50
STRENGTH_RANGE = (0.05, 0.5)
STRENGTH_DEFAULT = 0.15
CHART_HEIGHT_PX = 640
CLUSTER_COLUMNS = 3
PARTNERS_SHOWN = 3
CLUSTER_TILE_PREFIX = "tag-cluster-"  # the card
# The overlay's prefix must not contain the card's: the CSS selects cards with
# [class*="st-key-tag-cluster-"], which would also match "tag-cluster-open-".
CLUSTER_OPEN_PREFIX = "tag-clusteropen-"
_CARD = keyed_prefix(CLUSTER_TILE_PREFIX)
CLUSTER_CSS = f"""
<style>
{overlay_button(_CARD, keyed_prefix(CLUSTER_OPEN_PREFIX))}
{_CARD} {{ transition: background 120ms ease-in-out; }}
{_CARD}:hover {{ background: rgba(128, 128, 128, 0.1); }}
{_CARD}:has(button:focus-visible) {{
    outline: 3px solid {FOCUS_RING};
    outline-offset: 2px;
}}
</style>
"""


def render_tags(filters: PhotoQuery, library: PhotoLibrary) -> None:
    """Draw the controls, the network, the cluster cards and the table."""
    top_n, min_strength = _controls()
    graph = library.tag_graph(filters, top_n, min_strength)
    if not graph.nodes:
        st.info("No tagged photos match these filters.")
        return
    st.caption(
        f"The {len(graph.nodes)} most-used tags across {graph.photos} photos. "
        "Bigger means more photos; lines join tags that often appear together. "
        "Hover to highlight a tag's links, drag to rearrange, scroll to zoom."
    )
    theme = theme_for(getattr(st.context.theme, "type", None))
    st.echarts_chart(
        network_spec(graph, theme),
        height=CHART_HEIGHT_PX,
        key="tag_network",
        alt="Network of the most-used tags, grouped into clusters.",
    )
    _clusters(graph)
    with st.expander("Show as table"):
        st.dataframe(_table(graph), hide_index=True, width="stretch")


def _controls() -> tuple[int, float]:
    top_col, strength_col = st.columns(2)
    top_n = top_col.slider(
        "Tags shown",
        *TOP_N_RANGE,
        value=TOP_N_DEFAULT,
        step=10,
        key="t_top_n",
        help="The most-used tags, by number of photos.",
    )
    min_strength = strength_col.slider(
        "Link strength",
        *STRENGTH_RANGE,
        value=STRENGTH_DEFAULT,
        step=0.05,
        key="t_strength",
        help="Draw a line only if this share of the photos with either tag "
        "have both. Higher means fewer, stronger links.",
    )
    return top_n, min_strength


def cluster_open_key(index: int) -> str:
    """Stable key of the invisible button over the ``index``-th cluster card."""
    return f"{CLUSTER_OPEN_PREFIX}{index}"


def _clusters(graph: TagGraph) -> None:
    """One card per cluster; clicking a card shows its photos in the Gallery."""
    st.subheader("Clusters", divider="gray")
    if not graph.clusters:
        st.caption("No clusters at this link strength; try a lower one.")
        return
    st.caption("Click a cluster to see its photos (any of its tags) in the Gallery.")
    st.html(CLUSTER_CSS)
    counts = {node.tag: node.photos for node in graph.nodes}
    columns = st.columns(CLUSTER_COLUMNS)
    for index, cluster in enumerate(graph.clusters):
        with (
            columns[index % CLUSTER_COLUMNS],
            st.container(border=True, key=f"{CLUSTER_TILE_PREFIX}{index}"),
        ):
            st.markdown(f"**{cluster.name}**")
            st.caption(", ".join(f"{tag} ({counts[tag]})" for tag in cluster.tags))
            st.button(
                f"Show the photos of {cluster.name} in the Gallery",
                key=cluster_open_key(index),
                help="Show these photos in the Gallery",
                on_click=_show_in_gallery,
                args=(cluster.tags,),
            )


def _show_in_gallery(tags: list[str]) -> None:
    """Filter to photos with any of ``tags`` and open the Gallery tab."""
    show_any_of_tags(tags)
    open_tab(Tab.GALLERY)


def _table(graph: TagGraph) -> pd.DataFrame:
    names = [cluster.name for cluster in graph.clusters]
    return pd.DataFrame(
        {
            "Tag": [node.tag for node in graph.nodes],
            "Photos": [node.photos for node in graph.nodes],
            "Cluster": [
                OTHER if node.cluster is None else names[node.cluster]
                for node in graph.nodes
            ],
            "Often with": [_partners(graph, node.tag) for node in graph.nodes],
        }
    )


def _partners(graph: TagGraph, tag: str) -> str:
    links = top_partners(graph, tag, PARTNERS_SHOWN)
    return ", ".join(
        f"{link.target if link.source == tag else link.source} ({link.photos})"
        for link in links
    )
