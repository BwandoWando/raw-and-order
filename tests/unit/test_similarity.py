"""Naming how alike two photos are from their dHash distance."""

import pytest

from my_agent.analysis.similarity import Similarity, similarity


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, Similarity.IDENTICAL),
        (1, Similarity.VERY_SIMILAR),
        (5, Similarity.VERY_SIMILAR),
        (6, Similarity.SIMILAR),
        (10, Similarity.SIMILAR),
    ],
)
def test_distance_buckets(distance: int, expected: Similarity) -> None:
    assert similarity(distance) == expected
