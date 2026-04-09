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
- `scripts/resolve_review_mode.sh` can resolve this mode from `.claude/review-capabilities.env`; it chooses a reviewer mode, it does not schedule the reviewer for you
- `scripts/launch_qa_review.sh` is the minimal execution bridge for this decision: it writes a handoff file and can call a configured `REVIEW_LAUNCH_COMMAND_*`
- The bundled Claude capability template ships an opt-in `fresh-session` preset using `claude -p`; enable `REVIEW_CAPABILITY_FRESH_SESSION=yes` only when you want to use it
- `scripts/run_qa_review.sh` is the recommended end-to-end helper when you want one command for launch + output capture + artifact write, and it can append calibration too
- For non-pass review runs, `scripts/run_qa_review.sh --append-calibration` can conservatively infer `qa-review Hit` from explicit findings in the captured review output when you omit `--qa-review-hit`
- That same helper also auto-records `review_findings_count`; clean passing artifacts keep that count at `0`, and `review_findings_highest_severity` is only retained on non-pass or optional artifacts that still record findings
- It records `review_findings_highest_severity` when the review output contains explicit markers such as `[high]` or `Severity: medium`

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
For project-local automatic mode selection, prefer `bash scripts/write_gate_artifact.sh qa-review ... --resolve-reviewer-mode`.
If the project configured launcher hooks in `.claude/review-capabilities.env`, prefer `bash scripts/launch_qa_review.sh --task "<task>"` before writing the final artifact.
For the shortest path, prefer `bash scripts/run_qa_review.sh --task "<task>" --status auto --append-calibration --contract-scope-changed no --new-session yes --progress-read no`.
Required when `status: pass`:
- `reviewer_mode`: `isolated-agent | external-agent | fresh-session | same-context | human`
- If `reviewer_mode: same-context`, `reviewer_fallback_reason`
- If `review_findings_count` is present, it must be `0`
- `review_findings_highest_severity` must be omitted

Recommended extra headers:
- `reviewer_identity`: tool / model / session name
- `reviewer_scope`: `contract+diff+touched-files | full-repo | custom`
If no findings: list checked categories and state `no findings`.

## Calibration

After each run, append to `CALIBRATION.md`: date, task, reviewer mode, hits, misses, false positives.
Prefer `bash scripts/write_calibration_entry.sh --from-current-gates --task "<task>" ...` so reviewer mode is imported from the current gate artifact and the log stays machine-readable for downgrade recommendations.
If you are already writing the final gate artifact for the round, `bash scripts/write_gate_artifact.sh ... --append-calibration --calibration-task "<task>" ...` can do both in one command.
For passing artifacts, omitting the current gate's hit/miss/false-positive counters now records a visible `0/0/0` default plus a note, so the log does not silently hide the assumption.
For non-pass runs through `bash scripts/run_qa_review.sh --append-calibration`, omitting `--qa-review-hit` lets the helper infer a conservative hit count from explicit findings in the review output and record that assumption in `Notes`.
