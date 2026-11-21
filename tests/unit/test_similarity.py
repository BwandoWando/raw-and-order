"""Naming how alike two photos are from their dHash distance."""

import pytest

from my_agent.analysis.similarity import Similarity, similarity


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, Similarity.IDENTICAL),
        (12, Similarity.IDENTICAL),
        (13, Similarity.VERY_SIMILAR),
        (32, Similarity.VERY_SIMILAR),
        (33, Similarity.SIMILAR),
        (64, Similarity.SIMILAR),
    ],
)
def test_distance_buckets(distance: int, expected: Similarity) -> None:
    assert similarity(distance) == expected
