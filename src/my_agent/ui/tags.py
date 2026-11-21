"""Tags tab: the tag network, its clusters and a table view."""

import pandas as pd
import streamlit as st

from my_agent.analysis.tag_graph import top_partners
from my_agent.schemas.query import PhotoQuery
from my_agent.schemas.tags import TagGraph
from my_agent.ui.charts import theme_for
from my_agent.ui.library import PhotoLibrary
from my_agent.ui.tag_network import OTHER, network_spec

TOP_N_RANGE = (20, 100)
TOP_N_DEFAULT = 50
STRENGTH_RANGE = (0.05, 0.5)
STRENGTH_DEFAULT = 0.15
CHART_HEIGHT_PX = 640
CLUSTER_COLUMNS = 3
PARTNERS_SHOWN = 3


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


def _clusters(graph: TagGraph) -> None:
    st.subheader("Clusters", divider="gray")
    if not graph.clusters:
        st.caption("No clusters at this link strength; try a lower one.")
        return
    counts = {node.tag: node.photos for node in graph.nodes}
    columns = st.columns(CLUSTER_COLUMNS)
    for index, cluster in enumerate(graph.clusters):
        with columns[index % CLUSTER_COLUMNS], st.container(border=True):
            st.markdown(f"**{cluster.name}**")
            st.caption(", ".join(f"{tag} ({counts[tag]})" for tag in cluster.tags))


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
