"""Logging setup for the application entry point."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Configure root logging once, at startup.

    Args:
        level: Log level name such as ``"INFO"`` or ``"DEBUG"``.
    """
    logging.basicConfig(level=level.upper(), format=LOG_FORMAT)
    for noisy in ("httpx", "httpcore", "exiftool"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
