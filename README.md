# Raw and Order

Catalogues a folder of camera raw files and regular images. It extracts EXIF
metadata, makes an upright JPEG preview, asks a vision LLM (local Ollama,
OpenAI or Anthropic) for a description and tags, and stores everything in
SQLite. A local Streamlit app lets you browse, filter and explore the
catalogue. The command is `raw-and-order` and the Python package
`raw_and_order`.

Each run is a plain ordered workflow (`workflow/runner.py`):

```
plan:     discover ─▶ fingerprint ─▶ skip_known ─▶ skip_copies ─▶ record_copies ─▶ select_batch
per chunk: extract_exif ─▶ decode ─▶ perceptual_hash ─▶ annotate ─▶ persist
```

`--reprocess-failed` starts from the failure log instead of `discover`.

**Supported files**
- Raw (via LibRaw): CR2, CR3, NEF, ARW, RAF, ORF, RW2, DNG (`RAW_EXTENSIONS`)
- Images (via Pillow): JPEG, PNG, TIFF, WebP, and HEIC/HEIF with the `heic`
  extra (`IMAGE_EXTENSIONS`)

**RAW+JPEG pairs:** if a raw file and an image with the same name are in the
same folder (e.g. `DSC_0042.NEF` and `DSC_0042.JPG`) and were captured within
one second of each other (EXIF `DateTimeOriginal`), only the raw file is
processed; the image is skipped and counted in the run summary. Files are
never paired across folders. Cameras reuse names (a Sony counter wraps from
`DSC09999` back to `DSC00001`), so a same-name image with a different capture
time is a different shot and is kept. If either file has no capture time, the
name alone decides. Only same-name files have their capture time read, in one
batch, so this adds about a second per thousand pairs.

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

**Fingerprints:** every file gets a SHA-256 of its contents and a 64-bit
perceptual hash (pHash: the 8×8 lowest frequencies of a DCT) of its preview. A
stored photo is skipped while its SHA-256 is unchanged, so edited files are
processed again automatically and `--reprocess` forces everything. Two photos
count as similar (shown as "Similar photos" in the UI) when their pHashes
differ in at most 14 of 64 bits **and** they share at least 25% of each
photo's tags. The pHash describes the overall structure of light and dark (it
barely changes with resizing, compression or brightness edits), so on its own
it can also match unrelated photos with a similar layout; the tags confirm the
content. After upgrading from an older hash, run `raw-and-order rehash` once:
it recomputes every stored hash from the saved previews (no LLM calls).

**Exact copies:** a file whose SHA-256 matches a photo stored at another path
(e.g. the same shot copied to a backup folder) is not annotated again. It is
skipped, counted in the run summary and logged in the `photo_copies` table with
the path of its original. Within one run, the first file by path is the
original. If the original file has since been deleted, the copy is processed as
a normal photo. Copies are skipped even with `--reprocess`; logged copies that
are no longer found (deleted, or edited so they differ) are forgotten on the
next full run of their folder. A different image that happens to share a file
name (a wrapped counter) has a different SHA-256, so it is always kept.

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
continues. Errors about one image (e.g. HTTP 400/413) are still logged per
photo. After `MAX_CONSECUTIVE_FAILURES` annotation failures in a row the run
also stops, since that usually means the model is misbehaving.

## Requirements

| What | Version | Notes |
|---|---|---|
| Python | 3.11+ | Developed and tested on 3.12 in a conda env |
| [exiftool](https://exiftool.org/) | **12.15+** | Must be on `PATH`; check with `exiftool -ver` |
| An LLM with vision | - | A local [Ollama](https://ollama.com/) model (tested with Ollama 0.32 and `gemma3:12b`), or an OpenAI or Anthropic API key |
| Git | - | To clone the repository |

LibRaw (raw decoding) comes bundled with the `rawpy` wheel and HEIC support
with `pillow-heif`, so they need no system packages. Ollama runs on CPU, but a
GPU makes annotation much faster.

**exiftool:** Ubuntu 20.04's apt package is 11.88, which is too old. Install a
current release without sudo:

```bash
mkdir -p ~/.local/opt ~/.local/bin
V=$(curl -fsS https://exiftool.org/ver.txt)
curl -fsSL "https://github.com/exiftool/exiftool/archive/refs/tags/$V.tar.gz" \
  | tar -xz -C ~/.local/opt
ln -sf ~/.local/opt/exiftool-$V/exiftool ~/.local/bin/exiftool
exiftool -ver       # if not found, add ~/.local/bin to PATH
```

## Installation

```bash
git clone git@github.com:BwandoWando/raw-and-order.git
cd raw-and-order

conda create -n raw-and-order python=3.12 && conda activate raw-and-order
conda env config vars set PYTHONNOUSERSITE=1      # ignore packages in ~/.local
conda deactivate && conda activate raw-and-order  # apply it

pip install -e ".[dev,ollama,heic,ui]"
cp .env.example .env    # then edit (model, provider, limits)
alembic upgrade head    # create / migrate data/app.db
pre-commit install      # optional: lint + type-check on commit
```

**Pick a model.** For Ollama, pull a vision model and set it in `.env`:

```bash
ollama pull gemma3:12b   # LLM__MODEL=gemma3:12b (also gemma3:4b, gemma3:27b)
raw-and-order check      # config valid, model reachable, supports images
```

`llama3.2-vision` fails to load on recent Ollama versions ("unknown model
architecture: 'mllama'"), so use `gemma3` or another vision model. For OpenAI
or Anthropic, set `LLM__PROVIDER`, `LLM__MODEL` and `LLM__API_KEY` instead (see
`.env.example`).

Whenever you pull new code, run `pip install -e ".[dev,ollama,heic,ui]"` and
`alembic upgrade head` again in case dependencies or tables changed.

## Usage

```bash
raw-and-order check                                       # config valid, model reachable, supports images
raw-and-order process /path/to/photos                     # process new and changed files
raw-and-order process /path/to/photos --reprocess         # process everything again
raw-and-order process /path/to/photos --reprocess-failed  # retry only logged failures
raw-and-order process /path/to/photos --reread-exif       # refresh EXIF of stored photos (no LLM)
raw-and-order process /path/to/photos --max-photos 1500   # up to 1500 photos this run (max 5000)
raw-and-order process /path/to/photos --chunk-size 10     # save every 10 photos
raw-and-order process /path/to/photos --skip-model-check  # skip the startup LLM check
raw-and-order rehash                                      # recompute similar-photo hashes (no LLM)
```

Folders are searched recursively. Each run prints a summary: photos processed
(saved and failed), unchanged, previously failed, RAW+JPEG pairs skipped,
exact copies skipped (the first five listed with their original), and how many
remain for the next run.
`python -m raw_and_order` works the same as `raw-and-order`.

## Photo browser (Streamlit)

```bash
raw-and-order ui   # opens http://localhost:8501 (needs the ui extra)
raw-and-order ui --port 8600 --no-open-browser
```

Stop it with Ctrl+C. In VS Code, the **Streamlit UI** debug configuration in
`.vscode/launch.json` runs it with breakpoints.

- **Filters** (sidebar): text search over descriptions and tags, scene, tags
  (all of; each listed with its number of photos, e.g. `urban (431)`), people,
  camera, lens, capture-date range, white balance (K) range, GPS only,
  annotating model. They apply to the Gallery, Tags and Export tabs.

- **Gallery:** a thumbnail grid (24 / 48 / 72 / 99 per page) sized so a whole
  page fits on one screen, with the pager below it (or the left and right
  arrow keys). Tiles shrink as the page size grows and follow the window when
  you resize it. The page size is kept in the URL (`?g_page_size=99`), so you
  can bookmark it. Hover a photo for its date and scene; click it to see the
  large preview, description, tags, camera and lens settings, a map when the
  photo has GPS, its SHA-256 and pHash, exact copies of it stored elsewhere
  ("Also stored at"), and similar photos. The dialog fits one screen, with the
  file name at the top; click the photo to see it full screen, as large as the
  window allows. Step to the previous or next photo on the gallery page with
  the buttons at its edges (shown on hover) or the arrow keys; click a similar
  photo to show it in the dialog. Similar photos are labelled by pHash
  distance (of 64 bits): Identical (0–2), Very similar (3–8) and Similar
  (9–14); all of them share at least 25% of their tags.
- **Tags:** a network of the most-used tags (20–100). Bubble size is the number
  of photos; lines join tags that often appear together (Jaccard overlap above
  the "Link strength" slider). Tags are grouped into clusters (Louvain
  community detection), each drawn in its own colour and shape, and listed as
  cards and in a table. Hover to highlight links, drag to rearrange, scroll to
  zoom. The sidebar filters apply.
- **Failures:** the `processing_failures` log, filterable by stage.
- **Stats:** totals (including copies skipped) and photos by scene, lens,
  capture month and white balance.
- **Export:** download the photos matching the sidebar filters as Excel
  (.xlsx), CSV or JSON, one row per photo: file, capture date, camera and lens
  settings, GPS, description, tags, scene, people, model, processing time (UTC),
  SHA-256, pHash and preview path. Excel gets a frozen, filterable header and
  real dates; CSV joins tags with `; ` (UTF-8 with BOM, so Excel reads accents);
  JSON keeps tags as lists. A preview of the first 10 rows shows the columns.
- **Light and dark theme:** switch with the ⋮ menu at the top right (System /
  Light / Dark); the choice is remembered in the browser. The dark theme is a
  neutral graphite, as in photo editors, so photos keep their true colours.
  Both themes are defined in `src/raw_and_order/ui/theme.toml`.

The UI only reads the database, so it is safe to keep open during a processing
run (press **Refresh data** to see new photos). It listens on `localhost` only
and Streamlit's usage statistics are turned off (see `.streamlit/config.toml`).

## Configuration

All settings come from environment variables or `.env`
(see [.env.example](.env.example)). Nested settings use `__`, e.g. `LLM__MODEL`.

| Setting | Default | Purpose |
|---|---|---|
| **LLM** | | |
| `LLM__PROVIDER` | `ollama` | `ollama`, `openai` or `anthropic` |
| `LLM__MODEL` | `gemma3:12b` | Model name for the provider |
| `LLM__BASE_URL` | provider default | e.g. `http://localhost:11434` for Ollama |
| `LLM__API_KEY` | - | Required for OpenAI / Anthropic |
| `LLM__TEMPERATURE` | provider default | Sampling temperature |
| `LLM__TIMEOUT_SECONDS` | `120` | Per-request timeout (`.env.example` uses `300` for local models) |
| `LLM__MAX_RETRIES` | `3` | Attempts for transient provider errors |
| `LLM__MAX_OUTPUT_FIX_ATTEMPTS` | `2` | Attempts to get output that matches the annotation schema |
| **Runs** | | |
| `MAX_PHOTOS_PER_RUN` | `500` | Process at most this many photos per run, first by path; the rest wait for the next run (1–5000; `--max-photos`) |
| `CHUNK_SIZE` | `25` | Photos processed and saved together; an interruption loses at most one chunk (1–5000; `--chunk-size`) |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Stop a run after this many annotation failures in a row (`0` = never) |
| `MAX_TAGS` | `20` | Most tags the LLM may give one photo (1–50); sets both the prompt and the validation |
| `DATE_SOURCES` | `exif_original,xmp,exif_create,filename` | Capture-date sources, in order |
| `SEND_EXIF_TO_LLM` | `true` | Send camera metadata as context |
| `REDACT_GPS` | `true` | Never send GPS coordinates to the LLM |
| **Files and storage** | | |
| `DATABASE_URL` | `sqlite:///data/app.db` | App database (managed by Alembic) |
| `PREVIEW_DIR` | `data/previews` | Where preview JPEGs are written |
| `PREVIEW_MAX_PX` | `1024` | Longest side of a preview, in pixels |
| `PREVIEW_QUALITY` | `85` | JPEG quality of previews (1–100) |
| `RAW_EXTENSIONS` | CR2, CR3, NEF, ARW, RAF, ORF, RW2, DNG | Files decoded as raw |
| `IMAGE_EXTENSIONS` | JPG, JPEG, PNG, TIF, TIFF, WebP, HEIC, HEIF | Files decoded with Pillow |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

## Project layout

```
src/raw_and_order/
├── main.py           CLI (Typer); top-level error handling
├── bootstrap.py      composition root: the only place concrete classes are built
├── config.py         pydantic-settings
├── exceptions.py     domain exception hierarchy
├── pipeline.py       runs the workflow, builds the run summary
├── exif_reread.py    --reread-exif: refresh EXIF columns of stored photos
├── rehash.py         raw-and-order rehash: recompute stored perceptual hashes
├── workflow/         state, steps (nodes/), routing, ordered runner
├── media/            discovery, exiftool, raw/Pillow decoding, previews, hashing
├── llm/              provider factory, capability check, annotator, prompts
├── schemas/          Pydantic models shared across layers
├── db/               SQLAlchemy models, session, repositories, read-only catalog
├── analysis/         pure computations (tag network, clusters, similarity)
├── export/           export rows and Excel / CSV / JSON encoding
└── ui/               Streamlit app; renderers receive a PhotoLibrary
migrations/           Alembic
tests/                unit/ and integration/, using injected fakes
```

## Development

```bash
ruff format . && ruff check . && mypy src tests && pytest   # all must pass
alembic revision --autogenerate -m "describe change"       # after editing db/models.py
```

Tests never touch your real `data/`: a fixture points the database, previews
and LLM at throwaway locations. Coding rules: PEP 8 via Ruff (line length 88),
strict mypy, Pure DI (constructor injection; only `bootstrap.py` builds
concrete classes), single-responsibility steps, and only the domain exceptions
in `exceptions.py`. VS Code debug configurations for the CLI, the current test
file and the UI are in `.vscode/launch.json`.