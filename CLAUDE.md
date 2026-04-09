# CLAUDE.md

## Scope

- This repository implements `aiwiki`, the local-first runtime / CLI behind 炼丹炉.
- 炼丹炉 is the product/system name; `aiwiki` is the runtime, command name, and repository name.
- `open-harness` provides the engineering loop and gate scaffolding around the project.
- Dynamic task state lives in `PROGRESS.md`.
- Current scope, acceptance criteria, and gate requirements live in `.codex/contracts/active.md`.

## Project Summary

- `aiwiki` compiles raw sources into structured wiki artifacts, machine memory, judgment assets, and reviewable execution outputs.

## Current Direction

- Maintain the five-layer furnace runtime: `raw / wiki / machine memory / schema / outputs`.
- Keep the deterministic baseline plus multi-backend execution (`codex-cli`, `claude-cli`, `openai-api`).
- Keep direct material drop entry points for URLs, PDFs, images, and repositories.
- Maintain protocol-aware runtime behavior for `general / investing / research / product / ops`.
- Maintain the governance and execution layers: `review / aging / escalation / repair / nightly / apply / revert / audit`.

## Source Of Truth

- Product and operator overview: `README.md`
- Current sprint scope: `.codex/contracts/active.md`
- Task state: `PROGRESS.md`
- Local verification entry point: `bash scripts/verify.sh`
- Runtime validation: fixture-driven tests in `tests/`
- Deploy entry point: none

## Stable Constraints

- Python 3.10+, stdlib-first, file-based state
- Runtime model: `single writer, many readers`
- `raw/` is the only fact input layer
- `wiki/sources/` and `wiki/derived/` stay separate
- Derived outputs never overwrite source pages
- Judgment and execution artifacts must remain auditable, reversible, and provenance-aware
- No hosted service, multi-user sync, heavy RAG infrastructure, or fine-tuning

## Working Rules

- Prefer concrete, reversible local changes
- Keep provenance explicit in generated artifacts
- Record any same-context review fallback in the gate artifact
- User-level service wiring is allowed when it stays within the current user's session scope
- Use “炼丹炉” for the product/system and `aiwiki` only for repo/runtime/CLI contexts
