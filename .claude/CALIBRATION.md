# Claude QA Calibration Log

Records qa-review and qa-runtime hit/miss/false-positive for Claude runs.
Used to drive scaffolding degradation triggers.
Each qa-review / qa-runtime run must append one entry.
Prefer appending via `bash scripts/write_calibration_entry.sh --from-current-gates ...` after gate artifacts are up to date.
Review current recommendations via `bash scripts/calibration_report.sh`.
For automation, use `bash scripts/calibration_report.sh --json`.
To review what those recommendations would change, use `bash scripts/apply_calibration_recommendation.sh --dry-run`.
To auto-apply the current safe subset, use `bash scripts/apply_calibration_recommendation.sh --apply` (currently only the active contract `qa-review` requirement plus its adjacent structured `calibration_note` payload).

qa-review downgrade heuristic:
- Lite: 2 consecutive zero-hit rounds
- Standard: 3 consecutive zero-hit rounds
- Strict: 3 consecutive zero-hit rounds

## Template

- Date:
- Agent: Claude
- Task:
- qa-review Mode:
- qa-review Hit:
- qa-review Miss:
- qa-review False Positive:
- qa-runtime Mode:
- qa-runtime Hit:
- qa-runtime Miss:
- qa-runtime False Positive:
- Contract Scope Changed:
- New Session:
- PROGRESS Read:
- Notes:
