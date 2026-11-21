"""Pop-up with everything known about one photo."""

from pathlib import Path

import pandas as pd
import streamlit as st

from my_agent.schemas import ExifData, PhotoRecord
from my_agent.ui.formatting import camera_settings, capture_label, date_source_label
from my_agent.ui.library import PhotoLibrary

DUPLICATE_COLUMNS = 4


@st.dialog("Photo details", width="large")
def show_details(path: Path, library: PhotoLibrary) -> None:
    """Render the details of the photo at ``path``."""
    record = library.photo(path)
    if record is None:
        st.warning("This photo is no longer in the database.")
        return
    left, right = st.columns([3, 2])
    with left:
        _image(record.preview_path)
        st.caption(str(record.path))
    with right:
        st.markdown(f"**{record.annotation.description}**")
        st.markdown(
            " ".join(f"`{tag}`" for tag in record.annotation.tags) or "_No tags_"
        )
        people = "Yes" if record.annotation.contains_people else "No"
        st.markdown(
            f"Scene: **{record.annotation.scene.value}** · People: **{people}**"
        )
        source = date_source_label(record.exif.date_source)
        st.markdown(f"Taken: **{capture_label(record)}** (from {source})")
        st.caption(f"Annotated by {record.annotated_by}")
    _exif_table(record.exif)
    _location(record)
    _fingerprints(record.sha256, record.dhash)
    _copies(library.copies_of(path))
    _near_duplicates(path, library)


def _image(preview_path: Path) -> None:
    if preview_path.is_file():
        st.image(str(preview_path), width="stretch")
    else:
        st.info("Preview file not found.")


def _exif_table(exif: ExifData) -> None:
    rows = camera_settings(exif)
    if rows:
        st.subheader("Camera", divider="gray")
        st.table(pd.DataFrame(rows, columns=["", "Value"]).set_index(""))


def _location(record: PhotoRecord) -> None:
    if record.exif.gps is None:
        return
    gps = record.exif.gps
    st.subheader("Location", divider="gray")
    st.caption(f"{gps.latitude:.5f}, {gps.longitude:.5f}")
    st.map(pd.DataFrame({"lat": [gps.latitude], "lon": [gps.longitude]}), zoom=11)


def _fingerprints(sha256: str | None, dhash: str | None) -> None:
    st.subheader("Fingerprints", divider="gray")
    st.code(f"SHA-256  {sha256 or '-'}\ndHash    {dhash or '-'}", language=None)


def _copies(paths: list[Path]) -> None:
    if not paths:
        return
    st.subheader("Also stored at", divider="gray")
    st.caption("Exact copies (same SHA-256); not annotated again.")
    st.code("\n".join(str(p) for p in paths), language=None)


def _near_duplicates(path: Path, library: PhotoLibrary) -> None:
    matches = library.near_duplicates(path)
    st.subheader("Similar photos", divider="gray")
    if not matches:
        st.caption("No similar photos (dHash distance ≤ 10).")
        return
    columns = st.columns(DUPLICATE_COLUMNS)
    for index, match in enumerate(matches[: DUPLICATE_COLUMNS * 2]):
        with columns[index % DUPLICATE_COLUMNS]:
            if match.record.preview_path.is_file():
                st.image(str(match.record.preview_path), width="stretch")
            label = "identical" if match.distance == 0 else f"distance {match.distance}"
            st.caption(f"{match.record.path.name} · {label}")
