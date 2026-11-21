"""Export rows and the CSV, JSON and Excel files built from them."""

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import load_workbook

from my_agent.export import COLUMNS, ExportFormat, encode, photo_row
from my_agent.schemas import ExifData, GpsCoordinate, PhotoRecord
from tests.fakes import SAMPLE_ANNOTATION

TAKEN = datetime(2026, 5, 3, 14, 29)
PROCESSED = datetime(2026, 11, 21, 9, 0, tzinfo=UTC)


def _record(gps: bool = True) -> PhotoRecord:
    return PhotoRecord(
        path=Path("/photos/trip/DSC01234.ARW"),
        sha256="ab" * 32,
        phash="0" * 16,
        exif=ExifData(
            make="SONY",
            model="ILCE-6400",
            iso=200,
            f_number=5.6,
            captured_at=TAKEN,
            gps=GpsCoordinate(latitude=14.6, longitude=121.0) if gps else None,
        ),
        annotation=SAMPLE_ANNOTATION.model_copy(update={"tags": ["sea", "pier"]}),
        preview_path=Path("/previews/DSC01234.jpg"),
        annotated_by="ollama:gemma3:12b",
        processed_at=PROCESSED,
    )


def test_row_has_every_column_in_order() -> None:
    row = photo_row(_record())

    assert tuple(row) == COLUMNS
    assert (row["file_name"], row["folder"]) == ("DSC01234.ARW", "/photos/trip")
    assert (row["camera_model"], row["iso"], row["aperture_f"]) == (
        "ILCE-6400",
        200,
        5.6,
    )
    assert (row["latitude"], row["longitude"]) == (14.6, 121.0)
    assert row["tags"] == ["sea", "pier"]


def test_missing_values_are_none() -> None:
    row = photo_row(_record(gps=False))

    assert (row["latitude"], row["altitude_m"], row["lens"]) == (None, None, None)


def test_csv_joins_tags_and_writes_iso_dates() -> None:
    data = encode([photo_row(_record())], ExportFormat.CSV)

    assert data.startswith(b"\xef\xbb\xbf")  # BOM, so Excel reads accents
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows[0]["tags"] == "sea; pier"
    assert rows[0]["taken_at"] == "2026-05-03 14:29:00"
    assert rows[0]["lens"] == ""


def test_json_keeps_tags_as_a_list() -> None:
    data = json.loads(encode([photo_row(_record())], ExportFormat.JSON))

    assert data[0]["tags"] == ["sea", "pier"]
    assert data[0]["taken_at"] == "2026-05-03T14:29:00"
    assert data[0]["lens"] is None


def test_excel_has_a_frozen_header_and_real_values() -> None:
    data = encode([photo_row(_record()), photo_row(_record(False))], ExportFormat.EXCEL)

    sheet = load_workbook(io.BytesIO(data)).active
    assert sheet is not None
    header = [cell.value for cell in sheet[1]]
    assert tuple(header) == COLUMNS
    assert sheet.freeze_panes == "A2"
    assert sheet.max_row == 3  # header + 2 photos
    values = dict(zip(header, (cell.value for cell in sheet[2]), strict=True))
    assert values["taken_at"] == TAKEN  # a real date
    assert values["processed_at_utc"] == PROCESSED.replace(tzinfo=None)
    assert values["iso"] == 200 and values["tags"] == "sea; pier"
