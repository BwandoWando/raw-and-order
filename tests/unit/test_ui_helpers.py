import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from my_agent.schemas import (
    Annotation,
    DateSource,
    ExifData,
    PhotoRecord,
    SceneType,
    WhiteBalanceSource,
)
from my_agent.schemas.query import CountRow
from my_agent.ui.charts import DARK, LIGHT, columns_by_month, horizontal_bars, theme_for
from my_agent.ui.filters import tag_label
from my_agent.ui.formatting import (
    camera_settings,
    card_caption,
    date_source_label,
    escape_markdown,
    format_exposure,
    format_white_balance,
)
from my_agent.ui.launcher import APP_PATH, THEME_PATH, streamlit_command


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.004, "1/250 s"),
        (1 / 8000, "1/8000 s"),
        (0.5, "1/2 s"),
        (2.0, "2 s"),
        (0.3, "0.3 s"),
        (None, None),
        (0, None),
    ],
)
def test_format_exposure(seconds: float | None, expected: str | None) -> None:
    assert format_exposure(seconds) == expected


def test_camera_settings_skips_missing_values() -> None:
    exif = ExifData(
        make="SONY", model="ILCE-6400", f_number=1.8, exposure_time_s=0.004, iso=100
    )

    assert camera_settings(exif) == [
        ("Camera", "SONY ILCE-6400"),
        ("Aperture", "f/1.8"),
        ("Shutter", "1/250 s"),
        ("ISO", "100"),
    ]


def test_card_caption() -> None:
    record = PhotoRecord(
        path=Path("/p/a.arw"),
        exif=ExifData(captured_at=None),
        annotation=Annotation(
            description="x", scene=SceneType.STREET, contains_people=False
        ),
        preview_path=Path("/p/a.jpg"),
        annotated_by="m",
        processed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert card_caption(record) == "Unknown date · street"


def test_streamlit_command_binds_localhost_without_telemetry() -> None:
    command = streamlit_command(port=8600, open_browser=False)

    assert command[1:5] == ["-m", "streamlit", "run", str(APP_PATH)]
    flags = dict(zip(command[5::2], command[6::2], strict=True))
    assert flags == {
        "--server.address": "localhost",
        "--server.port": "8600",
        "--browser.gatherUsageStats": "false",
        "--client.toolbarMode": "viewer",
        "--theme.base": str(THEME_PATH),
        "--server.headless": "true",
    }


def test_chart_theme_follows_streamlit_theme() -> None:
    assert theme_for("dark") is DARK
    assert theme_for("light") is LIGHT
    assert theme_for(None) is LIGHT


def test_charts_use_theme_bar_color_and_capped_thickness() -> None:
    rows = [CountRow(label="landscape", count=3), CountRow(label="street", count=1)]

    for chart in (horizontal_bars(rows, DARK), columns_by_month(rows, DARK)):
        spec = chart.to_dict()
        bar = spec["layer"][0]["mark"]
        assert (bar["color"], bar["size"], bar["cornerRadiusEnd"]) == ("#3987e5", 18, 4)
        assert "legend" not in str(spec["layer"][0].get("encoding", {}))


def test_date_source_label() -> None:
    assert date_source_label(DateSource.EXIF_ORIGINAL) == "EXIF DateTimeOriginal"
    assert date_source_label(DateSource.FILENAME) == "file name"
    assert date_source_label(None) == "unknown"


def test_horizontal_bars_leave_room_for_every_row() -> None:
    rows = [CountRow(label=f"lens {i}", count=i + 1) for i in range(3)]

    spec = horizontal_bars(rows, LIGHT).to_dict()

    assert spec["height"] == 3 * 28 + 40
    assert spec["layer"][0]["encoding"]["y"]["scale"]["paddingInner"] == 0.3


@pytest.mark.parametrize(
    ("exif", "expected"),
    [
        (
            ExifData(
                white_balance="Auto",
                white_balance_k=5400,
                white_balance_k_source=WhiteBalanceSource.ESTIMATED,
            ),
            "Auto · ≈ 5,400 K (estimated)",
        ),
        (
            ExifData(
                white_balance="Color Temperature/Color Filter",
                white_balance_k=3200,
                white_balance_k_source=WhiteBalanceSource.CAMERA,
            ),
            "Color Temperature/Color Filter · 3,200 K (recorded by camera)",
        ),
        (ExifData(white_balance="Auto"), "Auto"),
        (ExifData(), None),
    ],
)
def test_format_white_balance(exif: ExifData, expected: str | None) -> None:
    assert format_white_balance(exif) == expected


def test_escape_markdown_keeps_file_names_literal() -> None:
    assert escape_markdown("IMG_0001 [v2].jpg") == r"IMG\_0001 \[v2\]\.jpg"
    assert escape_markdown("/a:b*c") == r"/a\:b\*c"


def test_theme_file_defines_light_and_dark() -> None:
    theme = tomllib.loads(THEME_PATH.read_text())["theme"]

    assert {"light", "dark"} <= theme.keys()  # both -> the switch is shown
    assert (theme["paddingTop"], theme["paddingBottom"]) == ("0rem", "1rem")


def test_tag_label_adds_the_photo_count() -> None:
    counts = {"urban": 1204, "people": 344}

    assert tag_label("urban", counts) == "urban (1,204)"
    assert tag_label("people", counts) == "people (344)"
    assert tag_label("rare", counts) == "rare"  # not counted
