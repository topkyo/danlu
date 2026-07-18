# W8 Final AgentOS Residual Close — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task. **Do not leave half-cuts** — each task’s Done means the named surface is gone or live-only, with verify green.

**Goal:** Finish every remaining cross-review gap so knowledge-compounding goals are **GOAL_MET** on main chain **and** AgentOS residuals that violate ADOPT/THIN are **CUT_DONE** (not stubbed half-measures).  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md`  
**Depends on:** W7 merged (`4ebac9e`)  
**Worktree:** `.worktrees/feat-w8-final-close` branch `feat/w8-final-agentos-close`

### In-scope residuals (must all close)

| # | Gap | Target |
|---|-----|--------|
| R1 | `run-nightly` still runs agent_loop / signal_pipeline | Nightly = **only** deterministic `compile_wiki` + `lint_wiki` + health write |
| R2 | `shell_capabilities` lists deleted CLIs | Capabilities = **live commands only** |
| R3 | Generated surfaces / operator helpers emit dead CLI strings | Purge `apply-action` / `apply-rewrite` / `run-compile` / `review-action` / `protocol-set` teaching from product-facing generators |
| R4 | P8 投料即煅烧非默认 | Successful `drop` **defaults to** deterministic auto-process (compile+lint); keep `watch` for continuous external drops |
| R5 | A21 `review-page --batch/--next/--all-pending` | **Remove** these flags + batch helpers from CLI/Shell |
| R6 | B46 file-back three kinds | Product `file-back` **judgment only** (remove derived/decision CLI+Shell choices) |
| R7 | B48/B49 thick Shell/summary | Remove Review/Execution/Runs as registered primary views; shrink persist contract to compounding fields |
| R8 | Docs + acceptance + verify all | Align Active docs; fix fixtures; `verify.sh all` PASS |

**Out of scope:** deleting entire internal `debt_autopilot` / `agent_loop` / `run_compile` **modules** (may remain for tests/history) as long as **zero product/nightly/drop/watch path** reaches them. Prefer delete call sites over leaving “preview still runs AgentOS”.

---

## Task 1: Nightly = compile + lint only

**Depends on:** none

**Files:** `src/aiwiki/runner/workflows.py` (`run_nightly`), callers/docs of agent_loop on nightly; acceptance fixtures that expect agent_loop on nightly

- [x] `run_nightly` / `nightly` CLI path: **remove** `run_nightly_agent_loop`, `run_signal_pipeline`, and any alchemy auto/lane apply from this path
- [x] Remove or no-op `promote_recurring_outputs` from nightly if it enqueues AgentOS candidates (prefer remove from nightly)
- [x] Keep: `compile_wiki`, `lint_wiki`, `write_nightly_health` (deterministic fields only)
- [x] Update acceptance that assumed signals/planner on nightly
- [x] **Verify:** `bash scripts/verify.sh python-static cli-smoke acceptance`

**Commit:** `feat(cut): nightly is deterministic compile+lint only`

---

## Task 2: Live-only capabilities + purge generated dead CLI strings

**Depends on:** none

**Files:** `app_shell/meta.py`, `app_shell/controls.py`, `app_shell/helpers.py`, `cli/dispatch_helpers.py`, `content`/`compile`/`render` generators that emit `apply-*` / `run-compile` / `protocol-set`, `memory/execution_surfaces.py`, `render/furnace_center.py` as needed

- [x] `shell_capabilities()` lists only commands that exist in parsers today
- [x] No product-facing generator writes `apply-action`, `review-action`, `apply-archive`, `apply-rewrite`, `review-rewrite`, `run-compile`, `run-lint`, `signals-*`, `protocol-set` as runnable commands
- [x] Operator `review-queue` JSON must not recommend deleted CLIs
- [x] **Verify:** `bash scripts/verify.sh python-static` + `rg` gate: zero matches of those tokens as command strings in `app_shell/` and `dispatch_helpers.py` (except dead-token filter lists / comments)

**Commit:** `fix(shell): live-only capabilities; purge dead CLI generators`

---

## Task 3: P8 drop defaults to auto-process + A21/B46 product cuts

**Depends on:** Task 1 (nightly semantics stable)

**Files:** `cli/parsers.py`, `cli/dispatch.py` / `dispatch_helpers.py`, `execution` file-back, Product Shell modal_specs/plugin for file-back & review-page batch

- [x] After successful `drop`, **default** run deterministic `auto_process_once` (compile+lint). Opt-out only if needed (`--no-auto`); remove confusing dual semantics
- [x] Delete `review-page` `--batch` / `--next` / `--all-pending` from parsers/dispatch/helpers; Shell batch/next stubs → gone (not Notice half-life if unused)
- [x] `file-back` accepts **only** `--kind judgment` (or drop `--kind` and hardcode judgment); remove derived/decision from CLI help and Shell modal
- [x] **Verify:** `bash scripts/verify.sh python-static cli-smoke product-shell-static`

**Commit:** `feat(product): drop auto-compile; judgment-only file-back; no review batch`

---

## Task 4: B48/B49 Today-only Shell contract

**Depends on:** Task 2

**Files:** Product Shell view registration / plugin_lifecycle / constants; `app_shell/summary.py` thin persist; rebuild `main.js`

- [x] Unregister or permanently hide Review Center / Execution Center / Recent Runs views (no command-palette resurrection of AgentOS centers)
- [x] Persist `shell-summary.json` only compounding fields: status/sync health, today/reports, `compound_suggest`, `suggested_next_actions` (live-only), minimal llm_health if required by Shell — drop planner/execution_controls/dashboard/agent_loop/rewrite_followup from **persist**
- [x] **Verify:** `bash scripts/verify.sh product-shell-static python-static`

**Commit:** `feat(shell): Today-only views; minimal shell-summary persist`

---

## Task 5: Docs + acceptance + verify all + residual rg gate

**Depends on:** Task 1–4

**Files:** Active docs, `PROGRESS.md`, this plan, acceptance fixtures, `docs/README.md`

- [x] Docs: nightly = compile+lint only; drop auto-compiles; file-back judgment-only; no batch review; no AgentOS capabilities marketing
- [x] Acceptance updated; `bash scripts/verify.sh all` PASS
- [x] Final residual gate (must be empty for product paths):
  ```bash
  # live parsers must not register deleted names
  rg -n "add_parser\\(\"(run-compile|run-lint|apply-action|protocol-set)" src/aiwiki/cli/parsers.py
  # nightly must not call agent_loop
  rg -n "run_nightly_agent_loop|run_signal_pipeline" src/aiwiki/runner/workflows.py
  ```
- [x] Check off all plan checkboxes

**Commit:** `docs+test: W8 final AgentOS residual close`

---

## Final verify

`bash scripts/verify.sh all`

## Success criteria (all required — no “mostly”)

1. `run_nightly` source contains **no** `run_nightly_agent_loop` / `run_signal_pipeline` calls  
2. `shell_capabilities` contains **no** deleted CLI names  
3. `drop` without flags triggers deterministic compile+lint  
4. `file-back --kind derived|decision` fails or is removed; judgment works  
5. `review-page --batch|--next|--all-pending` fails  
6. Shell has no Review/Execution/Runs view registration for product use  
7. `verify.sh all` green  
8. Cross-check: Keep alchemy min chain / watch / ask / trace / ranking / compound_suggest still work  
