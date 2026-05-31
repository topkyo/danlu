---
name: finish
description: AgentStack finish flow for coding task closure.
---

# Finish

Summarize changes, risk level, verification, context/review status, independent pre-submit review status when the pre-submit gate is enabled, iteration evidence when present, runtime evidence status when required, risks, and follow-ups. Use `scripts/agentstack-finish` when artifact evidence is useful.

Closure minimums:

- L0/L1: verify when available, then finish.
- L2/L3: context evidence, structural preflight, review, verify, and finish.
- L4: add real runtime evidence.
- L5: stop for confirmation and record blocked evidence.

Independent pre-submit reviewer output should be recorded with `scripts/agentstack review --id independent --reviewer independent --handoff PATH --result pass|needs-fix|blocked`; same-run `review-*.md` and `iteration-*.md` are collected by finish. For pre-submit gates, run finish with `--pre-submit-review-required`.
