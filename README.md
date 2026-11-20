# my-agent

A LangGraph agent that reads camera raw files (CR2, CR3, NEF, ARW, RAF, ORF,
RW2, DNG), extracts EXIF metadata, creates a preview, asks a vision LLM to
annotate it, and stores everything in SQLite.

```
discover ─▶ extract_exif ─▶ decode_raw ─▶ annotate ─▶ persist
```

A failure in one file is recorded against that file; the rest of the batch
continues. Files already in the database are skipped unless `--reprocess`.

## Requirements

- Python 3.11+
- [exiftool](https://exiftool.org/): `sudo apt install libimage-exiftool-perl`
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
