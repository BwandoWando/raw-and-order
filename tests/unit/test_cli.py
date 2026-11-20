import pytest
from typer.testing import CliRunner

from my_agent.config import MAX_PHOTOS_HARD_LIMIT
from my_agent.main import app

MISSING_DIR = "/nonexistent/my-agent-test-dir"

runner = CliRunner()


@pytest.mark.parametrize("option", ["--max-photos", "--chunk-size"])
@pytest.mark.parametrize("value", ["0", str(MAX_PHOTOS_HARD_LIMIT + 1)])
def test_options_outside_range_are_rejected(option: str, value: str) -> None:
    # A folder that does not exist: if validation ever fails, nothing is scanned.
    result = runner.invoke(app, ["process", MISSING_DIR, option, value])

    assert result.exit_code == 2  # usage error, nothing runs
    assert option in result.output


def test_help_mentions_max_photos() -> None:
    result = runner.invoke(app, ["process", "--help"])

    assert "--max-photos" in result.output
    assert "--chunk-size" in result.output


def test_reprocess_and_reprocess_failed_are_mutually_exclusive() -> None:
    result = runner.invoke(
        app, ["process", MISSING_DIR, "--reprocess", "--reprocess-failed"]
    )

    assert result.exit_code == 2
    assert "not both" in result.output


@pytest.mark.parametrize("other", ["--reprocess", "--reprocess-failed"])
def test_reread_exif_cannot_be_combined(other: str) -> None:
    result = runner.invoke(app, ["process", MISSING_DIR, "--reread-exif", other])

    assert result.exit_code == 2
    assert "--reread-exif" in result.output


def test_tests_never_see_the_real_database() -> None:
    from my_agent.config import load_settings

    settings = load_settings()

    assert "pytest" in settings.database_url  # a tmp_path, not data/app.db
    assert settings.llm.base_url == "http://127.0.0.1:9"
