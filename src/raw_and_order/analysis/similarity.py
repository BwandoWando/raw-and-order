"""Decide whether two photos are similar, and name how alike they look.

Two photos are similar only if both hold:

1. Their pHashes (64-bit) differ in at most
   :data:`SIMILAR_MAX_DISTANCE` (14) bits.
2. They share at least :data:`MIN_TAG_OVERLAP` (25%) of each photo's tags.

The pHash describes the overall structure of light and dark, so on its own
it can also match unrelated photos with a similar layout; the tags confirm
the content. Model tags vary from run to run, so the tag bar is low.

Calibrated on a real catalogue of 6,871 photos: these limits found 63% of
burst neighbours (shots seconds apart) with about 0.035 chance matches per
photo. With 60% shared tags only 29% of burst neighbours were found.

How alike similar photos look comes from the pHash distance:

- Identical: 0-2 (the same picture, maybe resized or recompressed)
- Very similar: 3-8 (the same shot, lightly edited or a burst neighbour)
- Similar: 9 or more (same scene, small changes in framing or light)
"""

from collections.abc import Iterable
from enum import StrEnum

IDENTICAL_MAX_DISTANCE = 2
VERY_SIMILAR_MAX_DISTANCE = 8
SIMILAR_MAX_DISTANCE = 14  # of 64 pHash bits; beyond this photos are not similar
MIN_TAG_OVERLAP = 0.25


class Similarity(StrEnum):
    """How alike two photos look, closest first."""

    IDENTICAL = "Identical"
    VERY_SIMILAR = "Very similar"
    SIMILAR = "Similar"


def similarity(distance: int) -> Similarity:
    """Bucket a pHash distance (number of differing bits)."""
    if distance <= IDENTICAL_MAX_DISTANCE:
        return Similarity.IDENTICAL
    if distance <= VERY_SIMILAR_MAX_DISTANCE:
        return Similarity.VERY_SIMILAR
    return Similarity.SIMILAR


def tag_overlap(first: Iterable[str], second: Iterable[str]) -> float:
    """Share of each photo's tags that both have (the lower of the two).

    Tags are compared case-insensitively. 1.0 means the same tag set; a
    photo without tags overlaps with nothing.
    """
    a = {tag.strip().lower() for tag in first}
    b = {tag.strip().lower() for tag in second}
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def shares_tags(first: Iterable[str], second: Iterable[str]) -> bool:
    """True if the photos share at least :data:`MIN_TAG_OVERLAP` of their tags."""
    return tag_overlap(first, second) >= MIN_TAG_OVERLAP
