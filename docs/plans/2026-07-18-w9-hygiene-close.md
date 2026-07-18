# W9 Hygiene Close — P9 + Dead Residuals

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task. **Delete or purge — no “leave for later” stubs.**

**Goal:** Close the last P9 PARTIAL and all non-material residuals called out after W8 GOAL_MET review.  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` P9 + C53  
**Depends on:** W8 merged (`8b001d9`)  
**Worktree:** `.worktrees/feat-w9-hygiene` branch `feat/w9-hygiene-close`

### Must close

| # | Residual | Action |
|---|----------|--------|
| H1 | Multi-protocol dicts/colors/hints (`content/memory.py`, `memory/graph.py`, Shell protocol labels) | Keep **general only** |
| H2 | Orphan `agent_loop.py` + `debt_autopilot.py` | **Delete**; rewrite acceptance helpers that call preview |
| H3 | Orphan `run_compile` / `run_lint` in `workflows.py` (only used by debt_autopilot) | **Delete** functions + exports; keep `run_ask*` / `run_nightly` |
| H4 | Dead execution-center renderers + furnace/wiki links teaching Execution Center | Delete unused renderers; strip links/marketing from furnace_center / views / packs / meta views |
| H5 | `today_snooze` persist/read paths; batch-helper ids named `batch-review-*` | Remove snooze from summary/feed; rename helper ids to live `review-queue` naming |
| H6 | Shell i18n zombie keys (Review/Execution Center, three-kind file-back, investing protocol labels as product surface) | Purge unused keys; rebuild main.js |
| H7 | Active docs / AGENTS.md / USER_GUIDE residue mentioning multi-protocol or AgentOS product paths | Sweep |
| H8 | `verify.sh all` + plan checkboxes | Green |

**Out of scope:** Archive docs under `docs/archive/**` (historical). Internal event names in old receipts (`run-compile` as log event) may remain as **read-only** parsers for historical JSONL.

---

## Task 1: Delete agent_loop + debt_autopilot; remove run_compile/run_lint

**Depends on:** none

**Files:** delete `src/aiwiki/agent_loop.py`, `src/aiwiki/debt_autopilot.py`; gut `runner/workflows.py` `run_compile`/`run_lint` + helpers; `runner/__init__.py`; `tests/acceptance/case_runner.py`

- [ ] No production or acceptance import of agent_loop / debt_autopilot
- [ ] Rewrite `_run_observe_setup` (or equivalent) without agent_loop preview — use only still-live deterministic helpers needed by fixtures
- [ ] Remove `run_compile` / `run_lint` definitions and re-exports
- [ ] **Verify:** `bash scripts/verify.sh python-static acceptance`

**Commit:** `chore: delete agent_loop debt_autopilot and orphan run_compile`

---

## Task 2: P9 general-only + execution-center surface purge

**Depends on:** none

**Files:** `content/memory.py`, `memory/graph.py`, `memory/execution_surfaces.py`, `render/furnace_center.py`, `render/views.py`, `render/packs.py`, `app_shell/meta.py`, `app_compile_ops.py` as needed

- [ ] Strip investing/research/product/ops patch hints, label maps, graph colors — general only (or generic fallback)
- [ ] Delete or stop exporting unused `render_execution_center*` if no writers call them; remove furnace/wiki links to execution-center
- [ ] `shell_capabilities.views` must not advertise execution-center as product surface
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `fix: P9 general-only; purge execution-center product surfaces`

---

## Task 3: Shell/summary hygiene + i18n + docs + verify all

**Depends on:** Task 1, Task 2

**Files:** `app_shell/summary.py`, `today_feed.py`, `dispatch_helpers.py`, Product Shell `constants.js` + tests + `main.js`; Active docs; `PROGRESS.md`; this plan

- [ ] Remove `today_snooze` from build/persist summary and today_feed filters
- [ ] Rename `batch-review-ready-actions` helper id away from batch-review naming
- [ ] Purge zombie i18n (Review/Execution Center open commands, three-kind file-back, unused multi-protocol product labels if only for deleted UI)
- [ ] Docs/AGENTS.md/USER_GUIDE: no multi-protocol product matrix; no AgentOS product nightly narrative
- [ ] `bash scripts/verify.sh all` PASS
- [ ] Gates:
  ```bash
  rg -n "agent_loop|debt_autopilot" src/aiwiki --glob '!**/archive/**'   # only acceptable if comments about deletion
  rg -n "def run_compile|def run_lint" src/aiwiki/runner/workflows.py   # empty
  rg -n "PROTOCOL_PATCH_HINTS|\"investing\":" src/aiwiki/content/memory.py   # empty or general-only
  ```

**Commit:** `docs+chore: W9 hygiene close`

---

## Final verify

`bash scripts/verify.sh all`

## Success criteria

1. No `agent_loop.py` / `debt_autopilot.py` files  
2. No `def run_compile` / `def run_lint` in workflows.py  
3. content/memory + graph have no multi-protocol product matrices  
4. No execution-center product links in furnace_center generation  
5. No today_snooze in thin shell-summary persist  
6. Shell constants purged of Review/Execution Center command i18n  
7. `verify.sh all` green  
8. KEEP compounding surfaces still work (ask, file-back, alchemy, compound_suggest, drop auto)  
