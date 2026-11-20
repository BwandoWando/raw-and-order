"""Optional HEIC/HEIF support for Pillow (``pip install -e ".[heic]"``)."""

import importlib
import logging

logger = logging.getLogger(__name__)


def enable_heif_support() -> bool:
    """Register the HEIF opener with Pillow if ``pillow-heif`` is installed.

    Returns:
        True if HEIC/HEIF files can now be opened.
    """
    try:
        pillow_heif = importlib.import_module("pillow_heif")
    except ImportError:
        logger.info('HEIC support disabled; install with: pip install -e ".[heic]"')
        return False
    pillow_heif.register_heif_opener()
    return True
