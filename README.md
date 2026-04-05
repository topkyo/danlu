# aiwiki

`aiwiki` is a local-first knowledge compiler scaffold.

It treats a knowledge base like a build artifact:

- `raw/` holds the source material
- `wiki/` holds compiled markdown knowledge
- `output/` holds query artifacts such as reports, slide decks, and figure briefs
- `open-harness` wraps the project with contracts, verification, and review gates

## Current MVP

The repository ships a Python CLI with deterministic commands plus optional LLM-backed execution commands.

Deterministic commands:

- `ingest`: register a local file or a URL stub into `raw/`
- `compile`: turn the current source inventory into `wiki/sources/` pages and indexes
- `ask`: generate a report, slide deck, or figure brief artifact grounded in the wiki
- `file-back`: move a useful markdown output back into `wiki/derived/`
- `lint`: scan for missing source pages, broken source references, and obvious provenance gaps

LLM-backed execution commands:

- `run-compile`: replace placeholder source summaries using a configured LLM
- `run-ask`: create a query artifact and let the LLM fill it with grounded content
- `run-lint`: run deterministic lint, then generate a semantic lint report
- `llm-check`: show whether the LLM runner is configured
- `auto-once`: run the whole ingest/compile/summary/lint pipeline once
- `watch`: keep watching `raw/inbox/` and trigger the pipeline automatically on changes

Direct raw-material entry points:

- `drop-url`: fetch a web page into `raw/inbox/`, render it in a browser when available, extract main content, and store page images under `raw/assets/`
- `drop-pdf`: store the original PDF under `raw/assets/` and extracted text under `raw/inbox/`
- `drop-image`: store the original image under `raw/assets/` and a metadata note under `raw/inbox/`
- `drop-repo`: snapshot a local or remote repository into a markdown source note under `raw/inbox/`

The deterministic path remains the safe baseline. The LLM runner is additive and uses prompt files plus explicit file-path citations.

## Layout

```text
raw/
  inbox/        direct drops or imported source files
  normalized/   reserved for future normalization steps
  assets/       local images and attachments
wiki/
  sources/      one source page per raw input
  concepts/     reserved for future concept synthesis
  indexes/      inventory and compile status pages
  derived/      filed-back markdown outputs
output/
  reports/
  slides/
  figures/
  lint/
.aiwiki/
  state/        manifest and incremental state
  cache/
  logs/
prompts/
  compile.md
  ask.md
  lint.md
```

## Obsidian Role

Obsidian is intended to be the `aiwiki` frontend or IDE, not the knowledge compiler itself.

- `aiwiki` owns ingest, compile, query, lint, automation, and provenance
- Obsidian is where you browse `raw/`, inspect `wiki/`, and read `output/`
- You can add plugins such as Web Clipper or Marp, but the source of truth remains the repo layout on disk

The intended operating model is:

- drop or capture material into the repo
- let `aiwiki` compile and maintain the markdown artifacts
- use Obsidian to navigate and review those artifacts

Repo-local Obsidian assets are included:

- `.obsidian/app.json`: default note and attachment folders point at `raw/inbox/` and `raw/assets/`
- `.obsidian/workspace.json`: opens a dashboard plus scoped search tabs for `raw`, `wiki`, and `output`
- `HOME.md`: default landing page for the vault
- `wiki/indexes/*.md`: navigation and search reference pages

To use it, open `/home/tim/ai-wiki` as an Obsidian vault.

## LLM Configuration

The execution layer supports three backends:

- `codex-cli`: uses local `codex exec`
- `claude-cli`: uses local `claude --print`
- `openai-api`: uses an OpenAI-compatible `/chat/completions` endpoint

Selection rules:

1. If `AIWIKI_LLM_BACKEND` is set, that backend is used.
2. Otherwise `aiwiki` auto-resolves in this order:
3. `openai-api` if model + API key are present
4. `codex-cli` if `codex` is installed
5. `claude-cli` if `claude` is installed

Common variables:

```bash
export AIWIKI_LLM_BACKEND="codex-cli"                    # optional: auto | codex-cli | claude-cli | openai-api
export AIWIKI_LLM_MODEL="gpt-4.1-mini"                  # optional for CLI backends, required for openai-api
export AIWIKI_LLM_TIMEOUT="120"                         # optional
export AIWIKI_LLM_TEMPERATURE="0.2"                     # optional; only used by openai-api
export AIWIKI_LLM_MAX_CONTEXT_CHARS="24000"             # optional
```

CLI-specific variables:

```bash
export AIWIKI_CODEX_COMMAND="codex"                     # optional
export AIWIKI_CLAUDE_COMMAND="claude"                   # optional
```

OpenAI-compatible API variables:

```bash
export AIWIKI_LLM_BACKEND="openai-api"
export AIWIKI_LLM_MODEL="gpt-4.1-mini"
export AIWIKI_LLM_API_KEY="..."
export AIWIKI_LLM_BASE_URL="https://api.openai.com/v1"  # optional
```

`OPENAI_MODEL`, `OPENAI_API_KEY`, and `OPENAI_BASE_URL` are accepted as fallbacks for the API backend.

`llm-check` reports the resolved backend and whether auth is handled by an API key or by the local CLI session.
It also reports whether the resolved backend supports image analysis for `drop-image`.

## Usage

Install in editable mode if you want a shell command:

```bash
pip install -e .
```

Or invoke it directly from the repo:

```bash
PYTHONPATH=src python3 -m aiwiki.cli --root . ingest /path/to/paper.md
PYTHONPATH=src python3 -m aiwiki.cli --root . ingest https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-url https://example.com/article
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-pdf /path/to/paper.pdf
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-image /path/to/diagram.png --no-vision
PYTHONPATH=src python3 -m aiwiki.cli --root . drop-repo https://github.com/user/repo.git
PYTHONPATH=src python3 -m aiwiki.cli --root . compile
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
AIWIKI_LLM_BACKEND=claude-cli PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare A and B" --format report
AIWIKI_LLM_BACKEND=openai-api PYTHONPATH=src python3 -m aiwiki.cli --root . run-lint
PYTHONPATH=src python3 -m aiwiki.cli --root . run-compile --limit 3
PYTHONPATH=src python3 -m aiwiki.cli --root . ask "Compare A and B" --format report
PYTHONPATH=src python3 -m aiwiki.cli --root . run-ask "Compare A and B" --format report
PYTHONPATH=src python3 -m aiwiki.cli --root . file-back output/reports/20260405-120000-compare-a-and-b.md
PYTHONPATH=src python3 -m aiwiki.cli --root . lint
PYTHONPATH=src python3 -m aiwiki.cli --root . run-lint
PYTHONPATH=src python3 -m aiwiki.cli --root . llm-check
```

## Hands-Off Mode

If you want the Karpathy-style workflow where you only drop material into the inbox, use the automation entry points.

Run one automatic pass:

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . auto-once
```

Run the watcher and then just copy files into `raw/inbox/`:

```bash
AIWIKI_LLM_BACKEND=codex-cli PYTHONPATH=src python3 -m aiwiki.cli --root . watch --interval 5
```

Once `watch` is running, the intended flow is:

- You drop files into `raw/inbox/`
- Or you use `drop-url`, `drop-pdf`, `drop-image`, or `drop-repo`
- `aiwiki` discovers them automatically
- source pages are compiled under `wiki/sources/`
- the LLM fills pending summaries
- lint artifacts are refreshed under `output/lint/`

If you want a quieter/offline mode, add `--deterministic-only`.

## Material Drop Modes

`drop-url`

- Best for articles, blog posts, docs pages, and newsletters
- Fetches the page, prefers a browser-rendered DOM when Playwright Chromium is available, then extracts `article` / `main` content
- Downloads a limited set of page images into `raw/assets/` and links them from the note frontmatter
- Falls back to direct HTTP + BeautifulSoup extraction if browser rendering is unavailable
- If a site blocks basic fetching, clip it manually and drop the markdown file instead

Optional browser-render setup:

```bash
python3 -m pip install --user playwright
python3 -m playwright install chromium
```

`drop-pdf`

- Best for papers, reports, slide decks, and exported docs
- Copies the original PDF to `raw/assets/`
- Runs `pdftotext` and writes extracted text into a markdown source note in `raw/inbox/`
- Scanned PDFs may still need OCR

`drop-image`

- Best for screenshots, figures, diagrams, whiteboard photos, and long-image posts
- Copies the original image to `raw/assets/`
- Writes an image note into `raw/inbox/` with metadata, OCR text, and optional visual analysis
- OCR is included when `tesseract` is available on the machine
- On Ubuntu, install OCR support with `sudo apt-get install -y tesseract-ocr`
- LLM-backed visual analysis is attempted automatically when the resolved backend supports image input
- Current image-analysis backends are `codex-cli` and `openai-api`
- Use `--no-vision` if you want a purely local metadata/OCR drop

`drop-repo`

- Best for local repositories or remote git URLs
- Captures README text, repo tree, key config files, and selected source excerpts
- Produces one snapshot note in `raw/inbox/`

## User Service

To make the watcher start automatically for your user session, install the provided `systemd --user` service:

```bash
cd /home/tim/ai-wiki
bash scripts/install_user_service.sh
```

This installs:

- unit file: `~/.config/systemd/user/aiwiki-watch.service`
- env file: `~/.config/aiwiki/aiwiki-watch.env`

Default env file values use `codex-cli`. Adjust the env file if you want `claude-cli` or `openai-api`, then restart the service:

```bash
systemctl --user restart aiwiki-watch.service
systemctl --user status --no-pager aiwiki-watch.service
journalctl --user -u aiwiki-watch.service -n 100 --no-pager
```

To remove the service:

```bash
bash scripts/uninstall_user_service.sh
```

## Verification

Run the local verification entry point:

```bash
bash scripts/verify.sh
```

This repository uses the `open-harness` Standard tier, so the current sprint scope lives in `.codex/contracts/active.md` and review outcomes belong in `.codex/gates/`.
