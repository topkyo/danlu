# W3 Governance Side-Cuts — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task.

**Goal:** Delete AgentOS governance side-paths per spec W3 ADOPT list; keep alchemy min chain, watch, lint, ask, file-back, review-page, trace.  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` W3 packing  
**Worktree:** `.worktrees/feat-compounding-w3` after W2 merges (or stacked on `feat/compounding-w2` if still open — prefer merge W2 first)  
**Depends on:** W2 merged (or sequential same epic branch)

### ADOPT cut list (must remove CLI + dead modules; zero alias)

A3 alchemy **膨胀** (keep start/distill/finalize/promote/revert/demote), A4 L3, A5 rewrite chain, A6 concept retire/reactivate/review-concept, A7 repair actions, A8 archive, A10 promote/demote candidates, A16 signals/planner-log ops, A17 audit-preview/backfill, A19 run-lint, A34 nightly auto L2/L3/adopt (thin nightly to compile+lint), A37 derived packs auto, B42 aging auto proposals, B43 planner/dry-run/bundles, B47 run-compile

### KEEP

alchemy-start/distill/finalize/promote(+revert/demote), watch, compile, lint, ask/run-ask*, file-back, review-page, trace, llm-check

---

## Task 1: Cut L3 + rewrite + repair + archive + promote/demote CLI

**Depends on:** none

- [x] Remove parsers/dispatch/legacy for: l3-*, apply/revert (L3), review-rewrite/apply-rewrite/verify-rewrite/revert-rewrite, retire/reactivate/review-concept, review-action/apply-action/auto-resolve/revert-action, apply-archive/revert-archive, promote/demote
- [x] Delete or gut owner modules only if unused after CLI removal; fix imports
- [x] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cut): remove L3 rewrite repair archive promote CLI`

---

## Task 2: Cut alchemy AgentOS expansion; thin nightly; cut run-compile/run-lint

**Depends on:** Task 1

- [x] Remove `alchemy` dry-run/lane/judge/propose/auto expansion CLI; keep primitive alchemy-* commands
- [x] Nightly: remove auto L2/L3/judgment adopt; keep deterministic compile+lint path
- [x] Remove `run-compile`, `run-lint` CLI (keep `compile`, `lint`)
- [x] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cut): slim alchemy nightly; drop run-compile/run-lint`

---

## Task 3: Cut signals/planner-log/audit ops + packs + aging proposals + planner bundles

**Depends on:** Task 1

- [x] Remove signals-list/show/replay, planner-log-*, audit-preview/backfill CLI and unused modules
- [x] Stop derived packs / auto aging proposal generation where cheap; delete dead render paths
- [x] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(cut): remove signals planner audit and pack factories`

---

## Task 4: Fixtures, Shell refs, docs, verify all

**Depends on:** Task 2, Task 3

- [x] Fix acceptance/Shell that call deleted commands
- [x] Active docs + PROGRESS; `bash scripts/verify.sh all`
- [x] **Verify:** all PASS

**Commit:** `test+docs: W3 governance side-cuts`

---

## Final verify

`bash scripts/verify.sh all`
