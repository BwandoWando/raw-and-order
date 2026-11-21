from my_agent.schemas.tags import TagCluster, TagGraph, TagNode
from my_agent.ui.charts import DARK, LIGHT
from my_agent.ui.tag_network import (
    MAX_STYLED_CLUSTERS,
    OTHER,
    cluster_style,
    legend_names,
    network_spec,
)


def _graph(clusters: int, extra_unclustered: bool = False) -> TagGraph:
    nodes = [
        TagNode(tag=f"t{i}", photos=10 + i, cluster=i, x=i, y=i)
        for i in range(clusters)
    ]
    if extra_unclustered:
        nodes.append(TagNode(tag="lonely", photos=1, cluster=None, x=0, y=0))
    return TagGraph(
        photos=50,
        nodes=nodes,
        links=[],
        clusters=[TagCluster(name=f"c{i}", tags=[f"t{i}"]) for i in range(clusters)],
    )


def test_nine_clusters_get_distinct_colour_and_shape_pairs() -> None:
    styles = {cluster_style(i, LIGHT) for i in range(MAX_STYLED_CLUSTERS)}

    assert len(styles) == MAX_STYLED_CLUSTERS


def test_clusters_past_nine_and_unclustered_tags_are_grey() -> None:
    assert cluster_style(MAX_STYLED_CLUSTERS, LIGHT) == (LIGHT.muted, "circle")
    assert cluster_style(None, DARK) == (DARK.muted, "circle")


def test_dark_theme_uses_its_own_hues() -> None:
    assert cluster_style(0, DARK)[0] != cluster_style(0, LIGHT)[0]


def test_legend_adds_other_only_when_needed() -> None:
    assert legend_names(_graph(2)) == ["c0", "c1"]
    assert legend_names(_graph(2, extra_unclustered=True)) == ["c0", "c1", OTHER]
    assert legend_names(_graph(11))[-1] == OTHER
    assert len(legend_names(_graph(11))) == MAX_STYLED_CLUSTERS + 1


def test_spec_puts_overflow_tags_in_the_other_category() -> None:
    spec = network_spec(_graph(11), LIGHT)

    series = spec["series"][0]
    categories = [node["category"] for node in series["data"]]
    assert categories[:MAX_STYLED_CLUSTERS] == list(range(MAX_STYLED_CLUSTERS))
    assert set(categories[MAX_STYLED_CLUSTERS:]) == {MAX_STYLED_CLUSTERS}
    assert series["categories"][-1]["name"] == OTHER


def test_bigger_tags_get_bigger_symbols() -> None:
    sizes = [
        n["symbolSize"] for n in network_spec(_graph(3), LIGHT)["series"][0]["data"]
    ]

    assert sizes == sorted(sizes)
    assert sizes[-1] == 48
