# my-agent

An ordered workflow that reads camera raw files and regular images, extracts
EXIF metadata, creates an upright preview, asks a vision LLM to annotate it,
and stores everything in SQLite.

```
discover ─▶ extract_exif ─▶ decode ─▶ annotate ─▶ persist
```

**Supported files**
- Raw (via LibRaw): CR2, CR3, NEF, ARW, RAF, ORF, RW2, DNG (`RAW_EXTENSIONS`)
- Images (via Pillow): JPEG, PNG, TIFF, WebP, and HEIC/HEIF with the `heic`
  extra (`IMAGE_EXTENSIONS`)

**RAW+JPEG pairs:** if a raw file and an image with the same name are in the
same folder (e.g. `DSC_0042.NEF` and `DSC_0042.JPG`), only the raw file is
processed; the image is skipped and counted in the run summary.

**Capture date** (used for the database and the preview folder
`data/previews/YYYYMMDD/<extension>/`), first plausible source wins:

1. EXIF `DateTimeOriginal`
2. XMP `DateCreated` / `DateTimeOriginal` (e.g. Lightroom exports)
3. EXIF `CreateDate`
4. A date in the file name (`IMG_20240501_183000`, `PXL_…`, `IMG-20240501-WA0001`,
   `Screenshot 2024-05-01 at 18.30.00`, `2024-05-01`)
5. otherwise `unknown-date`

Dates before 1990, camera reset dates (2000-01-01, 2001-01-01, 2010-01-01) and
dates more than a day in the future are rejected. Times are kept as recorded
(no timezone conversion). The source used is stored in `photos.date_source`.
Reorder or trim with `DATE_SOURCES` in `.env`.

**White balance:** the mode (e.g. Auto, Daylight) and the colour temperature in
kelvin. Sources, first found wins: the camera's recorded value (`camera`: e.g.
K mode, or Canon's as-shot temperature); an estimate from the camera's
white-balance calibration (`estimated`: most Sony Auto WB shots, accurate to a
few hundred K); Lightroom's `XMP-crs:ColorTemperature` (`edited`).

**Re-reading EXIF:** `--reread-exif` re-reads the EXIF of photos already stored
from the folder and updates only those columns (dates, lens, white balance,
GPS, camera settings). Annotations, previews and hashes are kept and no LLM is
called, so it is fast (about 15 s for 1,000 photos). Use it after an update adds
or fixes EXIF fields. Missing files are listed and skipped. Previews stay in
their original `YYYYMMDD` folder even if a corrected date differs.

**Lens:** `lens_model` (exiftool's lens database, then EXIF/maker-note/XMP lens
tags; numeric codes and placeholders are skipped), `lens_make`, and
`lens_spec` (e.g. `24-70mm f/2.8`).

**Batches and chunks:** each run takes the first `MAX_PHOTOS_PER_RUN` photos that
still need work (sorted by path) and processes them `CHUNK_SIZE` at a time.
Every chunk is saved before the next starts, so an interrupted run keeps all
finished chunks. Run the same folder again to continue: saved photos are
skipped as unchanged.

**Failures:** a file that fails any step is logged in the `processing_failures`
table (stage, error, attempts, first/last failure) and the rest of the batch
continues. Later runs skip logged failures, unless the file's contents changed
(then it is retried automatically). `--reprocess-failed` retries only the
logged failures under the folder that still exist (missing ones are removed
from the log); `--max-photos` and chunking still apply. A photo that succeeds
is removed from the log.

**Outages stop the run:** if the LLM is unavailable (model not found, server
unreachable, bad API key, still rate-limited or failing after retries), the run
stops at once with one message and exit code 1. No photo is logged as failed;
photos saved in earlier chunks are kept, and running the same command again
continues. Errors about one image (e.g. HTTP 400/413) are still logged per photo. Files already in the database are skipped unless `--reprocess`.

## Requirements

- Python 3.11+
- [exiftool](https://exiftool.org/) **12.15 or newer** (`exiftool -ver`). Ubuntu 20.04's
  apt package is 11.88, which is too old. Install a current release without sudo:
  ```bash
  V=$(curl -fsS https://exiftool.org/ver.txt)
  curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/$V.tar.gz" \
    | tar -xz -C ~/.local/opt
  ln -sf ~/.local/opt/exiftool-$V/exiftool ~/.local/bin/exiftool
  ```
- An LLM: a local [Ollama](https://ollama.com/) vision model, or an OpenAI or
  Anthropic API key

## Setup

```bash
conda create -n my-agent python=3.12 && conda activate my-agent
pip install -e ".[dev,ollama]"      # or [dev,openai], [dev,anthropic], [dev,all]
cp .env.example .env                # then edit
alembic upgrade head                # create / migrate the database
pre-commit install                  # lint + type-check on every commit
```

For Ollama, pull a vision model first, e.g. `ollama pull llama3.2-vision`.

## Usage

```bash
my-agent check                      # config valid, model reachable, supports images
my-agent process /path/to/raws      # process new files
my-agent process /path/to/raws --reprocess
my-agent process /path/to/raws --reprocess-failed   # retry only logged failures
my-agent process /path/to/raws --reread-exif        # refresh EXIF of stored photos (no LLM)
my-agent process /path/to/raws --max-photos 1500   # up to 1500 photos this run (max 5000)
my-agent process /path/to/raws --chunk-size 10     # save every 10 photos
```

## Photo browser (Streamlit)

```bash
pip install -e ".[ui]"     # once
my-agent ui                # opens http://localhost:8501
my-agent ui --port 8600 --no-open-browser
```

- **Gallery:** thumbnail grid (24 / 48 / 72 / 96 per page), sorted by capture or
  processing date. Click a photo (or **Details**) to see the large preview, description, tags,
  camera and lens settings, a map when the photo has GPS, its SHA-256 and dHash,
  and similar photos (dHash distance ≤ 10).
- **Filters** (sidebar): text search over descriptions and tags, scene, tags
  (all of), people, camera, lens, capture-date range, white balance (K) range,
  GPS only, annotating model.
- **Failures:** the `processing_failures` log, filterable by stage.
- **Stats:** totals and photos by scene, lens, capture month and white balance.

The UI only reads the database, so it is safe to keep open during a processing
run (press **Refresh data** to see new photos). It listens on `localhost` only
and Streamlit's usage statistics are turned off (see `.streamlit/config.toml`).

## Configuration

All settings come from environment variables or `.env`
(see [.env.example](.env.example)). Nested settings use `__`, e.g. `LLM__MODEL`.

| Setting | Default | Purpose |
|---|---|---|
| `LLM__PROVIDER` | `ollama` | `ollama`, `openai` or `anthropic` |
| `LLM__MODEL` | `llama3.2-vision` | Model name for the provider |
| `LLM__API_KEY` | - | Required for OpenAI / Anthropic |
| `DATABASE_URL` | `sqlite:///data/app.db` | App database (managed by Alembic) |
| `MAX_PHOTOS_PER_RUN` | `500` | Process at most this many photos per run, first by path; the rest wait for the next run (1–5000; `--max-photos`) |
| `CHUNK_SIZE` | `25` | Photos processed and saved together; an interruption loses at most one chunk (1–5000; `--chunk-size`) |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Stop a run after this many annotation failures in a row (`0` = never) |
| `MAX_TAGS` | `20` | Most tags the LLM may give one photo (1–50); sets both the prompt and the validation |
| `SEND_EXIF_TO_LLM` | `true` | Send camera metadata as context |
| `REDACT_GPS` | `true` | Never send GPS coordinates to the LLM |

## Project layout

```
src/my_agent/
├── main.py           CLI (Typer); top-level error handling
├── bootstrap.py      composition root: the only place concrete classes are built
├── config.py         pydantic-settings
├── exceptions.py     domain exception hierarchy
├── pipeline.py       runs the graph, builds the run summary
├── workflow/         state, steps (nodes/), routing, ordered runner
├── media/            discovery, exiftool, rawpy, previews (no LLM code)
├── llm/              provider factory, capability check, annotator, prompts
├── schemas/          Pydantic models shared across layers
└── db/               SQLAlchemy models, session, repository
migrations/           Alembic
tests/                unit/ and integration/, using injected fakes
```

## Development

```bash
pytest                    # tests
ruff check . && ruff format .
mypy src tests
alembic revision --autogenerate -m "describe change"   # after editing db/models.py
```
