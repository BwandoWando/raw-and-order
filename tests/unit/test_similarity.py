"""Naming how alike two photos are, and the shared-tags rule."""

import pytest

from raw_and_order.analysis.similarity import (
    Similarity,
    shares_tags,
    similarity,
    tag_overlap,
)


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, Similarity.IDENTICAL),
        (2, Similarity.IDENTICAL),
        (3, Similarity.VERY_SIMILAR),
        (8, Similarity.VERY_SIMILAR),
        (9, Similarity.SIMILAR),
        (14, Similarity.SIMILAR),
    ],
)
def test_distance_buckets(distance: int, expected: Similarity) -> None:
    assert similarity(distance) == expected


def test_overlap_is_measured_against_the_larger_tag_set() -> None:
    assert tag_overlap(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert tag_overlap(["a", "b", "c", "d", "e"], ["a", "b", "c"]) == 0.6
    assert tag_overlap(["Sky", " sea"], ["sky", "sea"]) == 1.0  # case, spaces


def test_photos_without_tags_overlap_with_nothing() -> None:
    assert tag_overlap([], ["a"]) == 0.0
    assert tag_overlap([], []) == 0.0


def test_similar_needs_a_quarter_of_shared_tags() -> None:
    eight = ["a", "b", "c", "d", "e", "f", "g", "h"]

    assert shares_tags(eight, ["a", "b", "w", "x", "y", "z"])  # 2 of 8 = 25%
    assert not shares_tags(eight, ["a", "w", "x", "y", "z"])  # 1 of 8
