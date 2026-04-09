---
name: closed-loop
description: Semi-automatic engineering runner. Validates contract policy, runs verify, checks gate artifacts, and prints writeback hints.
---

# Closed Loop

Run the semi-automatic engineering loop after implementation work.

## Default Entry Point

```bash
bash scripts/closed_loop.sh
```

## Options

```bash
bash scripts/closed_loop.sh --artifacts-only
bash scripts/closed_loop.sh --require-contract
bash scripts/closed_loop.sh --json
bash scripts/enforce_closed_loop_policy.sh
bash scripts/enforce_closed_loop_policy.sh --json
bash scripts/enforce_closed_loop_policy.sh --check-calibration-report
bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --max-qa-review-findings 0
bash scripts/enforce_closed_loop_policy.sh --allow-action backfill-structured-note --deny-qa-review-severity high
```

## What It Checks

1. Contract execution policy and stop conditions when a contract exists
2. Project-local `verify`
3. `qa-review` / `qa-runtime` artifacts per contract
4. Writeback hints for `PROGRESS.md`, contract, gate artifacts, current `qa-review` calibration-note state, calibration downgrade suggestions, and the dry-run apply planner

## Notes

- This runner does not deploy
- This runner does not update state files or gate artifacts for you
- `--json` emits a machine-readable summary on stdout and keeps runner logs on stderr; automation should consume the top-level `compat_*` keys plus `schema_version`
- that stable surface includes `qa-review` artifact metadata such as presence, status, reviewer mode, findings count, and highest severity, plus threshold-readiness summaries for findings/severity gating
- the stable field set is documented in the source harness repo `docs/harness-json-contract.md`
- `enforce_closed_loop_policy.sh` is the CI wrapper that fails when pending follow-up actions are not explicitly allowed, `--check-calibration-report` extends that enforcement to nested calibration recommendations, and `--json` emits the helper's own machine-readable pass/fail result; its `policy_state` carries the same `qa-review` artifact metadata and threshold summaries
- the same helper can optionally enforce `qa-review` findings thresholds with `--max-qa-review-findings` and `--deny-qa-review-severity`; if you ask for those checks and the artifact metadata is missing, it fails closed
- the source harness repo also ships a copyable GitHub Actions example at `docs/examples/github-actions-closed-loop.yml`; it stays fail-closed on pending follow-up by default, and threshold bootstrap there is explicit opt-in via `OPEN_HARNESS_BOOTSTRAP_THRESHOLDS=yes`
- If `verify` changes the worktree or contract, refresh the relevant gate artifacts before expecting a pass
- Use `deploy_gate.sh` / `deploy_with_gate.sh` for release-time gating
