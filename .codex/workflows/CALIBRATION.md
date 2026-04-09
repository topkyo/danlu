# Codex QA Calibration Log

Records qa-review and qa-runtime hit/miss/false-positive for Codex runs.
Used to drive scaffolding degradation triggers.
Each qa-review / qa-runtime run must append one entry.
Prefer appending via `HARNESS_DIR=.codex bash scripts/write_calibration_entry.sh --from-current-gates ...` after gate artifacts are up to date.
Review current recommendations via `HARNESS_DIR=.codex bash scripts/calibration_report.sh`.
For automation, use `HARNESS_DIR=.codex bash scripts/calibration_report.sh --json`.
To review what those recommendations would change, use `HARNESS_DIR=.codex bash scripts/apply_calibration_recommendation.sh --dry-run`.
To auto-apply the current safe subset, use `HARNESS_DIR=.codex bash scripts/apply_calibration_recommendation.sh --apply` (currently only the active contract `qa-review` requirement plus its adjacent structured `calibration_note` payload).

qa-review downgrade heuristic:
- Lite: 2 consecutive zero-hit rounds
- Standard: 3 consecutive zero-hit rounds
- Strict: 3 consecutive zero-hit rounds

## Template

- Date:
- Agent: Codex
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

- Date: 2026-04-09
- Agent: Codex
- Task: concept lifecycle runtime extension
- qa-review Mode: same-context
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: scripted
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: no
- PROGRESS Read: yes
- Notes: captured after gate refresh and closed_loop pass

- Date: 2026-04-09
- Agent: Codex
- Task: concept lifecycle override retire/reactivate
- qa-review Mode: same-context
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: scripted
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: no
- PROGRESS Read: yes
- Notes: captured after concept lifecycle override closed_loop pass
