import pytest
from typer.testing import CliRunner

from my_agent.main import app

runner = CliRunner()


@pytest.mark.parametrize("option", ["--max-photos", "--chunk-size"])
@pytest.mark.parametrize("value", ["0", "2001"])
def test_options_outside_range_are_rejected(option: str, value: str) -> None:
    result = runner.invoke(app, ["process", "/tmp", option, value])

    assert result.exit_code == 2  # usage error, nothing runs
    assert option in result.output


def test_help_mentions_max_photos() -> None:
    result = runner.invoke(app, ["process", "--help"])

    assert "--max-photos" in result.output
    assert "--chunk-size" in result.output
