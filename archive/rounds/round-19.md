# Round 19 — Proposal Acceptance From Reverted Accepted L3 Proposals

status: 完成
commit: 

Round 19 — Proposal Acceptance From Reverted Accepted L3 Proposals — 完成
- **目的**: dogfood `prop-ask` 已 apply 后 revert，但 `proposal_acceptance_rate=null reason=no decided proposals`；根因是 metrics 只看当前 `state=reverted`，没有把 `accepted_at` 表示的接受决策纳入 acceptance rate
- **设计核心**:
  - `metrics_io._proposal_from_mapping()`: `candidate` 继续归一为 `pending`
  - `state=reverted` 且存在 `accepted_at` 时，metrics read-side 归一为 `accepted`
  - 不改 L3 proposal state machine、不迁移 state、不改 metrics 顶层 key
- **测试**:
  - `tests/test_metrics_io.py::test_reverted_proposal_with_accepted_at_counts_as_accepted_decision`
  - focused proposal acceptance tests 2/2
- **验证**:
  - `bash scripts/verify.sh` exit 0；1499 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `proposal_acceptance_rate` 从 `null/no decided proposals` → `1.0`，sample_size=1
- **当前评估**: metrics 的 dogfood 主指标除 `elixir_reuse_count` 外均已反映真实闭环；`elixir_reuse_count=0` 是当前 vault 尚未发生后续复用，不应通过读侧修正伪造
