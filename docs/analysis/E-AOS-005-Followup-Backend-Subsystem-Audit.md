# E — AOS-005 Follow-up: Backend Usage + Subsystem Risk Audit

> Report-only milestone. Scope: repo-visible receipts/history and static code audit. No backend deletion, no config/CLI/schema changes, no subpackage split.

## 0. Executive Summary

Current evidence is **insufficient to delete or deprecate any backend**.

Repo-local runtime history contains only one real LLM run with backend/model fields:

- backend: `nvidia-nim-api`
- model: `moonshotai/kimi-k2.5`
- event: `run-ask`

Acceptance fixtures additionally cover `codex-cli` with `stub-model`, but those are deterministic test fixtures, not production usage-frequency evidence.

Subsystem audit conclusion:

- `src/aiwiki/memory/execution_surfaces.py` is 1329 lines with several medium-large render/reconcile functions, but no single giant function comparable to `app_surfaces.py`; future work should be targeted helper extraction, not blind file splitting.
- `src/aiwiki/signals/adapters.py` is 518 lines with small/medium adapters; main risk is adapter coverage / unused planned paths, not size. `_iter_elixir_dependency_break_seeds` has no current production/test caller evidence and should be proven or removed in a separate contract.

## 1. Backend Usage Statistics

### 1.1 Evidence sources

Repo-visible runtime files inspected:

| File | Records | Backend/model fields | Event summary |
|---|---:|---|---|
| `.aiwiki/logs/llm-receipts.jsonl` | 1 | `nvidia-nim-api` / `moonshotai/kimi-k2.5` | `run-ask` |
| `.aiwiki/logs/runs.jsonl` | 1 | `nvidia-nim-api` / `moonshotai/kimi-k2.5` | `run-ask` |
| `.aiwiki/state/audit.jsonl` | 5 | none | `query` x4, `failed` x1 |
| `.aiwiki/state/runtime-history.jsonl` | 4 | none | `query` x4 |
| `.aiwiki/state/metrics-history.jsonl` | 2 | none | metrics snapshots |

Acceptance fixture/golden evidence:

| Fixture | Backend/model | Meaning |
|---|---|---|
| `M6.1b/case_happy_run_ask` | `codex-cli` / `stub-model` | deterministic success coverage |
| `M6.1b/case_backend_failure` | `codex-cli` / `stub-model` | deterministic failure/fallback coverage |

### 1.2 Interpretation

The repo-local runtime sample is too small for backend retirement decisions:

- real visible sample size with backend/model fields is effectively `1` run;
- fixture evidence proves compatibility paths, not actual usage frequency;
- audit/runtime history currently do not carry backend fields consistently enough to infer long-term ratios.

### 1.3 AOS-005b recommendation

Do **not** delete or hide any backend in AOS-005b based on the current evidence.

Minimum prerequisites before backend deletion/deprecation:

1. Collect backend/model usage from real dogfood receipts over a meaningful window.
2. Split success, degraded, fallback, timeout, and failed delivery modes.
3. Check CLI/help/config references and historical receipt replay compatibility.
4. Define a deprecation path: warn → hide from default help → remove only after compatibility window.

Until that exists, AOS-005b should remain **stats-first / no-deletion**.

## 2. `memory/execution_surfaces.py` Render Complexity Audit

### 2.1 Size and public surface

- File: `src/aiwiki/memory/execution_surfaces.py`
- LoC: 1329
- Public render/audit functions: 12

Function-size scan:

| Function | Approx lines | Risk |
|---|---:|---|
| `render_concept_quality` | 170 | medium |
| `reconcile_concept_rewrite_proposals` | 163 | medium |
| `collect_execution_consistency_signals` | 156 | medium |
| `render_execution_audit` | 111 | low-medium |
| `render_execution_proposal_page` | 105 | low-medium |
| `render_execution_center` | 103 | low-medium |
| `render_execution_center_html` | 102 | low-medium |
| `build_execution_audit_snapshot` | 97 | low-medium |
| `render_execution_audit_html` | 90 | low-medium |
| `render_concept_rewrite_proposal_page` | 81 | low |
| `render_concept_rewrite_index` | 66 | low |
| `concept_rewrite_proposal_digest` | 4 | low |

### 2.2 Interpretation

This file is large, but it is not currently an `app_surfaces.py`-style giant-function hotspot.

Observed risk:

- render, reconciliation, and consistency scan logic are close together;
- several functions are 100–170 lines and would benefit from helper extraction;
- no evidence supports a large subpackage split in this milestone.

### 2.3 Recommendation

Defer to a future AOS-006-style targeted simplification:

1. Extract helpers from `render_concept_quality` first.
2. Then split reconciliation helpers from `reconcile_concept_rewrite_proposals`.
3. Then isolate consistency-signal row builders in `collect_execution_consistency_signals`.
4. Keep public render function names stable unless a separate compatibility contract proves safe.

Do **not** split the file just to reduce LoC.

## 3. `signals/adapters.py` Adapter Usage / Dead-Code Risk Audit

### 3.1 Supported sources

Current supported signal sources:

```python
SUPPORTED_SOURCES = ("runtime_history", "llm_receipt", "archive")
```

Collector dispatch currently covers these paths:

- `_runtime_history_to_signals`
- `_llm_receipt_to_signals`
- `_archive_receipt_to_signals`

Tests in `tests/test_signals_collector.py` cover the main adapters and source routing.

### 3.2 Function-size scan

| Function | Approx lines | Risk |
|---|---:|---|
| `_archive_receipt_to_signals` | 86 | medium |
| `_elixir_dependency_break_to_signals` | 76 | medium |
| `_runtime_history_to_signals` | 55 | low-medium |
| `_runtime_history_learning_threshold_to_signals` | 50 | low-medium |
| `_runtime_history_counter_evidence_to_signals` | 45 | low-medium |
| `_runtime_history_raw_added_to_signals` | 43 | low-medium |
| `_llm_receipt_to_signals` | 39 | low |
| `_iter_elixir_dependency_break_seeds` | 23 | usage risk |
| other helpers | 2–14 | low |

### 3.3 Dead/planned adapter risk

`_iter_elixir_dependency_break_seeds` has no current production/test caller evidence in this repo scan. That does not prove it is wrong, but it means it should not silently remain as assumed-live runtime behavior.

Recommended follow-up:

1. Add an explicit test or runtime call path if elixir dependency break signals are intended.
2. Otherwise remove the unused iterator in a separate, reviewable cleanup contract.
3. Do not delete `_elixir_dependency_break_to_signals` or related constants in this report-only milestone.

## 4. What Should Move Forward

### Later AOS-005b

Allowed next step:

- backend usage telemetry/reporting over real dogfood receipts;
- deprecation plan design;
- historical receipt replay compatibility audit.

Not allowed yet:

- deleting backend implementations;
- changing backend config schema;
- changing CLI options or default routing.

### Later AOS-006

Possible targeted simplification:

- helper extraction in `memory/execution_surfaces.py`;
- explicit proof/remove decision for `_iter_elixir_dependency_break_seeds`;
- no broad split until tests and owner boundaries are written first.

## 5. Single-Sentence Conclusion

> **AOS-005-followup should stop at evidence: current backend usage data is too sparse for backend deletion, `memory/execution_surfaces.py` deserves targeted helper extraction later but not a blind split, and `signals/adapters.py` is structurally small enough that its main follow-up is proving or removing the currently unreferenced elixir dependency-break iterator.**
