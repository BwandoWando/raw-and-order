"""Graph nodes. Each node is a small class built with its dependencies."""

from my_agent.graph.nodes.annotate import AnnotateNode
from my_agent.graph.nodes.decode import DecodeNode
from my_agent.graph.nodes.discover import DiscoverNode
from my_agent.graph.nodes.extract_exif import ExtractExifNode
from my_agent.graph.nodes.fingerprint import FingerprintNode
from my_agent.graph.nodes.next_chunk import NextChunkNode
from my_agent.graph.nodes.perceptual_hash import PerceptualHashNode
from my_agent.graph.nodes.persist import PersistNode
from my_agent.graph.nodes.record_chunk import RecordChunkNode
from my_agent.graph.nodes.select_batch import SelectBatchNode
from my_agent.graph.nodes.skip_unchanged import SkipUnchangedNode

__all__ = [
    "AnnotateNode",
    "DecodeNode",
    "DiscoverNode",
    "ExtractExifNode",
    "FingerprintNode",
    "NextChunkNode",
    "PerceptualHashNode",
    "PersistNode",
    "RecordChunkNode",
    "SelectBatchNode",
    "SkipUnchangedNode",
]
