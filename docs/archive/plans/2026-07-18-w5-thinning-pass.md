# W5 Thinning Pass — Implementation Plan

> **For agentic workers:** Load `executing-plans`.

**Goal:** Thin review states, file-back defaults, Shell views, shell-summary, LLM backend product lock, graph/index excess (W5 THIN).  
**Spec:** W5 packing  
**Depends on:** W4 merged

### THIN

B41 review → 待审/已确认/废弃, B44 product-lock single LLM default (don't delete all backends), B46 file-back default judgment only, B48 Shell views → Today-first, B49 shrink shell-summary, A36 thin graph/index factory

---

## Task 1: Review status thin + file-back default judgment

**Depends on:** none

- [x] Collapse review transitions to minimal set; default file-back kind judgment in CLI+Shell
- [x] **Verify:** `bash scripts/verify.sh python-static product-shell-static`

**Commit:** `feat(review): thin statuses; default file-back judgment`

---

## Task 2: Shell Today-first + shrink shell-summary

**Depends on:** Task 1

- [x] Deprioritize/hide Review/Execution/Runs as primary; shrink summary fields to Today/reports/compound_suggest needs
- [x] Rebuild main.js
- [x] **Verify:** `bash scripts/verify.sh product-shell-static python-static`

**Commit:** `feat(shell): Today-first; shrink shell-summary`

---

## Task 3: Thin graph/index factory + LLM product default docs + verify all

**Depends on:** Task 2

- [x] Reduce index/graph HTML spam; document single default backend; `bash scripts/verify.sh all`
- [x] PROGRESS W2–W5 complete note
- [x] **Verify:** all PASS

**Commit:** `docs+thin: W5 compounding thinning pass`

---

## Final verify

`bash scripts/verify.sh all`
