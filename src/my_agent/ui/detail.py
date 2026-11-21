"""Pop-up with everything known about one photo, sized to fit one screen.

The photo comes first, then its description and camera settings. The longer
sections (similar photos, location, files) sit in tabs below, so nothing
needs scrolling on a normal screen.
"""

from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from my_agent.schemas import ExifData, PhotoRecord
from my_agent.ui.formatting import camera_settings, capture_label, date_source_label
from my_agent.ui.library import PhotoLibrary

DUPLICATE_COLUMNS = 6
TAB_HEIGHT_PX = 130  # fits a row of similar photos with captions
PHOTO_KEY = "detail-photo"
SIMILAR_KEY = "detail-similar"
# Room left for the dialog title, summary, camera row and tabs.
CHROME_REM = 39

DETAIL_CSS = f"""
<style>
.st-key-{PHOTO_KEY} img {{
    max-height: calc(100vh - {CHROME_REM}rem);
    min-height: 9rem;
    width: auto !important;
    max-width: 100%;
    object-fit: contain;
    border-radius: 0.375rem;
}}
.st-key-{SIMILAR_KEY} img {{
    height: 4.5rem;
    object-fit: cover;
    border-radius: 0.25rem;
}}
</style>
"""


@st.dialog("Photo details", width="large")
def show_details(path: Path, library: PhotoLibrary) -> None:
    """Render the details of the photo at ``path``."""
    record = library.photo(path)
    if record is None:
        st.warning("This photo is no longer in the database.")
        return
    st.html(DETAIL_CSS)
    with st.container(key=PHOTO_KEY, horizontal_alignment="center"):
        _image(record.preview_path)
    _summary(record)
    _camera(record.exif)
    _sections(record, library)


def _image(preview_path: Path) -> None:
    if preview_path.is_file():
        st.image(str(preview_path), width="content")
    else:
        st.info("Preview file not found.")


def _summary(record: PhotoRecord) -> None:
    annotation = record.annotation
    st.markdown(f"**{annotation.description}**")
    st.markdown(" ".join(f"`{tag}`" for tag in annotation.tags) or "_No tags_")
    people = "yes" if annotation.contains_people else "no"
    source = date_source_label(record.exif.date_source)
    st.caption(
        f"Scene: {annotation.scene.value} · People: {people} · "
        f"Taken {capture_label(record)} (from {source}) · "
        f"Annotated by {record.annotated_by}"
    )


def _camera(exif: ExifData) -> None:
    rows = camera_settings(exif)
    if not rows:
        return
    with st.container(horizontal=True, gap="small"):
        for label, value in rows:
            st.markdown(f":small[:gray[{label}] **{value}**]", width="content")


def _sections(record: PhotoRecord, library: PhotoLibrary) -> None:
    """Tabs of equal height, so switching tabs never resizes the dialog."""
    names = ["Similar photos", "Files"]
    if record.exif.gps is not None:
        names.insert(1, "Location")
    tabs = dict(zip(names, st.tabs(names), strict=True))
    with tabs["Similar photos"], _panel():
        _near_duplicates(record.path, library)
    if "Location" in tabs:
        with tabs["Location"], _panel():
            _location(record)
    with tabs["Files"], _panel():
        _files(record, library.copies_of(record.path))


def _panel() -> DeltaGenerator:
    """A fixed-height tab body; longer content scrolls inside it."""
    return st.container(height=TAB_HEIGHT_PX, border=False)


def _location(record: PhotoRecord) -> None:
    gps = record.exif.gps
    if gps is None:
        return
    map_column, text_column = st.columns([4, 1])
    with map_column:
        st.map(
            pd.DataFrame({"lat": [gps.latitude], "lon": [gps.longitude]}),
            zoom=11,
            height=TAB_HEIGHT_PX,
        )
    with text_column:
        st.caption(f"{gps.latitude:.5f}, {gps.longitude:.5f}")


def _files(record: PhotoRecord, copies: list[Path]) -> None:
    st.code(
        f"File     {record.path}\n"
        f"SHA-256  {record.sha256 or '-'}\n"
        f"dHash    {record.dhash or '-'}",
        language=None,
    )
    if copies:
        st.caption("Also stored at (exact copies, same SHA-256; not annotated again)")
        st.code("\n".join(str(p) for p in copies), language=None)


def _near_duplicates(path: Path, library: PhotoLibrary) -> None:
    matches = library.near_duplicates(path)[:DUPLICATE_COLUMNS]
    if not matches:
        st.caption("No similar photos (dHash distance ≤ 10).")
        return
    with st.container(key=SIMILAR_KEY):
        columns = st.columns(DUPLICATE_COLUMNS, gap="small")
        for column, match in zip(columns, matches, strict=False):
            with column:
                if match.record.preview_path.is_file():
                    st.image(str(match.record.preview_path), width="stretch")
                label = (
                    "identical" if match.distance == 0 else f"distance {match.distance}"
                )
                st.caption(f"{match.record.path.name} · {label}")
