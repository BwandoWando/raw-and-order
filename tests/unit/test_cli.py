import pytest
from typer.testing import CliRunner

from my_agent.main import app

runner = CliRunner()


@pytest.mark.parametrize("value", ["0", "2001"])
def test_max_photos_outside_range_is_rejected(value: str) -> None:
    result = runner.invoke(app, ["process", "/tmp", "--max-photos", value])

    assert result.exit_code == 2  # usage error, nothing runs
    assert "--max-photos" in result.output


def test_help_mentions_max_photos() -> None:
    result = runner.invoke(app, ["process", "--help"])

    assert "--max-photos" in result.output
