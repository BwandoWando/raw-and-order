"""Pure display helpers (no Streamlit), so they are easy to unit-test."""

import hashlib
from fractions import Fraction
from pathlib import Path

from raw_and_order.schemas import DateSource, ExifData, PhotoRecord, WhiteBalanceSource

DATE_SOURCE_LABELS = {
    DateSource.EXIF_ORIGINAL: "EXIF DateTimeOriginal",
    DateSource.XMP: "XMP date",
    DateSource.EXIF_CREATE: "EXIF CreateDate",
    DateSource.FILENAME: "file name",
    DateSource.NOT_FOUND: "no date found",
}


def format_exposure(seconds: float | None) -> str | None:
    """Return ``1/250 s`` for short exposures, ``2 s`` / ``0.5 s`` otherwise."""
    if seconds is None or seconds <= 0:
        return None
    if seconds < 1:
        fraction = Fraction(seconds).limit_denominator(8000)
        if fraction.numerator == 1:
            return f"1/{fraction.denominator} s"
    return f"{seconds:g} s"


def shown_size(
    exif: ExifData, preview_size: tuple[int, int] | None
) -> tuple[int, int] | None:
    """The photo's width and height as shown, or ``None`` if not recorded.

    EXIF records the sensor's size, before the camera's rotation, so a
    portrait shot often reads as landscape. The saved preview is rotated, so
    when its shape disagrees, the EXIF numbers are swapped.
    """
    width, height = exif.width_px, exif.height_px
    if not width or not height:
        return None
    if preview_size is None or preview_size[0] == preview_size[1]:
        return width, height  # no preview, or square: nothing to go by
    preview_portrait = preview_size[1] > preview_size[0]
    return (height, width) if preview_portrait != (height > width) else (width, height)


def camera_settings(
    exif: ExifData, preview_size: tuple[int, int] | None = None
) -> list[tuple[str, str]]:
    """Return the ``(label, value)`` camera settings to show, skipping missing ones.

    Args:
        exif: The photo's camera data.
        preview_size: Width and height of the saved (rotated) preview, used to
            show the photo's size the way round it is viewed.
    """
    size = shown_size(exif, preview_size)
    rows = [
        ("Camera", " ".join(p for p in (exif.make, exif.model) if p) or None),
        ("Lens", exif.lens_model),
        ("Lens make", exif.lens_make),
        ("Lens range", exif.lens_spec),
        (
            "Focal length",
            f"{exif.focal_length_mm:g} mm" if exif.focal_length_mm else None,
        ),
        ("Aperture", f"f/{exif.f_number:g}" if exif.f_number else None),
        ("Shutter", format_exposure(exif.exposure_time_s)),
        ("ISO", str(exif.iso) if exif.iso else None),
        ("White balance", format_white_balance(exif)),
        ("Size", f"{size[0]} × {size[1]}" if size else None),
    ]
    return [(label, value) for label, value in rows if value]


def capture_label(record: PhotoRecord) -> str:
    """Return e.g. ``2026-01-11 14:15`` or ``Unknown date``."""
    captured = record.exif.captured_at
    return captured.strftime("%Y-%m-%d %H:%M") if captured else "Unknown date"


def thumbnail_tooltip(record: PhotoRecord) -> str:
    """Hover tooltip of a gallery thumbnail, as Markdown.

    The file name in bold, the description, then the capture day and scene in
    grey. The name and description are escaped, so ``_DSC0001`` stays as is.
    """
    captured = record.exif.captured_at
    day = captured.strftime("%Y-%m-%d") if captured else "Unknown date"
    return (
        f"**{escape_markdown(record.path.name)}**\n\n"
        f"{escape_markdown(record.annotation.description)}\n\n"
        f":gray[{day} · {record.annotation.scene.value}]"
    )


def date_source_label(source: DateSource | None) -> str:
    """Readable name for where the capture date came from."""
    return DATE_SOURCE_LABELS.get(source, "unknown") if source else "unknown"


WB_SOURCE_LABELS = {
    WhiteBalanceSource.CAMERA: "recorded by camera",
    WhiteBalanceSource.ESTIMATED: "estimated",
    WhiteBalanceSource.EDITED: "set in editor",
}


def format_white_balance(exif: ExifData) -> str | None:
    """Return e.g. ``Auto · ≈ 5,400 K (estimated)``, or ``None`` if unknown."""
    parts: list[str] = []
    if exif.white_balance:
        parts.append(exif.white_balance)
    if exif.white_balance_k is not None:
        estimated = exif.white_balance_k_source is WhiteBalanceSource.ESTIMATED
        kelvin = f"{'≈ ' if estimated else ''}{exif.white_balance_k:,} K"
        source = WB_SOURCE_LABELS.get(exif.white_balance_k_source)  # type: ignore[arg-type]
        parts.append(f"{kelvin} ({source})" if source else kelvin)
    return " · ".join(parts) or None


def path_digest(path: Path | str) -> str:
    """Short stable id of a path, for widget keys."""
    return hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()[:16]


MARKDOWN_SPECIAL = frozenset("\\`*_{}[]()#+-.!|~<>$:")


def escape_markdown(text: str) -> str:
    """Show ``text`` literally in Streamlit Markdown (file names, folders)."""
    return "".join(f"\\{c}" if c in MARKDOWN_SPECIAL else c for c in text)
