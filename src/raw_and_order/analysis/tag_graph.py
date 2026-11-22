"""Build the tag network: counts, co-occurrence links, clusters and layout.

Pure functions over the tag lists of photos; the caller fetches them. Links
are scored by Jaccard overlap (photos with both tags / photos with either),
so tags that are merely common everywhere do not link to everything.
Clusters come from Louvain community detection; positions from a
force-directed layout. Both are seeded so the picture is stable.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import combinations

import networkx as nx

from raw_and_order.schemas.tags import TagCluster, TagGraph, TagLink, TagNode

SEED = 7
CLUSTER_NAME_TAGS = 3
LAYOUT_ITERATIONS = 200

TagCounts = Counter[str]
PairCounts = Counter[tuple[str, str]]


def build_tag_graph(
    tag_lists: Sequence[Sequence[str]], top_n: int, min_strength: float
) -> TagGraph:
    """Network of the ``top_n`` most-used tags.

    Args:
        tag_lists: The tags of each photo.
        top_n: How many of the most-used tags to keep.
        min_strength: Weakest Jaccard overlap still drawn as a link.
    """
    photo_tags = [set(tags) for tags in tag_lists]
    counts = count_tags(photo_tags)
    top = most_used(counts, top_n)
    links = strong_links(count_pairs(photo_tags, set(top)), counts, min_strength)
    network = _network(top, links)
    clusters = find_clusters(network, counts)
    positions = nx.spring_layout(
        network, weight="weight", seed=SEED, iterations=LAYOUT_ITERATIONS
    )
    membership = {tag: i for i, c in enumerate(clusters) for tag in c.tags}
    nodes = [
        TagNode(
            tag=tag,
            photos=counts[tag],
            cluster=membership.get(tag),
            x=round(float(positions[tag][0]), 4),
            y=round(float(positions[tag][1]), 4),
        )
        for tag in top
    ]
    return TagGraph(photos=len(photo_tags), nodes=nodes, links=links, clusters=clusters)


def count_tags(photo_tags: Iterable[set[str]]) -> TagCounts:
    """Photos per tag."""
    return Counter(tag for tags in photo_tags for tag in tags)


def most_used(counts: TagCounts, top_n: int) -> list[str]:
    """The ``top_n`` tags by photo count; ties broken alphabetically."""
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [tag for tag, _ in ranked[:top_n]]


def count_pairs(photo_tags: Iterable[set[str]], keep: set[str]) -> PairCounts:
    """Photos per pair of kept tags, each pair in alphabetical order."""
    return Counter(
        pair for tags in photo_tags for pair in combinations(sorted(tags & keep), 2)
    )


def strong_links(
    pairs: PairCounts, counts: TagCounts, min_strength: float
) -> list[TagLink]:
    """Pairs whose Jaccard overlap is at least ``min_strength``, strongest first."""
    links = [
        TagLink(source=a, target=b, photos=both, strength=jaccard(both, a, b, counts))
        for (a, b), both in pairs.items()
    ]
    kept = [link for link in links if link.strength >= min_strength]
    return sorted(kept, key=lambda link: (-link.strength, link.source, link.target))


def jaccard(both: int, a: str, b: str, counts: TagCounts) -> float:
    """Photos with both tags over photos with either, rounded to 3 places."""
    either = counts[a] + counts[b] - both
    return round(both / either, 3) if either else 0.0


def find_clusters(network: nx.Graph, counts: TagCounts) -> list[TagCluster]:
    """Groups of two or more linked tags, biggest first."""
    if network.number_of_edges() == 0:
        return []
    communities = nx.community.louvain_communities(network, weight="weight", seed=SEED)
    groups = [_by_count(group, counts) for group in communities if len(group) > 1]
    groups.sort(key=lambda tags: (-sum(counts[t] for t in tags), tags[0]))
    return [
        TagCluster(name=" · ".join(tags[:CLUSTER_NAME_TAGS]), tags=tags)
        for tags in groups
    ]


def top_partners(graph: TagGraph, tag: str, limit: int) -> list[TagLink]:
    """The strongest links of ``tag``, strongest first."""
    mine = [link for link in graph.links if tag in (link.source, link.target)]
    return mine[:limit]  # graph.links is already strongest first


def _by_count(group: Iterable[str], counts: TagCounts) -> list[str]:
    return sorted(group, key=lambda tag: (-counts[tag], tag))


def _network(tags: list[str], links: list[TagLink]) -> nx.Graph:
    network = nx.Graph()
    network.add_nodes_from(tags)
    network.add_weighted_edges_from(
        (link.source, link.target, link.strength) for link in links
    )
    return network
