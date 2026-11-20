"""Workflow steps. Each step is a small class built with its dependencies."""

from my_agent.workflow.nodes.annotate import AnnotateNode
from my_agent.workflow.nodes.decode import DecodeNode
from my_agent.workflow.nodes.discover import DiscoverNode
from my_agent.workflow.nodes.extract_exif import ExtractExifNode
from my_agent.workflow.nodes.fingerprint import FingerprintNode
from my_agent.workflow.nodes.load_failures import LoadFailuresNode
from my_agent.workflow.nodes.log_failures import LogFailuresNode
from my_agent.workflow.nodes.next_chunk import NextChunkNode
from my_agent.workflow.nodes.perceptual_hash import PerceptualHashNode
from my_agent.workflow.nodes.persist import PersistNode
from my_agent.workflow.nodes.record_chunk import RecordChunkNode
from my_agent.workflow.nodes.select_batch import SelectBatchNode
from my_agent.workflow.nodes.skip_known import SkipKnownNode

__all__ = [
    "AnnotateNode",
    "DecodeNode",
    "DiscoverNode",
    "ExtractExifNode",
    "FingerprintNode",
    "LoadFailuresNode",
    "LogFailuresNode",
    "NextChunkNode",
    "PerceptualHashNode",
    "PersistNode",
    "RecordChunkNode",
    "SelectBatchNode",
    "SkipKnownNode",
]
