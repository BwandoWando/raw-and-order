"""Tags tab: the tag network, its clusters and a table view.

Clicking a cluster card, or a tag in the network, shows the cluster's
photos in the Gallery: it sets the "Tags (all of)" filter to the tags in the
cluster's name and opens the Gallery tab. Tags always combine with AND, as in
the sidebar; all of a cluster's tags together would match almost no photo.
A tag in no cluster shows the photos with just that tag.

Example photos follow the sidebar filters: hovering a tag shows a 3x3 grid
of photos with it, and each cluster card shows one photo for each tag in its
name. They are picked at random once per browser session, so they hold still
while you work and differ next time.
"""

import base64
import random
from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path

import pandas as pd
import streamlit as st

from raw_and_order.analysis.tag_graph import CLUSTER_NAME_TAGS, top_partners
from raw_and_order.analysis.tag_samples import one_per_tag
from raw_and_order.schemas.query import PhotoQuery
from raw_and_order.schemas.tags import TagCluster, TagGraph
from raw_and_order.ui.charts import theme_for
from raw_and_order.ui.css import FOCUS_RING, keyed_prefix, overlay_button
from raw_and_order.ui.filters import show_tags
from raw_and_order.ui.library import PhotoLibrary
from raw_and_order.ui.navigation import Tab, open_tab
from raw_and_order.ui.tag_network import (
    OTHER,
    TOOLTIP_PHOTOS,
    TOOLTIP_TILE_PX,
    network_spec,
)

TOP_N_RANGE = (20, 100)
TOP_N_DEFAULT = 50
STRENGTH_RANGE = (0.05, 0.5)
STRENGTH_DEFAULT = 0.15
CHART_HEIGHT_PX = 640
NETWORK_KEY = "tag_network"
# Counts tag clicks handled. Each one gives the network a new key, so it is
# drawn afresh with nothing selected: otherwise the chart remembers the
# clicked tag, and the next click on it would only unselect it.
NETWORK_CLICKS_KEY = "tag_network_clicks"
CLUSTER_COLUMNS = 3
CLUSTER_THUMB_PX = 48  # the photos on a cluster card, one per tag in its name
SAMPLE_SEED_KEY = "tag_sample_seed"  # session state: fixes the random photos
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
{_CARD} img {{
    width: {CLUSTER_THUMB_PX}px;
    height: {CLUSTER_THUMB_PX}px;
    object-fit: cover;
    border-radius: 0.25rem;
}}
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
        "Hover to highlight a tag's links, drag to rearrange, scroll to zoom. "
        "Click a tag to see its cluster's photos in the Gallery."
    )
    theme = theme_for(getattr(st.context.theme, "type", None))
    key = f"{NETWORK_KEY}-{st.session_state.get(NETWORK_CLICKS_KEY, 0)}"
    tags = [node.tag for node in graph.nodes]
    samples = library.tag_samples(filters, tags, TOOLTIP_PHOTOS, _sample_seed())
    st.echarts_chart(
        network_spec(graph, theme, _tooltip_images(samples, library)),
        height=CHART_HEIGHT_PX,
        key=key,
        # The graph drawn now is the one the click refers to.
        on_select=partial(_open_clicked_tag, graph, key),
        alt="Network of the most-used tags, grouped into clusters.",
    )
    _clusters(graph, samples, library)
    with st.expander("Show as table"):
        st.dataframe(_table(graph), hide_index=True, width="stretch")


def _controls() -> tuple[int, float]:
    """The "Tags shown" and "Link strength" sliders: ``(top_n, min_strength)``."""
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


def _sample_seed() -> int:
    """This browser session's seed for the random example photos."""
    if SAMPLE_SEED_KEY not in st.session_state:
        st.session_state[SAMPLE_SEED_KEY] = random.randrange(2**31)
    return int(st.session_state[SAMPLE_SEED_KEY])


def _tooltip_images(
    samples: Mapping[str, Sequence[Path]], library: PhotoLibrary
) -> dict[str, list[str]]:
    """Each tag's example photos as small JPEG data URIs for its tooltip.

    Missing previews are left out. Thumbnails are cached, so this is cheap
    after the first run.
    """
    return {
        tag: [
            data_uri(image)
            for path in paths
            if (image := library.thumbnail(path, TOOLTIP_TILE_PX)) is not None
        ]
        for tag, paths in samples.items()
    }


def data_uri(jpeg: bytes) -> str:
    """``jpeg`` as a ``data:`` URL, to embed in an HTML tooltip."""
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def cluster_open_key(index: int) -> str:
    """Stable key of the invisible button over the ``index``-th cluster card."""
    return f"{CLUSTER_OPEN_PREFIX}{index}"


def _clusters(
    graph: TagGraph, samples: Mapping[str, Sequence[Path]], library: PhotoLibrary
) -> None:
    """One card per cluster; clicking a card shows its photos in the Gallery.

    ``samples`` are example previews per tag; each card shows one for each
    tag in its name.
    """
    st.subheader("Clusters", divider="gray")
    if not graph.clusters:
        st.caption("No clusters at this link strength; try a lower one.")
        return
    st.caption(
        "Click a cluster to see the photos with all the tags in its name in the "
        "Gallery."
    )
    st.html(CLUSTER_CSS)
    counts = {node.tag: node.photos for node in graph.nodes}
    columns = st.columns(CLUSTER_COLUMNS)
    for index, cluster in enumerate(graph.clusters):
        with (
            columns[index % CLUSTER_COLUMNS],
            st.container(border=True, key=f"{CLUSTER_TILE_PREFIX}{index}"),
        ):
            with st.container(horizontal=True, vertical_alignment="center"):
                with st.container():
                    st.markdown(f"**{cluster.name}**")
                    st.caption(
                        ", ".join(f"{tag} ({counts[tag]})" for tag in cluster.tags)
                    )
                _cluster_photos(cluster, samples, library)
            st.button(
                f"Show the photos of {cluster.name} in the Gallery",
                key=cluster_open_key(index),
                help="Show these photos in the Gallery",
                on_click=_show_in_gallery,
                args=(cluster.tags[:CLUSTER_NAME_TAGS],),
            )


def _cluster_photos(
    cluster: TagCluster, samples: Mapping[str, Sequence[Path]], library: PhotoLibrary
) -> None:
    """Small photos to the right of a card's text, one per tag in its name.

    A different photo for each tag where possible, in the order of the
    name. Each is named after its tag for screen readers.
    """
    picks = one_per_tag(samples, cluster.tags[:CLUSTER_NAME_TAGS])
    images = [
        (tag, image)
        for tag, path in picks
        if (image := library.thumbnail(path, CLUSTER_THUMB_PX)) is not None
    ]
    if not images:
        return
    with st.container(horizontal=True, width="content", gap="xsmall"):
        for tag, image in images:
            st.image(image, width=CLUSTER_THUMB_PX, alt=f"A photo tagged {tag}")


def tags_to_show(graph: TagGraph, node_index: int) -> list[str]:
    """The tags whose photos a click on the ``node_index``-th tag shows.

    The tags in its cluster's name (its biggest ones), or just the tag if it
    is in no cluster.
    """
    node = graph.nodes[node_index]
    if node.cluster is None:
        return [node.tag]
    return graph.clusters[node.cluster].tags[:CLUSTER_NAME_TAGS]


def _open_clicked_tag(graph: TagGraph, key: str) -> None:
    """Show the photos of the tag clicked in the network drawn with ``key``.

    Clicks on links are ignored. A handled click bumps
    :data:`NETWORK_CLICKS_KEY`, so the next run draws a fresh, unselected chart.
    """
    selection = st.session_state[key].selection
    clicked = [
        index
        for group in selection.selected
        if group["data_type"] in ("node", "main")
        for index in group["data_indices"]
    ]
    if clicked:
        _show_in_gallery(tags_to_show(graph, clicked[0]))
        st.session_state[NETWORK_CLICKS_KEY] = (
            st.session_state.get(NETWORK_CLICKS_KEY, 0) + 1
        )


def _show_in_gallery(tags: list[str]) -> None:
    """Filter to photos with all of ``tags`` and open the Gallery tab."""
    show_tags(tags)
    open_tab(Tab.GALLERY)


def _table(graph: TagGraph) -> pd.DataFrame:
    """One row per tag: photos, cluster and the tags it most often appears with."""
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
    """``tag``'s strongest links as ``other (shared photos)``, comma-separated."""
    links = top_partners(graph, tag, PARTNERS_SHOWN)
    return ", ".join(
        f"{link.target if link.source == tag else link.source} ({link.photos})"
        for link in links
    )
