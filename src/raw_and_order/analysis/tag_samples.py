"""Pick random example photos for tags, as previews on the Tags tab.

Pure functions; the caller fetches each photo's preview path and tags. The
picks are seeded, so one seed always gives the same photos (the UI keeps a
seed per browser session, so its previews hold still between reruns).
"""

import random
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

TaggedPreview = tuple[Path, Sequence[str]]  # a photo's preview and its tags


def sample_by_tag(
    photos: Iterable[TaggedPreview], tags: Iterable[str], per_tag: int, seed: int
) -> dict[str, list[Path]]:
    """Up to ``per_tag`` random previews of photos carrying each of ``tags``.

    Tags no photo carries map to an empty list. The result depends only on
    the inputs, so pass ``photos`` in a fixed order (e.g. by path).
    """
    wanted = list(dict.fromkeys(tags))  # drop repeats, keep the order
    by_tag: dict[str, list[Path]] = {tag: [] for tag in wanted}
    for preview, photo_tags in photos:
        for tag in set(photo_tags):
            if tag in by_tag:
                by_tag[tag].append(preview)
    rng = random.Random(seed)  # not for security, only for variety
    return {
        tag: rng.sample(by_tag[tag], min(per_tag, len(by_tag[tag]))) for tag in wanted
    }


def one_per_tag(
    samples: Mapping[str, Sequence[Path]], tags: Iterable[str]
) -> list[tuple[str, Path]]:
    """One preview for each of ``tags``, a different photo for each if possible.

    Each tag takes its first sample not already taken by an earlier tag, so a
    photo carrying all the tags is not shown three times. A tag whose samples
    are all taken reuses its first; a tag with no samples is left out.
    """
    taken: set[Path] = set()
    picks: list[tuple[str, Path]] = []
    for tag in tags:
        options = samples.get(tag, ())
        if not options:
            continue
        preview = next((p for p in options if p not in taken), options[0])
        taken.add(preview)
        picks.append((tag, preview))
    return picks
