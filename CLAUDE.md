# CLAUDE.md

## Scope

- This repository implements `aiwiki`, a local-first knowledge compiler MVP.
- `open-harness` provides the engineering loop and gate scaffolding around the project.
- Dynamic task state lives in `PROGRESS.md`.
- Current scope, acceptance criteria, and gate requirements live in `.codex/contracts/active.md`.

## Project Summary

- `aiwiki` turns raw sources into structured markdown wiki artifacts and reviewable output bundles.

## Current Direction

- Build the MVP CLI around `ingest`, `compile`, `ask`, `file-back`, and `lint`.
- Add a multi-backend execution layer (`codex-cli`, `claude-cli`, `openai-api`) without removing the deterministic baseline.
- Add direct material drop entry points for URLs, PDFs, images, and repositories.
- Preserve the `raw/ -> wiki/ -> output/` layering and provenance rules.

## Source Of Truth

- Product and operator overview: `README.md`
- Current sprint scope: `.codex/contracts/active.md`
- Task state: `PROGRESS.md`
- Local verification entry point: `bash scripts/verify.sh`
- Runtime validation: fixture-driven tests in `tests/`
- Deploy entry point: none

## Stable Constraints

- Python 3.10+, stdlib-first, file-based state
- `raw/` is the only fact input layer
- `wiki/sources/` and `wiki/derived/` stay separate
- Derived outputs never overwrite source pages
- No vector database, hosted service, OCR, or fine-tuning in the MVP

## Working Rules

- Prefer concrete, reversible local changes
- Keep provenance explicit in generated artifacts
- Record any same-context review fallback in the gate artifact
- User-level service wiring is allowed when it stays within the current user's session scope
