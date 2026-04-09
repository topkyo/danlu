# Closed Loop

Semi-automatic engineering runner.

```bash
HARNESS_DIR=.codex bash scripts/closed_loop.sh
```

Options:

```bash
HARNESS_DIR=.codex bash scripts/closed_loop.sh --artifacts-only
HARNESS_DIR=.codex bash scripts/closed_loop.sh --require-contract
HARNESS_DIR=.codex bash scripts/closed_loop.sh --json
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --json
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --check-calibration-report
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --max-qa-review-findings 0
HARNESS_DIR=.codex bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --deny-qa-review-severity high
```

What it does:

1. Validates contract execution policy and stop conditions when a contract exists
2. Runs project-local `verify`
3. Validates `qa-review` / `qa-runtime` artifacts per contract
4. Prints writeback hints for `PROGRESS.md`, contract, gate artifacts, current `qa-review` calibration-note state, calibration downgrade suggestions, and the dry-run apply planner

It does not deploy or update state files for you. `--json` emits a machine-readable summary on stdout and keeps runner logs on stderr; automation should consume the top-level `compat_*` keys plus `schema_version`, not scrape nested objects by indentation. That stable surface includes `qa-review` artifact metadata such as presence, status, reviewer mode, findings count, and highest severity, plus threshold-readiness summaries like the current recommended `max-findings` value and the strictest deny-severity that would still pass. The stable field set is documented in the source harness repo `docs/harness-json-contract.md`. `enforce_closed_loop_policy.sh` is the CI wrapper that fails when pending follow-up actions are not explicitly allowed, `--check-calibration-report` extends that enforcement to the nested calibration recommendations, and `--json` emits the helper's own machine-readable pass/fail result; its `policy_state` carries the same `qa-review` artifact metadata and threshold summaries. It can also enforce `qa-review` findings thresholds directly with `--max-qa-review-findings` and `--deny-qa-review-severity`, failing closed if the artifact is missing the required metadata. For a copyable CI bootstrap, see the source harness repo example `docs/examples/github-actions-closed-loop.yml`, which stays fail-closed on pending follow-up by default and only bootstraps thresholds when `OPEN_HARNESS_BOOTSTRAP_THRESHOLDS=yes`. If `verify` changes the worktree or contract, refresh the relevant gate artifacts before expecting a pass. Use `deploy_gate.sh` / `deploy_with_gate.sh` for release.
