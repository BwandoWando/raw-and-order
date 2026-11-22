"""Write export rows as CSV, JSON or Excel bytes, in memory (pure, no I/O)."""

import csv
import io
import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from raw_and_order.export.rows import COLUMNS, Value

TAG_SEPARATOR = "; "
MAX_COLUMN_WIDTH = 60  # characters; long descriptions wrap past this
CSV_ENCODING = "utf-8-sig"  # the byte-order mark lets Excel read accents


class ExportFormat(StrEnum):
    """File formats an export can be written in."""

    EXCEL = "xlsx"
    CSV = "csv"
    JSON = "json"


MIME_TYPES = {
    ExportFormat.EXCEL: (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    ExportFormat.CSV: "text/csv",
    ExportFormat.JSON: "application/json",
}


def encode(rows: Sequence[dict[str, Value]], fmt: ExportFormat) -> bytes:
    """Return the file contents for ``rows`` in ``fmt``."""
    if fmt is ExportFormat.CSV:
        return to_csv(rows)
    if fmt is ExportFormat.JSON:
        return to_json(rows)
    return to_excel(rows)


def to_csv(rows: Iterable[dict[str, Value]]) -> bytes:
    """CSV with a header; tags joined by ``; ``, dates in ISO form."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(text_value(row[column]) for column in COLUMNS)
    return buffer.getvalue().encode(CSV_ENCODING)


def to_json(rows: Iterable[dict[str, Value]]) -> bytes:
    """A JSON list of objects; tags stay lists, dates are ISO strings."""
    data = [
        {k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()}
        for row in rows
    ]
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def to_excel(rows: Sequence[dict[str, Value]]) -> bytes:
    """One sheet: bold frozen header with filters, real dates and numbers."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Photos"
    sheet.append(list(COLUMNS))
    for row in rows:
        sheet.append([_excel_cell(row[column]) for column in COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    _fit_columns(sheet, rows)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def text_value(value: Value) -> str:
    """A cell as text: tags joined by ``; ``, dates in ISO form, ``None`` empty."""
    if value is None:
        return ""
    if isinstance(value, list):
        return TAG_SEPARATOR.join(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def _excel_cell(value: Value) -> object:
    if isinstance(value, list):
        return TAG_SEPARATOR.join(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)  # Excel has no time zones; UTC kept
    return value


def _fit_columns(sheet: Worksheet, rows: Sequence[dict[str, Value]]) -> None:
    """Width from the header and the first rows, capped for long text."""
    sample = rows[:200]
    for index, column in enumerate(COLUMNS, start=1):
        longest = max([len(column), *(len(text_value(r[column])) for r in sample)])
        width = min(longest + 2, MAX_COLUMN_WIDTH)
        sheet.column_dimensions[get_column_letter(index)].width = width
