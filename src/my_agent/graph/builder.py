"""Assemble the LangGraph pipeline from injected nodes.

```
START -> discover ------+                       (normal run)
START -> load_failures -+                       (--reprocess-failed)
                        v
   fingerprint -> skip_known -> select_batch -> log_planning_failures
                                                    |
        +-------------------------------------------+
        v
   next_chunk -> extract_exif -> decode -> perceptual_hash -> annotate -> persist
        ^                                                                    |
        +------ record_chunk (more queued?) <------ log_failures <-----------+
```
Inside a chunk, if every file has failed the remaining steps are skipped and
the chunk goes straight to ``log_failures``.
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
    LoadFailuresNode,
    LogFailuresNode,
    NextChunkNode,
    PerceptualHashNode,
    PersistNode,
    RecordChunkNode,
    SelectBatchNode,
    SkipKnownNode,
)
from my_agent.graph.routing import continue_or, next_chunk_or, start_from
from my_agent.graph.state import GraphState, Stage

DISCOVER = "discover"
LOAD_FAILURES = "load_failures"
SKIP_KNOWN = "skip_known"
SELECT_BATCH = "select_batch"
LOG_PLANNING_FAILURES = "log_planning_failures"
NEXT_CHUNK = "next_chunk"
LOG_FAILURES = "log_failures"
RECORD_CHUNK = "record_chunk"

PLANNING_STEPS = (
    Stage.FINGERPRINT.value,
    SKIP_KNOWN,
    SELECT_BATCH,
    LOG_PLANNING_FAILURES,
)
CHUNK_STEPS = (
    NEXT_CHUNK,
    Stage.EXTRACT_EXIF.value,
    Stage.DECODE.value,
    Stage.PERCEPTUAL_HASH.value,
    Stage.ANNOTATE.value,
    Stage.PERSIST.value,
    LOG_FAILURES,
    RECORD_CHUNK,
)


@dataclass(frozen=True)
class PipelineNodes:
    """All nodes the graph needs, already built with their dependencies."""

    discover: DiscoverNode
    load_failures: LoadFailuresNode
    fingerprint: FingerprintNode
    skip_known: SkipKnownNode
    select_batch: SelectBatchNode
    log_planning_failures: LogFailuresNode
    next_chunk: NextChunkNode
    extract_exif: ExtractExifNode
    decode: DecodeNode
    perceptual_hash: PerceptualHashNode
    annotate: AnnotateNode
    persist: PersistNode
    log_failures: LogFailuresNode
    record_chunk: RecordChunkNode


PhotoGraph = CompiledStateGraph[GraphState, None, GraphState, GraphState]


def build_graph(
    nodes: PipelineNodes, checkpointer: BaseCheckpointSaver[str] | None = None
) -> PhotoGraph:
    """Wire the entry points, the planning steps, then the chunk loop."""
    graph = StateGraph(GraphState)
    for name in (DISCOVER, LOAD_FAILURES, *PLANNING_STEPS, *CHUNK_STEPS):
        graph.add_node(name, getattr(nodes, name))

    graph.add_conditional_edges(
        START, start_from(DISCOVER, LOAD_FAILURES), [DISCOVER, LOAD_FAILURES]
    )
    graph.add_edge(DISCOVER, PLANNING_STEPS[0])
    graph.add_edge(LOAD_FAILURES, PLANNING_STEPS[0])
    for source, target in itertools.pairwise(PLANNING_STEPS):
        graph.add_edge(source, target)
    _add_loop_entry(graph, LOG_PLANNING_FAILURES)

    # next_chunk ... annotate: skip ahead to log_failures if the chunk is empty
    processing = CHUNK_STEPS[: CHUNK_STEPS.index(Stage.PERSIST.value) + 1]
    for source, target in itertools.pairwise(processing):
        graph.add_conditional_edges(
            source, continue_or(target, LOG_FAILURES), [target, LOG_FAILURES]
        )
    graph.add_edge(Stage.PERSIST.value, LOG_FAILURES)
    graph.add_edge(LOG_FAILURES, RECORD_CHUNK)
    _add_loop_entry(graph, RECORD_CHUNK)
    return graph.compile(checkpointer=checkpointer)


def steps_per_chunk() -> int:
    """Graph steps one chunk takes; used to size LangGraph's recursion limit."""
    return len(CHUNK_STEPS)


def planning_steps() -> int:
    """Graph steps before the first chunk, including the entry step."""
    return len(PLANNING_STEPS) + 1


def _add_loop_entry(graph: StateGraph[GraphState], source: str) -> None:
    graph.add_conditional_edges(
        source, next_chunk_or(NEXT_CHUNK, END), [NEXT_CHUNK, END]
    )
