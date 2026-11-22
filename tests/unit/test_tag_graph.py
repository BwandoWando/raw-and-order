from raw_and_order.analysis.tag_graph import (
    build_tag_graph,
    count_pairs,
    count_tags,
    jaccard,
    most_used,
    strong_links,
    top_partners,
)

# Two clear groups: a beach group and a city group, joined by one weak photo.
PHOTOS = [
    ["sea", "sand", "sky"],
    ["sea", "sand", "sky"],
    ["sea", "sand"],
    ["city", "night", "neon"],
    ["city", "night", "neon"],
    ["city", "night"],
    ["sky", "city"],
]


def test_counts_each_tag_once_per_photo() -> None:
    counts = count_tags([{"a", "b"}, {"a"}])

    assert counts == {"a": 2, "b": 1}


def test_most_used_breaks_ties_alphabetically() -> None:
    assert most_used(count_tags([{"b"}, {"a"}, {"c"}, {"c"}]), 2) == ["c", "a"]


def test_pairs_only_between_kept_tags() -> None:
    pairs = count_pairs([{"a", "b", "c"}, {"b", "a"}], keep={"a", "b"})

    assert pairs == {("a", "b"): 2}


def test_jaccard_is_both_over_either() -> None:
    counts = count_tags([{"a", "b"}, {"a"}, {"b"}])

    assert jaccard(1, "a", "b", counts) == round(1 / 3, 3)


def test_weak_links_are_dropped_and_strongest_come_first() -> None:
    photos = [set(p) for p in PHOTOS]
    counts = count_tags(photos)
    links = strong_links(count_pairs(photos, set(counts)), counts, 0.5)

    assert ("city", "sky") not in {(link.source, link.target) for link in links}
    assert links == sorted(links, key=lambda link: -link.strength)


def test_graph_finds_the_two_groups() -> None:
    graph = build_tag_graph(PHOTOS, top_n=10, min_strength=0.3)

    groups = sorted(sorted(cluster.tags) for cluster in graph.clusters)
    assert groups == [["city", "neon", "night"], ["sand", "sea", "sky"]]
    assert graph.photos == len(PHOTOS)
    by_tag = {node.tag: node for node in graph.nodes}
    assert by_tag["sea"].cluster == by_tag["sand"].cluster
    assert by_tag["sea"].cluster != by_tag["city"].cluster


def test_graph_is_stable_between_runs() -> None:
    assert build_tag_graph(PHOTOS, 10, 0.3) == build_tag_graph(PHOTOS, 10, 0.3)


def test_cluster_name_lists_its_biggest_tags_first_ties_alphabetical() -> None:
    graph = build_tag_graph(PHOTOS, top_n=10, min_strength=0.3)

    assert {c.name for c in graph.clusters} == {
        "sand · sea · sky",  # tied at 3 photos: alphabetical
        "city · night · neon",
    }


def test_top_n_limits_the_nodes() -> None:
    graph = build_tag_graph(PHOTOS, top_n=2, min_strength=0.0)

    assert [node.tag for node in graph.nodes] == ["city", "night"]


def test_tags_without_links_have_no_cluster() -> None:
    graph = build_tag_graph([["a", "b"], ["a", "b"], ["c"]], 10, 0.5)

    assert {n.tag: n.cluster for n in graph.nodes}["c"] is None


def test_no_tags_gives_an_empty_graph() -> None:
    graph = build_tag_graph([[], []], 50, 0.15)

    assert (graph.nodes, graph.links, graph.clusters) == ([], [], [])
    assert graph.photos == 2


def test_top_partners_of_a_tag() -> None:
    graph = build_tag_graph(PHOTOS, 10, 0.3)

    partners = top_partners(graph, "city", 1)

    assert len(partners) == 1
    assert "night" in (partners[0].source, partners[0].target)
