# W2 Compounding Rank + Suggest — Implementation Plan

> **For agentic workers:** Load `executing-plans`. Fresh implementer per task. Checkboxes track progress.

**Goal:** Ask default-ranks confirmed judgments + settled elixirs; write `used_refs`; scarce compound_suggest on Today/report with one-click file-back (judgment) / alchemy-start.  
**Spec:** `docs/specs/2026-07-18-knowledge-compounding-principles.md` P2–P7, W2  
**Architecture:** Extend machine-memory query + rank; provenance `used_refs`; suggest engine → shell-summary → Today CTA; Shell calls existing CLI.  
**Tech stack:** Python + Product Shell JS  
**Worktree:** `.worktrees/feat-compounding-w2` branch `feat/compounding-w2`  
**Depends on:** W1 merged to main

---

## Task 1: Index + query score for judgments/elixirs

**Depends on:** none

**Files:** `src/aiwiki/memory/builder.py`, `memory/graph.py` / `app_memory_query.py`, `judgment_assets.py` as needed

- [ ] Include **confirmed** judgment + **settled** elixir in term_index and/or query scoring; expose ranked judgment/elixir ids in machine_query payload
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(memory): rank confirmed judgments and settled elixirs`

---

## Task 2: Ask context + used_refs

**Depends on:** Task 1

**Files:** `execution/ask.py`, `runner/workflows_ask.py`, `app_queries.py` if needed

- [ ] Boost rank_sources/concepts from judgment/elixir hits; inject ranked judgment/elixir into run-ask prompt within budget
- [ ] Write `used_refs` frontmatter on ask + restore after LLM fill (like used_context_refs)
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(ask): used_refs and judgment/elixir context`

---

## Task 3: compound_suggest engine + shell-summary

**Depends on:** Task 2

**Files:** create `src/aiwiki/app_shell/compound_suggest.py` (or similar); `app_shell/summary.py`, `app_shell/surfaces.py`

- [ ] Scarce rules only (multi-turn same corpus / links confirmed judgment|elixir / conflict-or-extend); max few items; never every report
- [ ] Expose `compound_suggest` on shell-summary (or kind=compound-suggest in suggested_next_actions without maintenance filter)
- [ ] **Verify:** `bash scripts/verify.sh python-static`

**Commit:** `feat(shell): scarce compound_suggest in shell-summary`

---

## Task 4: Today + report card CTA + Shell CLI wrappers

**Depends on:** Task 3

**Files:** `today_feed.py`, Product Shell `today_feed.js`, `render_today.js`, `modal_specs.js`, `plugin.js`; rebuild `main.js`

- [ ] Surface compound_suggest in Today; report card CTA for 沉淀/凝丹
- [ ] Default file-back kind **judgment**; alchemy-start modal/action from report `corpus_id`
- [ ] **Verify:** `bash scripts/verify.sh product-shell-static`

**Commit:** `feat(shell): Today compound suggest CTAs`

---

## Task 5: Acceptance + docs + verify all

**Depends on:** Task 4

**Files:** new/extend acceptance fixture; `test_acceptance_loop.py`; Active docs/PROGRESS; plan checkboxes

- [ ] Assert used_refs / ranking presence when seeded; suggest scarce
- [ ] `bash scripts/verify.sh all` PASS
- [ ] **Verify:** all green

**Commit:** `test+docs: W2 compounding rank and suggest`

---

## Final verify

`bash scripts/verify.sh all`
