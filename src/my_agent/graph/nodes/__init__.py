"""Graph nodes. Each node is a small class built with its dependencies."""

from my_agent.graph.nodes.annotate import AnnotateNode
from my_agent.graph.nodes.check_limit import BatchLimitNode
from my_agent.graph.nodes.decode import DecodeNode
from my_agent.graph.nodes.discover import DiscoverNode
from my_agent.graph.nodes.extract_exif import ExtractExifNode
from my_agent.graph.nodes.fingerprint import FingerprintNode
from my_agent.graph.nodes.perceptual_hash import PerceptualHashNode
from my_agent.graph.nodes.persist import PersistNode
from my_agent.graph.nodes.skip_unchanged import SkipUnchangedNode

__all__ = [
    "AnnotateNode",
    "BatchLimitNode",
    "DecodeNode",
    "DiscoverNode",
    "ExtractExifNode",
    "FingerprintNode",
    "PerceptualHashNode",
    "PersistNode",
    "SkipUnchangedNode",
]
