"""Random example photos per tag, for the Tags tab's previews."""

from pathlib import Path

from raw_and_order.analysis.tag_samples import one_per_tag, sample_by_tag

PHOTOS = [
    (Path(f"/p/{i}.jpg"), ["sea", "sky"] if i % 2 else ["city", "sky"])
    for i in range(20)
]


def test_samples_only_photos_with_the_tag_up_to_the_limit() -> None:
    samples = sample_by_tag(PHOTOS, ["sea", "sky"], per_tag=9, seed=1)

    sea = {path for path, tags in PHOTOS if "sea" in tags}
    assert len(samples["sea"]) == 9
    assert set(samples["sea"]) <= sea
    assert len(set(samples["sky"])) == 9  # no photo twice


def test_a_rare_or_unknown_tag_gets_what_there_is() -> None:
    photos = [*PHOTOS, (Path("/p/rare.jpg"), ["rare"])]

    samples = sample_by_tag(photos, ["rare", "nowhere"], per_tag=9, seed=1)

    assert samples == {"rare": [Path("/p/rare.jpg")], "nowhere": []}


def test_the_same_seed_gives_the_same_photos() -> None:
    first = sample_by_tag(PHOTOS, ["sky"], per_tag=5, seed=42)

    assert sample_by_tag(PHOTOS, ["sky"], per_tag=5, seed=42) == first
    assert sample_by_tag(PHOTOS, ["sky"], per_tag=5, seed=43) != first


def test_a_tag_repeated_on_one_photo_counts_once() -> None:
    samples = sample_by_tag([(Path("/p/a.jpg"), ["sea", "sea"])], ["sea"], 9, 1)

    assert samples["sea"] == [Path("/p/a.jpg")]


def test_one_per_tag_prefers_a_different_photo_for_each_tag() -> None:
    shared, other = Path("/p/shared.jpg"), Path("/p/other.jpg")
    samples = {"urban": [shared], "grey": [shared, other]}

    assert one_per_tag(samples, ["urban", "grey"]) == [
        ("urban", shared),
        ("grey", other),
    ]


def test_one_per_tag_reuses_a_photo_rather_than_drop_a_tag() -> None:
    shared = Path("/p/shared.jpg")
    samples = {"urban": [shared], "grey": [shared], "empty": []}

    assert one_per_tag(samples, ["urban", "grey", "empty", "unknown"]) == [
        ("urban", shared),
        ("grey", shared),
    ]
