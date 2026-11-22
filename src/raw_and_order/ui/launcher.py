"""Build the command that starts the Streamlit UI.

The ``raw-and-order ui`` command (``main.py``) runs this argv as a child
process, so the UI always starts on localhost with the same theme, port
and toolbar.
"""

import importlib.util
import sys
from pathlib import Path

from raw_and_order.exceptions import ConfigurationError

APP_PATH = Path(__file__).with_name("app.py")
# Light and dark themes plus the page padding (see the file).
THEME_PATH = Path(__file__).with_name("theme.toml")
DEFAULT_PORT = 8501
# "viewer" shows the top-right menu (System / Light / Dark theme switch) but
# hides developer items such as Rerun and Deploy.
TOOLBAR_MODE = "viewer"


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
        TOOLBAR_MODE,
        "--theme.base",
        str(THEME_PATH),
        "--server.headless",
        "false" if open_browser else "true",
    ]
