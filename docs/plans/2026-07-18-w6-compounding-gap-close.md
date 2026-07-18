# W6 Compounding Gap Close — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task. Checkboxes track progress.

**Goal:** Close cross-review gaps so compounding loop works on default ask path, ADOPT LLM side-doors are locked, and Shell/Today match knowledge-compounding UX (not AgentOS residue).  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` (P2–P8, A19/A21/B47 ADOPT, B48/B49 THIN residuals)  
**Architecture:** Fix query-cache contract for elixirs; strip LLM `run_compile`/`run_lint` from watch/nightly/drop-auto; delete Shell dead CLI hooks; narrow Today primary feed to reports + scarce compound_suggest.  
**Tech stack:** Python + Product Shell JS  
**Depends on:** W2–W5 merged to main  
**Worktree:** `.worktrees/feat-w6-gap-close` branch `feat/w6-compounding-gap-close`

---

## Files touched (expected)

| Area | Paths |
|------|--------|
| Cache | `src/aiwiki/app_cache.py`, callers of sync/load hash |
| LLM doors | `src/aiwiki/runner/workflows.py`, `runner/automation.py`, `cli/dispatch.py`, `cli/parsers.py` |
| Shell | `.obsidian/plugins/furnace-product-shell/src/**`, rebuild `main.js` |
| Today | `src/aiwiki/today_feed.py`, Shell `today_feed.js` / `render_today.js` |
| Docs/tests | acceptance W2 fixture, Active docs residue, `PROGRESS.md` |

---

## Task 1: Persist elixirs in query cache

**Depends on:** none

**Files:** `src/aiwiki/app_cache.py` (+ any load/rebuild helpers that rebuild memory from snapshot)

- [ ] Include `elixir_nodes` and `elixir_derived_from` (or equivalent edges) in `sync_query_cache` / `load_query_cache_snapshot`
- [ ] Include elixir assets in `query_cache_memory_hash` so elixir-only updates invalidate cache
- [ ] After load, `ranked_elixir_ids` must work without `--no-cache` when memory has settled elixirs
- [ ] Extend W2 acceptance (or add assertion path) that default ask path (no `--no-cache`) still ranks elixir + writes `used_refs` elixir path
- [ ] **Verify:** `bash scripts/verify.sh python-static acceptance`

**Commit:** `fix(cache): persist elixir nodes in query cache`

---

## Task 2: Lock LLM run-compile / run-lint side doors

**Depends on:** none

**Files:** `runner/workflows.py` (`run_nightly`), `runner/automation.py`, `cli/parsers.py`, `cli/dispatch.py` / `dispatch_helpers.py`

- [ ] `run-nightly` / `nightly`: deterministic compile+lint only; no `run_compile()` / `run_lint()` LLM calls; remove or no-op `--no-semantic-lint` semantic path (default off permanently)
- [ ] `watch --with-llm` and `drop … --auto --with-llm`: either remove flags or make them hard-fail / warn+ignore with deterministic-only behavior (prefer remove flags + zero alias)
- [ ] Keep deterministic `compile` / `lint` CLI; keep internal `run_compile`/`run_lint` modules only if still needed by acceptance helpers — do not expose via automation defaults
- [ ] Fix Active docs that still teach `run-compile` / LLM nightly as product path
- [ ] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cut): lock LLM compile/lint out of watch and nightly`

---

## Task 3: Shell dead links + Today feed narrow

**Depends on:** Task 2 (CLI flags stable)

**Files:** Product Shell `modal_specs.js`, `plugin.js`, `plugin_lifecycle.js`, `control_items.js`, `today_feed.js`, `render_today.js`, `render/cards.js`; `src/aiwiki/today_feed.py`; rebuild `main.js`

- [ ] Remove or Notice-stub Shell actions that call deleted CLIs: `apply-archive`, `review-rewrite`/`apply-rewrite`, `sync-evidence-graph`, and any remaining rewrite/archive/promote candidate hooks
- [ ] Remove `review-page --batch/--next` product UX from Today primary path (A21); keep single-page `review-page` for thin confirm/discard if needed
- [ ] Narrow Today primary buckets to: today's reports + `compound_suggest` (+ minimal escalated only if already required by acceptance — prefer drop governance backlog from primary)
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static python-static`

**Commit:** `fix(shell): drop dead CLI hooks; Today reports+suggest first`

---

## Task 4: Docs residue + verify all

**Depends on:** Task 1, Task 2, Task 3

**Files:** `docs/USER_GUIDE.md`, `docs/INSTALL.md`, `docs/Furnace Runtime Operations.md`, `docs/README.md`, `README.md` (P9 five-protocol residue if still present), `PROGRESS.md`, this plan checkboxes

- [ ] Sweep C53 / P9 doc residue selling deleted or multi-protocol surfaces
- [ ] Note W6 gap-close in `PROGRESS.md`
- [ ] `bash scripts/verify.sh all` PASS
- [ ] **Verify:** all green

**Commit:** `docs+test: W6 compounding gap close`

---

## Final verify

`bash scripts/verify.sh all`

## Success criteria

1. Default `run-ask` (cached) ranks settled elixir when present  
2. No product path runs LLM `run_compile`/`run_lint` via watch/nightly/drop-auto  
3. Shell does not invoke deleted governance CLIs; Today leads with reports + scarce suggest  
4. `verify.sh all` green  
