"""Name how alike two photos are from the distance between their dHashes.

The distance counts differing bits of two 81-bit (9x9) dHashes (0-81). The
catalogue only lists matches within 14 bits, so the buckets cover 0-14:

- Identical: 0 (the same picture, maybe resized or recompressed)
- Very similar: 1-7 (the same shot, lightly edited or a burst neighbour)
- Similar: 8 or more (same scene, small changes in framing or light)

Calibrated on a real catalogue of 6,371 photos: a limit of 14 found 58% of
burst neighbours (shots seconds apart) with about 0.14 chance matches per
photo; the 64-bit dHash at 10 found 57% with 0.48. At 16 chance matches
rose to 0.69.
"""

from enum import StrEnum

IDENTICAL_MAX_DISTANCE = 0
VERY_SIMILAR_MAX_DISTANCE = 7


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
