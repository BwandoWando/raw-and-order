# my-agent

A LangGraph agent that reads camera raw files and regular images, extracts
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

**Lens:** `lens_model` (exiftool's lens database, then EXIF/maker-note/XMP lens
tags; numeric codes and placeholders are skipped), `lens_make`, and
`lens_spec` (e.g. `24-70mm f/2.8`).

A failure in one file is recorded against that file; the rest of the batch
continues. Files already in the database are skipped unless `--reprocess`.

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
my-agent process /path/to/raws --max-photos 1500   # one-off higher limit (max 2000)
```

## Configuration

All settings come from environment variables or `.env`
(see [.env.example](.env.example)). Nested settings use `__`, e.g. `LLM__MODEL`.

| Setting | Default | Purpose |
|---|---|---|
| `LLM__PROVIDER` | `ollama` | `ollama`, `openai` or `anthropic` |
| `LLM__MODEL` | `llama3.2-vision` | Model name for the provider |
| `LLM__API_KEY` | - | Required for OpenAI / Anthropic |
| `DATABASE_URL` | `sqlite:///data/app.db` | App database (managed by Alembic) |
| `CHECKPOINT_DB_PATH` | `data/checkpoints.db` | LangGraph checkpoints (separate DB) |
| `MAX_PHOTOS_PER_RUN` | `500` | Stop before processing if more photos need work (1–2000; override per run with `--max-photos`) |
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
├── graph/            LangGraph: state, nodes, routing, builder
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
