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

- Date: 2026-04-09
- Agent: Codex
- Task: lifecycle-driven governance indexes
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
- Notes: captured after governance index closed_loop pass

- Date: 2026-04-09
- Agent: Codex
- Task: open-harness upgrade sync
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
- PROGRESS Read: no
- Notes: captured after upgrading ai-wiki to latest local /home/tim/open-harness scaffold

- Date: 2026-04-09
- Agent: Codex
- Task: domain-pilots protocol relevance calibration
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
- Notes: captured after verify, push, and gate refresh

- Date: 2026-04-09
- Agent: Codex
- Task: domain-pilots ambiguity explicitization
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
- Notes: captured after ambiguity explicitization verify and gate refresh

- Date: 2026-04-14
- Agent: Codex
- Task: judgment/governance/product shell convergence
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: scripted
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: no
- Notes: auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass

- Date: 2026-04-14
- Agent: Codex
- Task: judgment/governance/product shell convergence
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: scripted
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: no
- PROGRESS Read: no
- Notes: auto-defaulted qa-runtime hit/miss/false-positive to 0 from write_gate_artifact pass

- Date: 2026-04-15
- Agent: Codex
- Task: Phase 5/6 closure
- qa-review Mode: isolated-agent
- qa-review Hit: 0
- qa-review Miss: 0
- qa-review False Positive: 0
- qa-runtime Mode: scripted
- qa-runtime Hit: 0
- qa-runtime Miss: 0
- qa-runtime False Positive: 0
- Contract Scope Changed: no
- New Session: yes
- PROGRESS Read: yes
- Notes: auto-defaulted qa-review hit/miss/false-positive to 0 from write_gate_artifact pass

- Date: 2026-04-15
- Agent: Codex
- Task: Phase 5/6 closure
- qa-review Mode: isolated-agent
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
- Notes: auto-defaulted qa-runtime hit/miss/false-positive to 0 from write_gate_artifact pass
