"""Assemble the LangGraph pipeline from injected nodes."""

from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    PersistNode,
)
from my_agent.graph.routing import continue_or_end
from my_agent.graph.state import GraphState, Stage

DISCOVER = "discover"


@dataclass(frozen=True)
class PipelineNodes:
    """All nodes the graph needs, already built with their dependencies."""

    discover: DiscoverNode
    extract_exif: ExtractExifNode
    decode: DecodeNode
    annotate: AnnotateNode
    persist: PersistNode


PhotoGraph = CompiledStateGraph[GraphState, None, GraphState, GraphState]


def build_graph(
    nodes: PipelineNodes, checkpointer: BaseCheckpointSaver[str] | None = None
) -> PhotoGraph:
    """Wire discover -> exif -> decode -> annotate -> persist.

    After every step the run ends early if no file is left to process.
    """
    graph = StateGraph(GraphState)
    graph.add_node(DISCOVER, nodes.discover)
    graph.add_node(Stage.EXTRACT_EXIF.value, nodes.extract_exif)
    graph.add_node(Stage.DECODE.value, nodes.decode)
    graph.add_node(Stage.ANNOTATE.value, nodes.annotate)
    graph.add_node(Stage.PERSIST.value, nodes.persist)

    graph.add_edge(START, DISCOVER)
    _add_guarded_edge(graph, DISCOVER, Stage.EXTRACT_EXIF.value)
    _add_guarded_edge(graph, Stage.EXTRACT_EXIF.value, Stage.DECODE.value)
    _add_guarded_edge(graph, Stage.DECODE.value, Stage.ANNOTATE.value)
    _add_guarded_edge(graph, Stage.ANNOTATE.value, Stage.PERSIST.value)
    graph.add_edge(Stage.PERSIST.value, END)
    return graph.compile(checkpointer=checkpointer)


def _add_guarded_edge(graph: StateGraph[GraphState], source: str, target: str) -> None:
    graph.add_conditional_edges(source, continue_or_end(target), [target, END])
