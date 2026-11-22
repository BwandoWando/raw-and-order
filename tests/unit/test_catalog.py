from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raw_and_order.db.catalog import SqlAlchemyPhotoCatalog, escape_like
from raw_and_order.db.copy_repository import SqlAlchemyCopyRepository
from raw_and_order.db.favorite_repository import SqlAlchemyFavoriteRepository
from raw_and_order.db.repository import SqlAlchemyPhotoRepository
from raw_and_order.schemas import (
    Annotation,
    ExifData,
    GpsCoordinate,
    PhotoCopy,
    PhotoRecord,
    SceneType,
)
from raw_and_order.schemas.query import PhotoQuery, SortOrder


def _photo(
    name: str,
    *,
    scene: SceneType = SceneType.LANDSCAPE,
    tags: tuple[str, ...] = ("sky",),
    description: str = "A photo.",
    people: bool = False,
    camera: str | None = "ILCE-6400",
    lens: str | None = "Sigma 17-40mm F1.8 DC | A",
    captured: datetime | None = datetime(2026, 1, 11, 14, 0),
    gps: bool = False,
    model: str = "ollama:gemma3:12b",
    phash: str | None = "0" * 16,
    processed_day: int = 1,
    kelvin: int | None = None,
) -> PhotoRecord:
    return PhotoRecord(
        path=Path(f"/photos/{name}"),
        sha256=name,
        phash=phash,
        exif=ExifData(
            model=camera,
            lens_model=lens,
            captured_at=captured,
            gps=GpsCoordinate(latitude=14.6, longitude=121.0) if gps else None,
            white_balance_k=kelvin,
        ),
        annotation=Annotation(
            description=description,
            tags=list(tags),
            scene=scene,
            contains_people=people,
        ),
        preview_path=Path(f"/previews/{name}.jpg"),
        annotated_by=model,
        processed_at=datetime(2026, 11, processed_day, tzinfo=UTC),
    )


@pytest.fixture
def catalog(
    session_factory: sessionmaker[Session], repository: SqlAlchemyPhotoRepository
) -> SqlAlchemyPhotoCatalog:
    photos = [
        _photo(
            "beach.arw",
            tags=("sunset", "beach", "sky"),
            description="Sunset over the sea.",
            captured=datetime(2026, 2, 21, 18, 0),
            gps=True,
            phash="0" * 15 + "f",
            kelvin=5400,
        ),
        _photo(
            "street.arw",
            scene=SceneType.STREET,
            tags=("city", "sunset-ish"),
            people=True,
            captured=datetime(2026, 1, 11, 9, 0),
            processed_day=3,
            kelvin=3150,
        ),
        _photo(
            "portrait.jpg",
            scene=SceneType.PORTRAIT,
            tags=("person",),
            people=True,
            camera="Pixel 8",
            lens=None,
            captured=None,
            model="openai:x",
            phash="f" * 16,
            processed_day=2,
        ),
        _photo(
            "odd_100%.arw",
            description="Contains 100% literal",
            captured=datetime(2025, 12, 31),
        ),
    ]
    for photo in photos:
        repository.upsert(photo)
    return SqlAlchemyPhotoCatalog(session_factory)


def _names(catalog: SqlAlchemyPhotoCatalog, **filters: object) -> list[str]:
    page = catalog.search(PhotoQuery(**filters))
    return [record.path.name for record in page.items]


def test_no_filters_returns_all_newest_capture_first_undated_last(
    catalog: SqlAlchemyPhotoCatalog,
) -> None:
    assert _names(catalog) == [
        "beach.arw",
        "street.arw",
        "odd_100%.arw",
        "portrait.jpg",
    ]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"text": "sunset"}, ["beach.arw", "street.arw"]),  # description or tags
        ({"text": "SEA"}, ["beach.arw"]),  # case-insensitive
        ({"text": "100%"}, ["odd_100%.arw"]),  # % is literal, not a wildcard
        ({"tags": ("sunset",)}, ["beach.arw"]),  # exact tag, not "sunset-ish"
        ({"tags": ("sunset", "beach")}, ["beach.arw"]),
        ({"tags": ("sunset", "city")}, []),  # must have all
        ({"scenes": ("street", "portrait")}, ["street.arw", "portrait.jpg"]),
        ({"contains_people": True}, ["street.arw", "portrait.jpg"]),
        ({"contains_people": False}, ["beach.arw", "odd_100%.arw"]),
        ({"cameras": ("Pixel 8",)}, ["portrait.jpg"]),
        (
            {"lenses": ("Sigma 17-40mm F1.8 DC | A",)},
            ["beach.arw", "street.arw", "odd_100%.arw"],
        ),
        ({"date_from": date(2026, 1, 1), "date_to": date(2026, 1, 31)}, ["street.arw"]),
        ({"date_to": date(2025, 12, 31)}, ["odd_100%.arw"]),  # end date is inclusive
        ({"only_with_gps": True}, ["beach.arw"]),
        ({"annotated_by": ("openai:x",)}, ["portrait.jpg"]),
    ],
)
def test_filters(
    catalog: SqlAlchemyPhotoCatalog, filters: dict[str, object], expected: list[str]
) -> None:
    assert _names(catalog, **filters) == expected


def test_sort_orders(catalog: SqlAlchemyPhotoCatalog) -> None:
    assert _names(catalog, sort=SortOrder.CAPTURED_OLDEST) == [
        "odd_100%.arw",
        "street.arw",
        "beach.arw",
        "portrait.jpg",
    ]
    assert _names(catalog, sort=SortOrder.PROCESSED_NEWEST)[0] == "street.arw"


def test_pagination(catalog: SqlAlchemyPhotoCatalog) -> None:
    first = catalog.search(PhotoQuery(page_size=3))
    second = catalog.search(PhotoQuery(page_size=3, page=2))

    assert (first.total, first.pages, len(first.items)) == (4, 2, 3)
    assert [r.path.name for r in second.items] == ["portrait.jpg"]


def test_filter_options(catalog: SqlAlchemyPhotoCatalog) -> None:
    options = catalog.filter_options()

    assert options.scenes == ["landscape", "portrait", "street"]
    assert options.cameras == ["ILCE-6400", "Pixel 8"]
    assert options.lenses == ["Sigma 17-40mm F1.8 DC | A"]
    assert options.tags[0] == "sky"  # most frequent first
    assert options.tag_counts["sky"] == 2
    assert options.tag_counts["sunset"] == 1
    assert (options.earliest, options.latest) == (date(2025, 12, 31), date(2026, 2, 21))


def test_tag_counts_count_each_photo_once(
    session_factory: sessionmaker[Session], repository: SqlAlchemyPhotoRepository
) -> None:
    repository.upsert(_photo("twice.arw", tags=("sea", "sea", "sky")))
    repository.upsert(_photo("once.arw", tags=("sea",)))

    counts = SqlAlchemyPhotoCatalog(session_factory).filter_options().tag_counts

    assert counts == {"sea": 2, "sky": 1}


def test_similar_photos_need_close_phash_and_shared_tags(
    session_factory: sessionmaker[Session], repository: SqlAlchemyPhotoRepository
) -> None:
    tags = ("sea", "sky", "boat", "pier", "sunset")
    photos = [
        _photo("target.arw", tags=tags),
        _photo("burst.arw", tags=tags, phash="0" * 15 + "f"),  # 4 bits, same tags
        _photo("copy.arw", tags=(*tags[:3], "dusk", "calm")),  # 0 bits, 60% tags
        _photo("lookalike.arw", tags=("city", "car", "road")),  # 0 bits, no tags
        _photo("far.arw", tags=tags, phash="f" * 16),  # same tags, 64 bits
    ]
    for photo in photos:
        repository.upsert(photo)
    catalog = SqlAlchemyPhotoCatalog(session_factory)
    target = catalog.get(Path("/photos/target.arw"))
    assert target is not None

    matches = catalog.similar_photos(target)

    assert [(m.record.path.name, m.distance) for m in matches] == [
        ("copy.arw", 0),
        ("burst.arw", 4),
    ]


def test_stats(catalog: SqlAlchemyPhotoCatalog) -> None:
    stats = catalog.stats()

    assert (stats.total, stats.with_gps, stats.with_people) == (4, 1, 2)
    assert stats.by_scene[0].label == "landscape"
    assert {r.label: r.count for r in stats.by_lens} == {
        "Sigma 17-40mm F1.8 DC | A": 3,
        "Unknown": 1,
    }
    assert [r.label for r in stats.by_month] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "Unknown",
    ]


def test_escape_like() -> None:
    assert escape_like("50%_off\\") == "50\\%\\_off\\\\"


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"kelvin_min": 5000}, ["beach.arw"]),
        ({"kelvin_max": 3150}, ["street.arw"]),  # bounds are inclusive
        ({"kelvin_min": 3000, "kelvin_max": 6000}, ["beach.arw", "street.arw"]),
    ],
)
def test_white_balance_filter(
    catalog: SqlAlchemyPhotoCatalog, filters: dict[str, object], expected: list[str]
) -> None:
    assert _names(catalog, **filters) == expected


def test_white_balance_options_and_buckets(catalog: SqlAlchemyPhotoCatalog) -> None:
    options = catalog.filter_options()
    stats = catalog.stats()

    assert (options.kelvin_min, options.kelvin_max) == (3150, 5400)
    assert [(r.label, r.count) for r in stats.by_white_balance] == [
        ("3000", 1),
        ("3500", 0),  # empty bands are kept so gaps are visible
        ("4000", 0),
        ("4500", 0),
        ("5000", 1),
    ]


def test_tag_lists_follow_the_filters(catalog: SqlAlchemyPhotoCatalog) -> None:
    everything = catalog.tag_lists(PhotoQuery())
    with_people = catalog.tag_lists(PhotoQuery(contains_people=True))

    assert ["sunset", "beach", "sky"] in everything
    assert len(everything) == len(_names(catalog))
    assert sorted(map(tuple, with_people)) == [("city", "sunset-ish"), ("person",)]


def test_copies_of_and_stats_count(
    catalog: SqlAlchemyPhotoCatalog, copies: SqlAlchemyCopyRepository
) -> None:
    original = Path("/photos/beach.arw")
    copies.record(
        [
            PhotoCopy(path=Path("/backup/beach.arw"), sha256="x", original=original),
            PhotoCopy(path=Path("/card/beach.arw"), sha256="x", original=original),
        ],
        datetime(2026, 11, 21, tzinfo=UTC),
    )

    assert catalog.copies_of(original) == [
        Path("/backup/beach.arw"),
        Path("/card/beach.arw"),
    ]
    assert catalog.copies_of(Path("/photos/street.arw")) == []
    assert catalog.stats().copies == 2


def test_matching_returns_every_filtered_photo_unpaged(
    catalog: SqlAlchemyPhotoCatalog,
) -> None:
    everything = catalog.matching(PhotoQuery(page_size=1))
    people = catalog.matching(PhotoQuery(contains_people=True))

    assert len(everything) == 4  # page_size does not limit it
    assert {r.path.name for r in people} == {"street.arw", "portrait.jpg"}


def test_favorites_only_filter(
    catalog: SqlAlchemyPhotoCatalog, session_factory: sessionmaker[Session]
) -> None:
    assert _names(catalog, only_favorites=True) == []
    favorites = SqlAlchemyFavoriteRepository(session_factory)
    for name in ("street.arw", "portrait.jpg"):
        favorites.set_favorite(
            Path("/photos") / name, True, when=datetime(2026, 11, 22, 9)
        )

    assert _names(catalog, only_favorites=True) == ["street.arw", "portrait.jpg"]
    assert _names(catalog, only_favorites=True, contains_people=False) == []
    assert sorted(catalog.tag_lists(PhotoQuery(only_favorites=True))) == [
        ["city", "sunset-ish"],
        ["person"],
    ]
