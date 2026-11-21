"""Naming how alike two photos are from their dHash distance."""

import pytest

from my_agent.analysis.similarity import Similarity, similarity


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0, Similarity.IDENTICAL),
        (1, Similarity.VERY_SIMILAR),
        (7, Similarity.VERY_SIMILAR),
        (8, Similarity.SIMILAR),
        (14, Similarity.SIMILAR),
    ],
)
def test_distance_buckets(distance: int, expected: Similarity) -> None:
    assert similarity(distance) == expected
