"""Pure display helpers (no Streamlit), so they are easy to unit-test."""

from fractions import Fraction

from my_agent.schemas import DateSource, ExifData, PhotoRecord, WhiteBalanceSource

DATE_SOURCE_LABELS = {
    DateSource.EXIF_ORIGINAL: "EXIF DateTimeOriginal",
    DateSource.XMP: "XMP date",
    DateSource.EXIF_CREATE: "EXIF CreateDate",
    DateSource.FILENAME: "file name",
    DateSource.NONE: "no date found",
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


def camera_settings(exif: ExifData) -> list[tuple[str, str]]:
    """Return the EXIF rows to show, skipping missing values."""
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
        (
            "Size",
            f"{exif.width_px} × {exif.height_px}"
            if exif.width_px and exif.height_px
            else None,
        ),
    ]
    return [(label, value) for label, value in rows if value]


def capture_label(record: PhotoRecord) -> str:
    """Return e.g. ``2026-01-11 14:15`` or ``Unknown date``."""
    captured = record.exif.captured_at
    return captured.strftime("%Y-%m-%d %H:%M") if captured else "Unknown date"


def card_caption(record: PhotoRecord) -> str:
    """Short caption under a gallery thumbnail."""
    captured = record.exif.captured_at
    day = captured.strftime("%Y-%m-%d") if captured else "Unknown date"
    return f"{day} · {record.annotation.scene.value}"


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
