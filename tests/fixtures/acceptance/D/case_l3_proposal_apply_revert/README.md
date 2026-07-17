# D: L3 proposal create → apply → revert acceptance

Function-level fixture for the L3 governance lane. Exercises a three-step
chain (`create_l3_proposal` → `apply_l3_proposal` → `revert_l3_proposal`)
against a deterministic prompt target, and asserts byte-stable goldens for:

- `prompts/test-prompt.md` (final state after revert == original bytes)
- `.aiwiki/state/l3-proposals.json` (terminal state `reverted`)
- `.aiwiki/state/execution-receipts/l3-proposal-apply-prop-test-prompt.json`
- `.aiwiki/state/execution-receipts/l3-proposal-revert-prop-test-prompt.json`
- `.aiwiki/state/runtime-history.jsonl` (create + apply + revert events)
- `.aiwiki/state/audit.jsonl` (mirror of runtime-history + receipt history)

> Note: `wiki/indexes/log.md` was retired (2026-07-17); governance history is jsonl-only.

## Stop-line interaction

`test_acceptance_no_stop_line_violations` (tests/test_acceptance_loop.py)
forbids the substring `l3-proposal-apply` in any acceptance golden because
nightly happy paths must never emit that event. This case is the deliberate
opposite: it explicitly tests the governance lane, so `l3-proposal-apply`
appears in receipt filenames and event_type. The stop-line
test grants this case (`D/case_l3_proposal_apply_revert`) an exception for
the `l3-proposal-apply` term only; the other four forbidden terms
(`lane_judge`, `auto_judge`, `l3-proposal-accept`, `hidden_backend`) remain
banned even here.

## Determinism notes

- `_copy_case_and_fix_clock_from` patches `aiwiki.execution.l3_proposals.utc_now`
  to FIXED_NOW (2026-04-27T00:00:00+00:00). `l3_proposals.py` uses
  `from aiwiki.app_utils import utc_now`, which is a module-local binding;
  patching only `aiwiki.app_utils.utc_now` would not reach it.
- `_unique_l3_action_id` derives action_id from `{prefix}-{proposal_id}` plus
  next-available stem, not the wall clock, so receipt paths are stable as
  `l3-proposal-apply-prop-test-prompt.json` and
  `l3-proposal-revert-prop-test-prompt.json`.
- Apply and revert share the same FIXED_NOW; `reverted_at == applied_at` is
  acceptable because the two events write to distinct action_id-stemmed
  receipt files.
