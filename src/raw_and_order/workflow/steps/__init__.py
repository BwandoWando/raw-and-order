"""Workflow steps, in the order :mod:`raw_and_order.workflow.runner` runs them.

Each step is a small class built with its dependencies; calling it with the
:class:`WorkflowState` returns a :class:`StateUpdate` with the fields it
changed.
"""

from raw_and_order.workflow.steps.annotate import AnnotateStep
from raw_and_order.workflow.steps.decode import DecodeStep
from raw_and_order.workflow.steps.discover import DiscoverStep
from raw_and_order.workflow.steps.extract_exif import ExtractExifStep
from raw_and_order.workflow.steps.fingerprint import FingerprintStep
from raw_and_order.workflow.steps.load_failures import LoadFailuresStep
from raw_and_order.workflow.steps.next_chunk import NextChunkStep
from raw_and_order.workflow.steps.perceptual_hash import PerceptualHashStep
from raw_and_order.workflow.steps.persist import PersistStep
from raw_and_order.workflow.steps.select_batch import SelectBatchStep
from raw_and_order.workflow.steps.skip_copies import SkipCopiesStep
from raw_and_order.workflow.steps.skip_known import SkipKnownStep
from raw_and_order.workflow.steps.sync_copy_log import SyncCopyLogStep
from raw_and_order.workflow.steps.sync_failure_log import SyncFailureLogStep
from raw_and_order.workflow.steps.tally_chunk import TallyChunkStep

__all__ = [
    "AnnotateStep",
    "DecodeStep",
    "DiscoverStep",
    "ExtractExifStep",
    "FingerprintStep",
    "LoadFailuresStep",
    "NextChunkStep",
    "PerceptualHashStep",
    "PersistStep",
    "SelectBatchStep",
    "SkipCopiesStep",
    "SkipKnownStep",
    "SyncCopyLogStep",
    "SyncFailureLogStep",
    "TallyChunkStep",
]
