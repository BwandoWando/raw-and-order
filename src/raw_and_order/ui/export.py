"""Export tab: download the filtered photos' data as Excel, CSV or JSON."""

from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from raw_and_order.export import ExportFormat, encode, photo_row
from raw_and_order.export.formats import MIME_TYPES, text_value
from raw_and_order.schemas.query import PhotoQuery
from raw_and_order.ui.gallery import chosen_sort
from raw_and_order.ui.library import PhotoLibrary

FORMAT_LABELS = {
    ExportFormat.EXCEL: "Excel (.xlsx)",
    ExportFormat.CSV: "CSV",
    ExportFormat.JSON: "JSON",
}
PREVIEW_ROWS = 10


def render_export(filters: PhotoQuery, library: PhotoLibrary) -> None:
    """Show how many photos match, a preview, and the download button.

    Only a small preview is read here (every tab runs on each rerun); the
    full export is read and written when the button is clicked.
    """
    query = filters.model_copy(update={"sort": chosen_sort(filters.sort)})
    preview = library.search(
        query.model_copy(update={"page": 1, "page_size": PREVIEW_ROWS})
    )
    if preview.total == 0:
        st.info("No photos match these filters.")
        return
    st.markdown(_summary(preview.total, filtered=filters.has_filters()))
    fmt = st.segmented_control(
        "Format",
        list(FORMAT_LABELS),
        format_func=FORMAT_LABELS.__getitem__,
        default=ExportFormat.EXCEL,
        required=True,
        key="x_format",
    )
    fmt = fmt or ExportFormat.EXCEL
    st.download_button(
        f"Download {preview.total:,} photos",
        data=partial(_file, query, library, fmt),
        file_name=f"photos-{date.today().isoformat()}.{fmt.value}",
        mime=MIME_TYPES[fmt],
        icon=":material/download:",
        type="primary",
        on_click="ignore",
        key="x_download",
    )
    st.caption(f"First {len(preview.items)} rows, one per photo:")
    rows = [photo_row(record) for record in preview.items]
    table = pd.DataFrame([{k: text_value(v) for k, v in row.items()} for row in rows])
    st.dataframe(table, hide_index=True, alt="Preview of the exported rows")


def _file(query: PhotoQuery, library: PhotoLibrary, fmt: ExportFormat) -> bytes:
    """Read every matching photo and write the file (runs on click)."""
    return encode([photo_row(r) for r in library.export_records(query)], fmt)


def _summary(total: int, filtered: bool) -> str:
    if filtered:
        return f"**{total:,} photos** match the current filters."
    return f"**All {total:,} photos** (no filters set; narrow them in the sidebar)."
