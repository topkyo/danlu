---
name: agentstack-finish
description: Use at the end of a coding task to summarize changes, verification, review, risks, and follow-ups.
---

# AgentStack Finish

Use this when implementation is complete.

Required final summary:

- Changes.
- Verification command and result.
- Risk level.
- Context evidence status when required.
- Review status.
- Independent pre-submit review status when the pre-submit gate is enabled.
- Iteration evidence status when a retry was recorded.
- Runtime evidence status when required.
- Risks.
- Follow-ups.

For high-risk tasks or when the user asks for artifacts, run:

```bash
scripts/agentstack-finish
```

Closure minimums:

- L0/L1: verify when available, then finish.
- L2/L3: context evidence, structural preflight, review, verify, and finish.
- L4: add real runtime evidence.
- L5: stop for confirmation and record blocked evidence.

Independent pre-submit review evidence should be recorded as `scripts/agentstack review --id independent --reviewer independent --handoff PATH --result pass|needs-fix|blocked`; finish accepts same-run `review.md` or `review-*.md`. For pre-submit gates, run finish with `--pre-submit-review-required`. Repair attempts may be recorded as `scripts/agentstack iteration ...`; finish lists same-run `iteration-*.md`.
