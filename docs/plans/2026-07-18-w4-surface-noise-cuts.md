# W4 Surface Noise Cuts — Implementation Plan

> **For agentic workers:** Load `executing-plans`.

**Goal:** Remove non-core CLI/UI surface noise (W4 ADOPT + THIN A29/A32).  
**Spec:** W4 packing in compounding principles  
**Depends on:** W3 merged

### Cut

A9 autonomy-*, A11 report-subgraph, A12 vault-queue-drain, A15 llm/backend-telemetry, A18 cache CLI, A20 today-snooze, A21 batch-review/review-next, A22 metrics top-level (or demote), A23 dashboard, A24 search, A26 sync-evidence-graph, A27 ingest, A28 top-level drop-* dual register, A30 workbench/packs consoles, A31 execution HTML centers, A33b auto-once, A39 agents derived pages, C51 compat noise, C53 doc/UI residue; THIN A29 layout→new-vault, A32 Advanced drawer

### KEEP primary

drop (unified), today, advanced (thin), watch, compile, lint, ask*, file-back, review-page, alchemy-*, trace, llm-check, shell-status, new-vault, sync-product-shell

---

## Task 1: Delete W4 CLI commands + legacy dual drop

**Depends on:** none

- [ ] Remove listed parsers/dispatch/legacy_argv; keep unified `drop`
- [ ] **Verify:** `bash scripts/verify.sh python-static cli-smoke`

**Commit:** `feat(cut): remove W4 non-core CLI surfaces`

---

## Task 2: Shell Advanced thin + remove dead UI entries

**Depends on:** Task 1

- [ ] Thin Advanced drawer; remove buttons for deleted commands; rebuild main.js
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`

**Commit:** `fix(shell): thin Advanced; drop dead command UI`

---

## Task 3: Stop agents/packs/execution-center HTML generation noise + docs

**Depends on:** Task 1

- [ ] No-op or delete generators for agents pages / excess control HTML if safe
- [ ] Active docs C51/C53; PROGRESS; `bash scripts/verify.sh all`
- [ ] **Verify:** all PASS

**Commit:** `feat(cut)+docs: W4 surface noise`

---

## Final verify

`bash scripts/verify.sh all`
