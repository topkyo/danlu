# Furnace 90+ Context Provenance Hardening Plan

## Goal
- Raise the trust boundary of 炼丹炉 by fixing four hard edges: direct ask provenance, judgment auto-adopt transactions, critical state fail-closed reads, and nightly fallback env validation.
- Keep the system local-first and dependency-free: no vector DB, hosted service, hidden backend routing, or broad rewrite.
- Make 金丹/context reuse auditable: selected context must be visible in artifacts, run notes, LLM receipts, and execution receipts.

## Scope
- In:
  - `run-ask` direct note context provenance.
  - Gold-first context selection budget: elixirs, judgments/decisions, sources, concepts.
  - Judgment auto-adopt rollback on post-write audit/history failures.
  - Critical state fail-closed handling for protocol state and compile memory reads.
  - Nightly fallback env permission and owner validation.
- Out:
  - New CLI commands or user-facing concepts.
  - Vector retrieval, external search, hosted services, or expanded LLM context windows.
  - Changing backend/model defaults.

## Files
| File | Action | Reason |
| --- | --- | --- |
| `src/aiwiki/runner/workflows_ask.py` | Update | Persist direct ask selected context provenance. |
| `src/aiwiki/runner/auto_adopt.py` | Update | Roll back judgment review writes if authoritative audit/history append fails. |
| `src/aiwiki/app_protocol.py` | Update | Avoid silently normalizing corrupt protocol state. |
| `src/aiwiki/compile/context.py` | Update | Treat corrupt previous machine memory as explicit degraded state. |
| `scripts/run_nightly.sh` | Update | Fail closed on unsafe fallback env files. |
| `tests/` | Update | Cover provenance, rollback, fail-closed, and env hardening. |

## Tasks
- [x] Add structured `used_context_refs` to direct ask context selection.
- [x] Persist `used_context_refs` to artifact frontmatter, run notes, LLM receipts, and execution receipts.
- [x] Enforce deterministic context priority and budget: `wiki/elixirs` > `wiki/judgments|decisions` > `wiki/sources` > `wiki/concepts`.
- [x] Transactionalize judgment auto-adopt page/receipt/history/audit writes.
- [x] Fail closed on corrupt protocol/machine-memory state.
- [x] Validate nightly fallback env path, owner, type, and writable bits before `source`.
- [x] Add focused tests and run targeted verification.

## Verify
- Targeted:
  - `PYTHONPATH=src python -m pytest tests/test_runner.py -k 'direct_note_supplies_relevant_vault_context_to_llm or prefers_elixir_context or quoted_report_note_uses_report_as_llm_material_context'`
  - `PYTHONPATH=src python -m pytest tests/test_auto_adopt.py -k 'judgment_review_audit_failure'`
  - `PYTHONPATH=src python -m pytest tests/unit/test_protocol_runtime_schema.py tests/test_app_compile.py -k 'corrupt'`
  - `PYTHONPATH=src python -m pytest tests/test_app_runtime.py -k 'run_nightly_script_retries_nim_fallback_before_deterministic or rejects_group_writable_fallback_env or allows_deterministic_when_only_fallback_is_unconfigured'`
  - `bash -n scripts/run_nightly.sh`
  - `git diff --check`
- Project:
  - `scripts/agentstack verify --target auto`

## Risks
- Direct ask behavior is user-facing; preserve existing prompt text while adding provenance metadata.
- Critical state fail-closed may surface existing corrupt local state; this is intended for authoritative paths.
- Shell portability matters for nightly env validation; keep checks POSIX-ish and Linux-compatible.
