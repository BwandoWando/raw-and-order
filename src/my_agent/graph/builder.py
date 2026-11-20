"""Assemble the LangGraph pipeline from injected nodes.

```
discover -> fingerprint -> skip_unchanged -> select_batch
                                                 |
        +----------------------------------------+
        v
   next_chunk -> extract_exif -> decode -> perceptual_hash -> annotate -> persist
        ^                                                                    |
        +----------------- record_chunk (more queued?) <--------------------+
```
Inside a chunk, if every file has failed the remaining steps are skipped
and the chunk goes straight to ``record_chunk``.
"""

import itertools
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from my_agent.graph.nodes import (
    AnnotateNode,
    DecodeNode,
    DiscoverNode,
    ExtractExifNode,
    FingerprintNode,
    NextChunkNode,
    PerceptualHashNode,
    PersistNode,
    RecordChunkNode,
    SelectBatchNode,
    SkipUnchangedNode,
)
from my_agent.graph.routing import continue_or, next_chunk_or
from my_agent.graph.state import GraphState, Stage

DISCOVER = "discover"
SKIP_UNCHANGED = "skip_unchanged"
SELECT_BATCH = "select_batch"
NEXT_CHUNK = "next_chunk"
RECORD_CHUNK = "record_chunk"

PLANNING_STEPS = (DISCOVER, Stage.FINGERPRINT.value, SKIP_UNCHANGED, SELECT_BATCH)
CHUNK_STEPS = (
    NEXT_CHUNK,
    Stage.EXTRACT_EXIF.value,
    Stage.DECODE.value,
    Stage.PERCEPTUAL_HASH.value,
    Stage.ANNOTATE.value,
    Stage.PERSIST.value,
    RECORD_CHUNK,
)


@dataclass(frozen=True)
class PipelineNodes:
    """All nodes the graph needs, already built with their dependencies."""

    discover: DiscoverNode
    fingerprint: FingerprintNode
    skip_unchanged: SkipUnchangedNode
    select_batch: SelectBatchNode
    next_chunk: NextChunkNode
    extract_exif: ExtractExifNode
    decode: DecodeNode
    perceptual_hash: PerceptualHashNode
    annotate: AnnotateNode
    persist: PersistNode
    record_chunk: RecordChunkNode


PhotoGraph = CompiledStateGraph[GraphState, None, GraphState, GraphState]


def build_graph(
    nodes: PipelineNodes, checkpointer: BaseCheckpointSaver[str] | None = None
) -> PhotoGraph:
    """Wire the planning steps, then the chunk loop."""
    graph = StateGraph(GraphState)
    for name in (*PLANNING_STEPS, *CHUNK_STEPS):
        graph.add_node(name, getattr(nodes, name))

    graph.add_edge(START, PLANNING_STEPS[0])
    for source, target in itertools.pairwise(PLANNING_STEPS):
        graph.add_edge(source, target)
    _add_loop_entry(graph, SELECT_BATCH)

    # next_chunk ... annotate: skip ahead to record_chunk if the chunk is empty
    for source, target in itertools.pairwise(CHUNK_STEPS[:-1]):
        graph.add_conditional_edges(
            source, continue_or(target, RECORD_CHUNK), [target, RECORD_CHUNK]
        )
    graph.add_edge(Stage.PERSIST.value, RECORD_CHUNK)
    _add_loop_entry(graph, RECORD_CHUNK)
    return graph.compile(checkpointer=checkpointer)


def steps_per_chunk() -> int:
    """Graph steps one chunk takes; used to size LangGraph's recursion limit."""
    return len(CHUNK_STEPS)


def planning_steps() -> int:
    """Graph steps before the first chunk."""
    return len(PLANNING_STEPS)


def _add_loop_entry(graph: StateGraph[GraphState], source: str) -> None:
    graph.add_conditional_edges(
        source, next_chunk_or(NEXT_CHUNK, END), [NEXT_CHUNK, END]
    )
