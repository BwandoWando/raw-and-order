"""Assemble the LangGraph pipeline from injected nodes."""

import itertools
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from my_agent.graph.nodes import (
    AnnotateNode,
    BatchLimitNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    PerceptualHashNode,
    PersistNode,
    SkipUnchangedNode,
)
from my_agent.graph.routing import continue_or_end
from my_agent.graph.state import GraphState, Stage

DISCOVER = "discover"
SKIP_UNCHANGED = "skip_unchanged"
CHECK_LIMIT = "check_limit"


@dataclass(frozen=True)
class PipelineNodes:
    """All nodes the graph needs, already built with their dependencies."""

    discover: DiscoverNode
    fingerprint: FingerprintNode
    skip_unchanged: SkipUnchangedNode
    check_limit: BatchLimitNode
    extract_exif: ExtractExifNode
    decode: DecodeNode
    perceptual_hash: PerceptualHashNode
    annotate: AnnotateNode
    persist: PersistNode


PhotoGraph = CompiledStateGraph[GraphState, None, GraphState, GraphState]

PIPELINE_ORDER = (
    DISCOVER,
    Stage.FINGERPRINT.value,
    SKIP_UNCHANGED,
    CHECK_LIMIT,
    Stage.EXTRACT_EXIF.value,
    Stage.DECODE.value,
    Stage.PERCEPTUAL_HASH.value,
    Stage.ANNOTATE.value,
    Stage.PERSIST.value,
)


def build_graph(
    nodes: PipelineNodes, checkpointer: BaseCheckpointSaver[str] | None = None
) -> PhotoGraph:
    """Wire the nodes in :data:`PIPELINE_ORDER`.

    After every step the run ends early if no file is left to process.
    """
    graph = StateGraph(GraphState)
    graph.add_node(DISCOVER, nodes.discover)
    graph.add_node(Stage.FINGERPRINT.value, nodes.fingerprint)
    graph.add_node(SKIP_UNCHANGED, nodes.skip_unchanged)
    graph.add_node(CHECK_LIMIT, nodes.check_limit)
    graph.add_node(Stage.EXTRACT_EXIF.value, nodes.extract_exif)
    graph.add_node(Stage.DECODE.value, nodes.decode)
    graph.add_node(Stage.PERCEPTUAL_HASH.value, nodes.perceptual_hash)
    graph.add_node(Stage.ANNOTATE.value, nodes.annotate)
    graph.add_node(Stage.PERSIST.value, nodes.persist)

    graph.add_edge(START, PIPELINE_ORDER[0])
    for source, target in itertools.pairwise(PIPELINE_ORDER):
        _add_guarded_edge(graph, source, target)
    graph.add_edge(PIPELINE_ORDER[-1], END)
    return graph.compile(checkpointer=checkpointer)


def _add_guarded_edge(graph: StateGraph[GraphState], source: str, target: str) -> None:
    graph.add_conditional_edges(source, continue_or_end(target), [target, END])
