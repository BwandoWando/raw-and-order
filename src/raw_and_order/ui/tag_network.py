"""ECharts option for the tag network.

Each cluster is a colour and shape pair. A network is an all-pairs chart
(any two clusters can sit side by side), and only the first three
categorical hues stay distinguishable all-pairs, colour-blind included, in
both themes (checked with the data-viz palette validator). So three hues x
three shapes give up to nine clusters; the rest, and tags with no cluster,
are grey "Other". Every tag is also labelled by name, and the clusters are
listed in text next to the chart, so colour is never the only cue.
"""

import math
from typing import Any

from raw_and_order.schemas.tags import TagGraph, TagNode
from raw_and_order.ui.charts import DARK, ChartTheme

CLUSTER_HUES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a")  # blue, orange, aqua
CLUSTER_HUES_DARK = ("#3987e5", "#d95926", "#199e70")
SHAPES = ("circle", "diamond", "triangle")
MAX_STYLED_CLUSTERS = len(CLUSTER_HUES_LIGHT) * len(SHAPES)
OTHER = "Other"
MIN_SYMBOL_PX = 10
MAX_SYMBOL_PX = 48
MAX_LINK_WIDTH_PX = 6


def cluster_style(index: int | None, theme: ChartTheme) -> tuple[str, str]:
    """Colour and shape of a cluster; grey circle for ``None`` or past nine."""
    if index is None or index >= MAX_STYLED_CLUSTERS:
        return theme.muted, SHAPES[0]
    hues = CLUSTER_HUES_DARK if theme is DARK else CLUSTER_HUES_LIGHT
    return hues[index % len(hues)], SHAPES[index // len(hues)]


def legend_names(graph: TagGraph) -> list[str]:
    """One legend entry per styled cluster, plus "Other" if any tag needs it."""
    names = [c.name for c in graph.clusters[:MAX_STYLED_CLUSTERS]]
    if any(_category(node, len(names)) == len(names) for node in graph.nodes):
        names.append(OTHER)
    return names


def network_spec(graph: TagGraph, theme: ChartTheme) -> dict[str, Any]:
    """ECharts graph option: tags sized by photo count, links by overlap."""
    names = legend_names(graph)
    styled = min(len(graph.clusters), MAX_STYLED_CLUSTERS)
    largest = max((node.photos for node in graph.nodes), default=0)
    return {
        "legend": {"data": names, "top": 0, "textStyle": {"color": theme.text}},
        "tooltip": {},
        "series": [
            {
                "type": "graph",
                "layout": "none",  # positions come from the seeded layout
                "top": 48,
                "roam": True,
                "draggable": True,
                # A click selects one tag; the Tags tab then opens its photos.
                "selectedMode": "single",
                "select": {"itemStyle": {"borderColor": theme.text, "borderWidth": 2}},
                "categories": [
                    _category_spec(i, n, theme) for i, n in enumerate(names)
                ],
                "data": [_node(node, styled, largest, theme) for node in graph.nodes],
                "links": [
                    {
                        "source": link.source,
                        "target": link.target,
                        "value": link.photos,
                        "lineStyle": {"width": 1 + MAX_LINK_WIDTH_PX * link.strength},
                    }
                    for link in graph.links
                ],
                "label": {
                    "show": True,
                    "position": "right",
                    "color": theme.text,
                    "fontSize": 11,
                },
                "labelLayout": {"hideOverlap": True},
                "lineStyle": {"color": theme.baseline, "opacity": 0.7},
                "emphasis": {"focus": "adjacency", "lineStyle": {"opacity": 1}},
                "tooltip": {"formatter": "{b}: {c} photos"},
            }
        ],
    }


def _category(node: TagNode, styled: int) -> int:
    """Legend slot of a node; ``styled`` is the shared "Other" slot."""
    return (
        node.cluster if node.cluster is not None and node.cluster < styled else styled
    )


def _category_spec(index: int, name: str, theme: ChartTheme) -> dict[str, Any]:
    colour, shape = cluster_style(None if name == OTHER else index, theme)
    return {"name": name, "symbol": shape, "itemStyle": {"color": colour}}


def _node(
    node: TagNode, styled: int, largest: int, theme: ChartTheme
) -> dict[str, Any]:
    colour, shape = cluster_style(node.cluster, theme)
    return {
        "name": node.tag,
        "value": node.photos,
        "x": node.x,
        "y": -node.y,  # screen y grows downwards
        "category": _category(node, styled),
        "symbol": shape,
        "symbolSize": _symbol_size(node.photos, largest),
        "itemStyle": {"color": colour},
    }


def _symbol_size(photos: int, largest: int) -> float:
    """Area grows with photo count, between the min and max sizes."""
    share = math.sqrt(photos / largest) if largest else 0.0
    return round(MIN_SYMBOL_PX + (MAX_SYMBOL_PX - MIN_SYMBOL_PX) * share, 1)
