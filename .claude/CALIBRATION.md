# Claude QA Calibration Log

Records qa-review and qa-runtime hit/miss/false-positive for Claude runs.
Used to drive scaffolding degradation triggers.
Each qa-review / qa-runtime run must append one entry.

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
- Checklist Change:
