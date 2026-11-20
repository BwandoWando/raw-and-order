from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from my_agent.db.catalog import SqlAlchemyPhotoCatalog, escape_like
from my_agent.db.repository import SqlAlchemyPhotoRepository
from my_agent.schemas import Annotation, ExifData, GpsCoordinate, PhotoRecord, SceneType
from my_agent.schemas.query import PhotoQuery, SortOrder


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
    dhash: str | None = "0000000000000000",
    processed_day: int = 1,
) -> PhotoRecord:
    return PhotoRecord(
        path=Path(f"/photos/{name}"),
        sha256=name,
        dhash=dhash,
        exif=ExifData(
            model=camera,
            lens_model=lens,
            captured_at=captured,
            gps=GpsCoordinate(latitude=14.6, longitude=121.0) if gps else None,
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
            dhash="000000000000000f",
        ),
        _photo(
            "street.arw",
            scene=SceneType.STREET,
            tags=("city", "sunset-ish"),
            people=True,
            captured=datetime(2026, 1, 11, 9, 0),
            processed_day=3,
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
            dhash="ffffffffffffffff",
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
    assert (options.earliest, options.latest) == (date(2025, 12, 31), date(2026, 2, 21))


def test_near_duplicates_closest_first(catalog: SqlAlchemyPhotoCatalog) -> None:
    street = catalog.get(Path("/photos/street.arw"))
    assert street is not None

    matches = catalog.near_duplicates(street)

    assert [(m.record.path.name, m.distance) for m in matches] == [
        ("odd_100%.arw", 0),
        ("beach.arw", 4),
    ]  # portrait.jpg is 64 bits away


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
