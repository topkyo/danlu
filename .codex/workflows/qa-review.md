# QA Review

Independent reviewer perspective on change risks.

## Preferred Execution

- Preferred: isolated reviewer context
  - sub-agent
  - peer agent
  - fresh session with only contract, diff, and touched-file context
- Fallback: same-context self-review only when isolation is unavailable or calibration has deliberately downgraded review independence
- If fallback is used, write `reviewer_fallback_reason` in the artifact
- `scripts/resolve_review_mode.sh` can resolve this mode from `.codex/review-capabilities.env`; it chooses a reviewer mode, it does not schedule the reviewer for you
- `scripts/launch_qa_review.sh` is the minimal execution bridge for this decision: it writes a handoff file and can call a configured `REVIEW_LAUNCH_COMMAND_*`
- The bundled Codex capability template ships an opt-in `fresh-session` preset that uses `codex review --uncommitted`; enable `REVIEW_CAPABILITY_FRESH_SESSION=yes` only when you want to use it
- `scripts/run_qa_review.sh` is the recommended end-to-end helper when you want one command for launch + output capture + artifact write, and it can append calibration too
- For non-pass review runs, `scripts/run_qa_review.sh --append-calibration` can conservatively infer `qa-review Hit` from explicit findings in the captured review output when you omit `--qa-review-hit`
- That same helper also auto-records `review_findings_count`; clean passing artifacts keep that count at `0`, and `review_findings_highest_severity` is only retained on non-pass or optional artifacts that still record findings
- It records `review_findings_highest_severity` when the review output contains explicit markers such as `[high]` or `Severity: medium`

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
For project-local automatic mode selection, prefer `--resolve-reviewer-mode` over hard-coding `--reviewer-mode`.
If the project configured launcher hooks in `.codex/review-capabilities.env`, prefer `HARNESS_DIR=.codex bash scripts/launch_qa_review.sh --task "<task>"` before writing the final artifact.
For the shortest path, prefer `HARNESS_DIR=.codex bash scripts/run_qa_review.sh --task "<task>" --status auto --append-calibration --contract-scope-changed no --new-session yes --progress-read no`.

Required when `status: pass`:
- `reviewer_mode`: `isolated-agent | external-agent | fresh-session | same-context | human`
- If `reviewer_mode: same-context`, `reviewer_fallback_reason`
- If `review_findings_count` is present, it must be `0`
- `review_findings_highest_severity` must be omitted

Recommended extra headers:
- `reviewer_identity`: tool / model / session name
- `reviewer_scope`: `contract+diff+touched-files | full-repo | custom`

## Calibration
After each run, append to `CALIBRATION.md`, including reviewer mode.
Prefer:

```bash
HARNESS_DIR=.codex bash scripts/write_calibration_entry.sh --from-current-gates --task "<task>" --qa-review-hit 0 --qa-review-miss 0 --qa-review-false-positive 0 --contract-scope-changed no --new-session yes --progress-read no
```

If you are already writing the final gate artifact for the round, you can collapse that into:

```bash
HARNESS_DIR=.codex bash scripts/write_gate_artifact.sh qa-review --status pass --summary "no findings" --resolve-reviewer-mode --append-calibration --calibration-task "<task>" --contract-scope-changed no --new-session yes --progress-read no
```

If you omit the current gate's hit/miss/false-positive counters on a passing artifact, the helper records a visible `0/0/0` default and explains that default in `Notes`.
For non-pass runs through `scripts/run_qa_review.sh --append-calibration`, omitting `--qa-review-hit` lets the helper infer a conservative hit count from explicit findings in the review output and record that assumption in `Notes`.
