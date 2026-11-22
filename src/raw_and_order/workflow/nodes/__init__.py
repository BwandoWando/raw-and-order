"""Workflow steps. Each step is a small class built with its dependencies."""

from raw_and_order.workflow.nodes.annotate import AnnotateNode
from raw_and_order.workflow.nodes.decode import DecodeNode
from raw_and_order.workflow.nodes.discover import DiscoverNode
from raw_and_order.workflow.nodes.extract_exif import ExtractExifNode
from raw_and_order.workflow.nodes.fingerprint import FingerprintNode
from raw_and_order.workflow.nodes.load_failures import LoadFailuresNode
from raw_and_order.workflow.nodes.log_failures import LogFailuresNode
from raw_and_order.workflow.nodes.next_chunk import NextChunkNode
from raw_and_order.workflow.nodes.perceptual_hash import PerceptualHashNode
from raw_and_order.workflow.nodes.persist import PersistNode
from raw_and_order.workflow.nodes.record_chunk import RecordChunkNode
from raw_and_order.workflow.nodes.record_copies import RecordCopiesNode
from raw_and_order.workflow.nodes.select_batch import SelectBatchNode
from raw_and_order.workflow.nodes.skip_copies import SkipCopiesNode
from raw_and_order.workflow.nodes.skip_known import SkipKnownNode

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
    "RecordCopiesNode",
    "SelectBatchNode",
    "SkipCopiesNode",
    "SkipKnownNode",
]
