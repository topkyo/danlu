# Raw Ingest Boundary Audit — 2026-05-21

> Scope: `aiwiki` drop/ingest paths vs constitution (`raw/` sole fact layer, F-INV-1~3, Product Shell UX checklist §130).
> Branch baseline: `fb455fa` + this round (`drop url/repo` metadata externalization, graph 1-hop connectivity).

## Invariant Matrix

| ID | Invariant | Status | Evidence |
|----|-----------|--------|----------|
| I-1 | `raw/` is sole fact input; derived layers do not overwrite raw | **PASS** | `compile/` / `runner/` / `execution/` have no `raw/` writers; `sync_manifest_with_raw` only updates manifest (`content/io.py:42-92`) |
| I-2 | `drop note` copies bytes without Capture Metadata / note frontmatter | **PASS** | `drop.py:_drop_note_unlocked` uses `atomic_copy_file` / `atomic_write_text`; `tests/test_drop.py` asserts no wrapper |
| I-3 | `drop pdf` / `drop image` store originals only in `raw/assets/` | **PASS** | `_materialize_pdf` / `_materialize_image`; inbox stays free of wrapper `.md` (`tests/test_drop.py`) |
| I-4 | `drop url` / `drop repo` raw files have no YAML frontmatter or capture-metadata sections | **PASS (this round)** | `_write_url_note_body` / `_write_repo_note_body`; metadata in `manifest.ingest_metadata` + `runtime-history.ingest_metadata` |
| I-5 | `ingest_source` HTTP URLs delegate to `drop_url`, no placeholder stub markdown | **PASS (this round)** | `content/io.py:121-132` |
| I-6 | New drops never overwrite existing raw paths | **PASS** | `_unique_path` / `_next_available_raw_path` across all drop paths |
| I-7 | Product Shell does not write `raw/` directly | **PASS** | Browser files → `.aiwiki/tmp/product-shell-drop` → CLI `drop *` (`helpers.js:resolvePluginFileSource`) |
| I-8 | Machine-memory graph nodes map to existing `.md` files | **PASS** | `app_memory.py:build_machine_memory_graph` filters missing pages |
| I-9 | Displayed sources retain visible graph edges to neighbors | **PASS (this round)** | `memory/graph.py` 1-hop neighbor expansion + SVG `node` before `edge` |
| I-10 | `raw/normalized/` has no production writers | **PASS** | Only `app_protocol.py` layout mkdir |

## Raw Write Surface (complete)

| Path | Writer | Target | Notes |
|------|--------|--------|-------|
| `drop_note` | `drop.py` | `raw/inbox` | Byte-faithful copy |
| `drop_pdf` | `drop.py` | `raw/assets` | PDF binary only |
| `drop_image` | `drop.py` | `raw/assets` | Image binary only |
| `drop_url` | `drop.py` | `raw/inbox` + optional `raw/assets` | Extracted text body only; fetch metadata external |
| `drop_repo` | `drop.py` | `raw/inbox` | README/tree/excerpts only; snapshot metadata external |
| `ingest_source` (file) | `content/io.py` | `raw/inbox` | `atomic_copy_file` |
| `ingest_source` (url) | `content/io.py` → `drop_url` | `raw/inbox` | No stub |
| `ensure_layout` | `app_protocol.py` | mkdir only | No content writes |

## Exceptions / Non-Goals

- **Obsidian evidence graph** (`.obsidian/graph.json`) filters `output/reports`, `wiki/sources`, `raw/inbox`, `raw/assets`, `wiki/judgments`, `wiki/indexes/evidence-graph` — **excludes** `wiki/concepts`. Source pages use plain-text concept paths (no wikilinks) so concepts are not pulled in as linked nodes. Full semantic graph (with concepts) remains `output/graph/machine-memory.html`.
- **Manual Obsidian notes** in `raw/inbox` via `newFileFolderPath` are outside CLI drop audit.
- **Vision/OCR text** for images lives in drop return value + manifest/history, not in raw files (by design).

## F-INV Checklist (dogfood 2026-05-21)

| Item | Result | Evidence |
|------|--------|----------|
| F-INV-1 PDF → `raw/assets` only | yes | `/home/tim/danlu/炼丹炉/raw/assets/*.pdf` |
| F-INV-2 note size / truncation | unchanged | existing drop limits |
| F-INV-3 no capture metadata in raw files | yes (new drops) | inbox `readme.md` clean; url/repo no frontmatter after this round |
| Image → assets not inbox md | yes | `hikedcjbqaadz3c.jpeg` in `raw/assets/` |

## Residual Risks

1. **Historical polluted raw** from pre-`fb455fa` drops may still exist in older vaults; operator should `rg "Capture Metadata" raw/` and re-drop or delete.
2. **`_write_text` rstrip** on url/repo new files trims trailing whitespace (not overwrite of existing files).
3. **English-only concept nodes** may appear when connected to a displayed Chinese source (intentional 1-hop connectivity tradeoff).

## Verification Run

```bash
PYTHONPATH=src python3 -m pytest tests/test_drop.py tests/test_drop_phases.py tests/test_app_io.py -q  # 75 passed
bash scripts/verify.sh python-static  # PASS
PYTHONPATH=src python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 compile
```
