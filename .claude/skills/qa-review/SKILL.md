---
name: qa-review
description: Independent skeptical review. Checks diff and context consistency.
---

# QA Review

Review from an independent reviewer perspective, not restating implementation intent.

## Preferred Execution

- Preferred: isolated reviewer context
  - sub-agent
  - peer agent
  - fresh session with only contract, diff, and touched-file context
- Fallback: same-context self-review only when isolation is unavailable or calibration has deliberately downgraded review independence
- If fallback is used, write `reviewer_fallback_reason` in the artifact

## Required Check Categories

1. **Behavior changes**: Does new logic unintentionally change existing behavior?
2. **Cross-file consistency**: Do docs, configs, and code still agree?
3. **Dead code**: Old branches, fields, commands only partially removed?
4. **Missing exclusions**: Deploy / sync / ignore files that could be accidentally deleted?
5. **Config duplication**: Same value defined in multiple places and drifting?
6. **Contract consistency**: Does implementation match the current contract?

## Output

Write gate artifact with: status, checked_at, contract_sha, worktree_fingerprint, findings.
Prefer generating the header via `bash scripts/write_gate_artifact.sh ...`, then append findings below it.
Required when `status: pass`:
- `reviewer_mode`: `isolated-agent | external-agent | fresh-session | same-context | human`
- If `reviewer_mode: same-context`, `reviewer_fallback_reason`

Recommended extra headers:
- `reviewer_identity`: tool / model / session name
- `reviewer_scope`: `contract+diff+touched-files | full-repo | custom`
If no findings: list checked categories and state `no findings`.

## Calibration

After each run, append to `CALIBRATION.md`: date, task, reviewer mode, hits, misses, false positives.
Prefer `bash scripts/write_calibration_entry.sh --from-current-gates --task "<task>" ...` so reviewer mode is imported from the current gate artifact and the log stays machine-readable for downgrade recommendations.
If you are already writing the final gate artifact for the round, `bash scripts/write_gate_artifact.sh ... --append-calibration --calibration-task "<task>" ...` can do both in one command.
For passing artifacts, omitting the current gate's hit/miss/false-positive counters now records a visible `0/0/0` default plus a note, so the log does not silently hide the assumption.
