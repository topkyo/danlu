# QA Review

Independent reviewer perspective on change risks.

## Preferred Execution

- Preferred: isolated reviewer context
  - sub-agent
  - peer agent
  - fresh session with only contract, diff, and touched-file context
- Fallback: same-context self-review only when isolation is unavailable or calibration has deliberately downgraded review independence
- If fallback is used, write `reviewer_fallback_reason` in the artifact

## Required Check Categories
1. Behavior changes
2. Cross-file consistency
3. Dead code / half-removed state
4. Missing exclusions
5. Config duplication
6. Contract consistency

## Output
Write gate artifact to `.codex/gates/qa-review.md` with status, checked_at, contract_sha, worktree_fingerprint, findings.
Prefer generating the header via `HARNESS_DIR=.codex bash scripts/write_gate_artifact.sh ...`, then append findings below it.

Required when `status: pass`:
- `reviewer_mode`: `isolated-agent | external-agent | fresh-session | same-context | human`
- If `reviewer_mode: same-context`, `reviewer_fallback_reason`

Recommended extra headers:
- `reviewer_identity`: tool / model / session name
- `reviewer_scope`: `contract+diff+touched-files | full-repo | custom`

## Calibration
After each run, append to `CALIBRATION.md`, including reviewer mode.
