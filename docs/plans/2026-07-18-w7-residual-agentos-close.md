# W7 Residual AgentOS Close — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task.

**Goal:** Close remaining cross-review gaps after W6: cut nightly debt_autopilot LLM `run_compile`, purge dead CLI hints from shell-summary/suggested_next_actions, sweep Active docs residue.  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` (B47 ADOPT residual, B49 THIN, C53)  
**Depends on:** W6 merged (`0d65656`)  
**Worktree:** `.worktrees/feat-w7-residual-close` branch `feat/w7-residual-agentos-close`

---

## Task 1: Cut nightly → debt_autopilot → run_compile

**Depends on:** none

**Files:** `src/aiwiki/runner/workflows.py` (`run_nightly`), `src/aiwiki/agent_loop.py`, `src/aiwiki/debt_autopilot.py` as needed

- [x] Nightly path must not call `workflows.run_compile()` / LLM `run_lint()` via debt_autopilot content digestion
- [x] Prefer: inventory/preview only for debt on nightly; or force `apply=False` / disable content LLM digestion when invoked from `run_nightly`
- [x] Do not reintroduce watch/`--with-llm` side doors
- [x] Keep deterministic `compile_wiki` / `lint_wiki` on nightly
- [ ] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cut): disable debt_autopilot LLM compile on nightly`

---

## Task 2: Purge dead CLI hints from shell-summary surfaces

**Depends on:** none

**Files:** `src/aiwiki/app_shell/surfaces.py`, `summary.py` / helpers that emit `suggested_next_actions` or batch hints; thin persist if cheap

- [x] Remove suggested_next_actions / batch hints that invoke deleted CLIs: `apply-action`, `review-action`, `apply-archive`, `apply-rewrite`, planner dry-run apply, etc.
- [x] Keep live commands only: `file-back`, `alchemy-*`, single-page `review-page`, `compile`/`lint`/`ask` as appropriate
- [x] Prefer not emitting `review-page --batch/--all-pending` as product hints (A21 residual)
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `fix(shell): purge dead suggested_next_actions CLI hints`

---

## Task 3: Active docs C53 / P9 residue sweep + verify all

**Depends on:** Task 1, Task 2

**Files:** Active docs that still teach deleted CLIs or multi-protocol: `docs/Furnace Evolution Mechanics.md`, `docs/Furnace Elixir.md`, `docs/DEVELOPER.md` owner map, `docs/Furnace Product Shell.md` snooze residue, `docs/USER_GUIDE.md` review/file-back examples, `docs/Furnace Runtime Operations.md` nightly LLM table inconsistency; `PROGRESS.md`; this plan checkboxes

- [x] Sweep C53 / P9 / Evolution CLI tables that mark deleted commands as current
- [x] Align USER_GUIDE review examples with thin 待审/已确认/废弃; file-back default judgment
- [x] Note W7 in PROGRESS; checkboxes
- [x] `bash scripts/verify.sh all` PASS

**Commit:** `docs+test: W7 residual AgentOS close`

---

## Final verify

`bash scripts/verify.sh all`

## Success criteria

1. `run-nightly` cannot reach `run_compile()` via debt_autopilot under default autonomy  
2. `shell-summary` / suggested_next_actions contain no deleted-CLI command strings for product surfaces  
3. Active docs no longer market deleted AgentOS CLIs as current  
4. `verify.sh all` green  
