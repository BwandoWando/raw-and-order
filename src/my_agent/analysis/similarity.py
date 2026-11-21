"""Name how alike two photos are from the distance between their dHashes.

The distance counts differing bits of two 64-bit dHashes (0-64). The
catalogue only lists matches within 10 bits, so the buckets cover 0-10:

- Identical: 0 (the same picture, maybe resized or recompressed)
- Very similar: 1-5 (the same shot, lightly edited or a burst neighbour)
- Similar: 6 or more (same scene, small changes in framing or light)
"""

from enum import StrEnum

IDENTICAL_MAX_DISTANCE = 0
VERY_SIMILAR_MAX_DISTANCE = 5


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
