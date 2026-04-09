# Codex Harness

Codex harness artifact root for this project.

## Principles

- Guardrails always, scaffolding as needed
- Calibration-driven degradation
- Stage-scoped workflow loading
- Same gate scripts as Claude, different artifact root

### Guardrails
- `verify.sh` — deterministic static checks
- `qa-runtime` — empirical behavior verification (per contract)
- `deploy-gate` — boundary enforcement

### Scaffolding
- `contract` — prevent scope drift and capture lightweight context, approach, and plan
- `qa-review` — prevent generator bias, preferably with an isolated reviewer
- `PROGRESS.md` — prevent cross-session amnesia

## Directory

- `contracts/`: enhanced sprint contract template, optional ADR template, and active contract
- `gates/`: qa-review / qa-runtime gate artifacts
- `workflows/`: stage runbooks

## Entry Points

```bash
HARNESS_DIR=.codex bash scripts/closed_loop.sh
HARNESS_DIR=.codex bash scripts/closed_loop.sh --json
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --json
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --check-calibration-report
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --max-qa-review-findings 0
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --deny-qa-review-severity high
HARNESS_DIR=.codex bash scripts/write_calibration_entry.sh --from-current-gates --task "feature round" --contract-scope-changed no --new-session yes --progress-read no
HARNESS_DIR=.codex bash scripts/write_gate_artifact.sh qa-runtime --status pass --summary "runtime smoke passed" --runtime-mode scripted --append-calibration --calibration-task "feature round" --contract-scope-changed no --new-session yes --progress-read no
HARNESS_DIR=.codex bash scripts/launch_qa_review.sh --task "feature review"
HARNESS_DIR=.codex bash scripts/run_qa_review.sh --task "feature review" --status auto --append-calibration --contract-scope-changed no --new-session yes --progress-read no
HARNESS_DIR=.codex bash scripts/write_gate_artifact.sh qa-review --status pass --summary "no findings" --resolve-reviewer-mode
HARNESS_DIR=.codex bash scripts/calibration_report.sh
HARNESS_DIR=.codex bash scripts/calibration_report.sh --json
HARNESS_DIR=.codex bash scripts/apply_calibration_recommendation.sh --dry-run
HARNESS_DIR=.codex bash scripts/apply_calibration_recommendation.sh --apply
```

`enforce_closed_loop_policy.sh` is the CI-facing wrapper around `closed_loop.sh --json`; by default it fails when pending `qa-review` calibration follow-up is detected, `--allow-action <value>` lets you whitelist a specific state, `--check-calibration-report` extends enforcement to the nested `qa-review / contract / PROGRESS.md` recommendations, and `--json` emits the helper's own machine-readable pass/fail result. Automation should consume the top-level `compat_*` keys plus `schema_version`, not scrape nested objects by indentation; that stable surface includes `qa-review` artifact metadata such as presence, status, reviewer mode, findings count, and highest severity, plus threshold-readiness summaries like the recommended `max-findings` value and strictest passing deny-severity. The helper's `policy_state` carries the same data for consumers that prefer the wrapper output, and it can optionally enforce findings thresholds with `--max-qa-review-findings` and `--deny-qa-review-severity`. See the source harness repo `docs/harness-json-contract.md` for the stable field set and `docs/examples/github-actions-closed-loop.yml` for a copyable GitHub Actions bootstrap that stays fail-closed on pending follow-up by default; threshold bootstrap there is explicit opt-in via `OPEN_HARNESS_BOOTSTRAP_THRESHOLDS=yes`. `--apply` currently updates only the active contract `qa-review` requirement and adds or normalizes an adjacent structured `calibration_note` so the downgrade stays auditable and script-readable.
`.codex/review-capabilities.env` is the local capability map for `resolve_review_mode.sh`; by default it keeps review conservative and resolves to `same-context` until you explicitly mark a more isolated reviewer mode as available. The same file can also define `REVIEW_LAUNCH_COMMAND_*` hooks for `launch_qa_review.sh`; the bundled template already ships an opt-in `fresh-session` preset using `codex review --uncommitted`, and it writes review output under `.codex/review-handoffs/qa-review.output.md`. `run_qa_review.sh` is the convenience wrapper that consumes the same preset, writes the final gate artifact, and can append calibration in the same command.

Strict tiers additionally expose:

```bash
HARNESS_DIR=.codex bash scripts/deploy_gate.sh
HARNESS_DIR=.codex bash scripts/deploy_with_gate.sh
```

`verify.sh` is shared and does not need HARNESS_DIR.

Architecture-grade changes may add a committed ADR using `.codex/contracts/ADR-TEMPLATE.md`.

Load only the workflow needed for the current stage. Do not preload every harness workflow into one long-running context.
