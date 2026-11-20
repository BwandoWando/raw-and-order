"""Build the command that starts the Streamlit UI."""

import importlib.util
import sys
from pathlib import Path

from my_agent.exceptions import ConfigurationError

APP_PATH = Path(__file__).with_name("app.py")
DEFAULT_PORT = 8501


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
        "--server.headless",
        "false" if open_browser else "true",
    ]
