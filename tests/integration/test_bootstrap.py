"""The ``open_*`` functions build each command against a real (temporary) database."""

import shutil
from pathlib import Path

import pytest

from raw_and_order.bootstrap import open_exif_rereader, open_pipeline, open_rehasher
from raw_and_order.config import Settings
from raw_and_order.db.base import Base
from raw_and_order.db.session import create_db_engine
from raw_and_order.maintenance.exif_reread import ExifRereader
from raw_and_order.maintenance.rehash import PerceptualRehasher
from raw_and_order.pipeline import PhotoPipeline

needs_exiftool = pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="no exiftool"
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    url = f"sqlite:///{tmp_path / 'app.db'}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return Settings(_env_file=None, database_url=url, preview_dir=tmp_path / "p")


def test_open_rehasher_runs_on_an_empty_library(settings: Settings) -> None:
    with open_rehasher(settings) as rehasher:
        assert isinstance(rehasher, PerceptualRehasher)
        summary = rehasher.run()

    assert summary.checked == 0


@needs_exiftool
def test_open_exif_rereader_runs_on_an_empty_library(
    settings: Settings, tmp_path: Path
) -> None:
    with open_exif_rereader(settings) as rereader:
        assert isinstance(rereader, ExifRereader)
        summary = rereader.run(tmp_path)

    assert summary.checked == 0


@needs_exiftool
def test_open_pipeline_processes_an_empty_folder(
    settings: Settings, tmp_path: Path
) -> None:
    empty = tmp_path / "photos"
    empty.mkdir()

    with open_pipeline(settings) as pipeline:
        assert isinstance(pipeline, PhotoPipeline)
        summary = pipeline.run(empty)

    assert summary.selected == 0
    assert summary.failed == []
