"""Build the command that starts the Streamlit UI."""

import importlib.util
import sys
from pathlib import Path

from my_agent.exceptions import ConfigurationError

APP_PATH = Path(__file__).with_name("app.py")
DEFAULT_PORT = 8501
# Tighter than Streamlit's default so a full gallery page fits on one screen.
PADDING_TOP = "2rem"
PADDING_BOTTOM = "1rem"


def streamlit_command(port: int = DEFAULT_PORT, open_browser: bool = True) -> list[str]:
    """Return the argv that runs the UI, bound to localhost with telemetry off.

    Raises:
        ConfigurationError: If Streamlit is not installed.
    """
    if importlib.util.find_spec("streamlit") is None:
        raise ConfigurationError('The UI needs Streamlit: pip install -e ".[ui]"')
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(APP_PATH),
        "--server.address",
        "localhost",
        "--server.port",
        str(port),
        "--browser.gatherUsageStats",
        "false",
        "--client.toolbarMode",
        "minimal",
        "--theme.paddingTop",
        PADDING_TOP,
        "--theme.paddingBottom",
        PADDING_BOTTOM,
        "--server.headless",
        "false" if open_browser else "true",
    ]
