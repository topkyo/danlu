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

- Date: 2026-04-16
- Agent: Claude
- Task: Review Next / Batch Review Product Shell UX
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: not-run
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: no
- Notes: n/a

- Date: 2026-04-16
- Agent: Claude
- Task: Phase A compile invalidation + Product Shell onboarding
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: not-run
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: no
- Notes: Independent code-review agent review; initial medium finding on hardness reset was fixed before final pass.; auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass

- Date: 2026-04-16
- Agent: Claude
- Task: danlu workspace 中文导航 + HTML link safety
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: not-run
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: no
- Notes: n/a

- Date: 2026-04-16
- Agent: code-review agent
- Task: danlu research-only cleanup + folder labels
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: not-run
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: yes
- Notes: auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass

- Date: 2026-04-16
- Agent: Claude
- Task: Product Shell UI simplification
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: not-run
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: no
- Notes: Independent code-review agent used after same-context helper could not auto-capture a body file.; auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass
