"""Workflow steps. Each step is a small class built with its dependencies."""

from raw_and_order.workflow.steps.annotate import AnnotateStep
from raw_and_order.workflow.steps.decode import DecodeStep
from raw_and_order.workflow.steps.discover import DiscoverStep
from raw_and_order.workflow.steps.extract_exif import ExtractExifStep
from raw_and_order.workflow.steps.fingerprint import FingerprintStep
from raw_and_order.workflow.steps.load_failures import LoadFailuresStep
from raw_and_order.workflow.steps.log_failures import LogFailuresStep
from raw_and_order.workflow.steps.next_chunk import NextChunkStep
from raw_and_order.workflow.steps.perceptual_hash import PerceptualHashStep
from raw_and_order.workflow.steps.persist import PersistStep
from raw_and_order.workflow.steps.record_chunk import RecordChunkStep
from raw_and_order.workflow.steps.record_copies import RecordCopiesStep
from raw_and_order.workflow.steps.select_batch import SelectBatchStep
from raw_and_order.workflow.steps.skip_copies import SkipCopiesStep
from raw_and_order.workflow.steps.skip_known import SkipKnownStep

__all__ = [
    "AnnotateStep",
    "DecodeStep",
    "DiscoverStep",
    "ExtractExifStep",
    "FingerprintStep",
    "LoadFailuresStep",
    "LogFailuresStep",
    "NextChunkStep",
    "PerceptualHashStep",
    "PersistStep",
    "RecordChunkStep",
    "RecordCopiesStep",
    "SelectBatchStep",
    "SkipCopiesStep",
    "SkipKnownStep",
]
