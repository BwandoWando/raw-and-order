from pathlib import Path

from my_agent.media.routing import ExtensionRoutingDecoder
from tests.fakes import FakeImageDecoder


def test_routes_by_extension_case_insensitively() -> None:
    raw, image = FakeImageDecoder(), FakeImageDecoder()
    router = ExtensionRoutingDecoder(raw, image, {".nef", ".dng"})

    for name in ("a.NEF", "b.jpg", "c.dng", "d.png"):
        router.decode(Path(name))

    assert [p.name for p in raw.decoded] == ["a.NEF", "c.dng"]
    assert [p.name for p in image.decoded] == ["b.jpg", "d.png"]
