"""Graph nodes. Each node is a small class built with its dependencies."""

from my_agent.graph.nodes.annotate import AnnotateNode
from my_agent.graph.nodes.decode_raw import DecodeRawNode
from my_agent.graph.nodes.discover import DiscoverNode
from my_agent.graph.nodes.extract_exif import ExtractExifNode
from my_agent.graph.nodes.persist import PersistNode

__all__ = [
    "AnnotateNode",
    "DecodeRawNode",
    "DiscoverNode",
    "ExtractExifNode",
    "PersistNode",
]
