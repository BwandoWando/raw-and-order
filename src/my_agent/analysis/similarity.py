"""Name how alike two photos are from the distance between their dHashes.

The distance counts differing bits of two 256-bit dHashes (0-256). The
catalogue only lists matches within 64 bits, so the buckets cover 0-64:

- Identical: 0-12 (the same picture, maybe resized or recompressed)
- Very similar: 13-32 (the same shot, lightly edited or a burst neighbour)
- Similar: 33 or more (same scene, small changes in framing or light)

Calibrated on a real catalogue of 6,371 photos: a limit of 64 found 64% of
burst neighbours (shots seconds apart) with about 0.16 chance matches per
photo; 72 found 68% but six times the chance matches.
"""

from enum import StrEnum

IDENTICAL_MAX_DISTANCE = 12
VERY_SIMILAR_MAX_DISTANCE = 32


class Similarity(StrEnum):
    """How alike two photos look, closest first."""

    IDENTICAL = "Identical"
    VERY_SIMILAR = "Very similar"
    SIMILAR = "Similar"


def similarity(distance: int) -> Similarity:
    """Bucket a dHash distance (number of differing bits)."""
    if distance <= IDENTICAL_MAX_DISTANCE:
        return Similarity.IDENTICAL
    if distance <= VERY_SIMILAR_MAX_DISTANCE:
        return Similarity.VERY_SIMILAR
    return Similarity.SIMILAR
