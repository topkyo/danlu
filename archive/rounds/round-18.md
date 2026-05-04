# Round 18 — Judgment Revisit From Page Review History

status: 完成
commit: 

Round 18 — Judgment Revisit From Page Review History — 完成
- **目的**: dogfood judgment page 已有 tracking + confirmed 两条 Review History，但 `metrics --json` 仍显示 `judgment_revisit_rate=null reason=no judgment receipts`；根因是 metrics 只读 judgment execution receipts，不读 `review-page` 写入的页面审阅历史
- **设计核心**:
  - `metrics_io._read_page_review_receipts()`: 保留 Round 11 的 `subject_kind=review` closure synthetic receipt
  - 对 judgment page 额外解析 `## Review History` 中 `- `timestamp` | status `...`` 行，生成 `subject_kind=judgment` synthetic receipts
  - 没有 Review History 行但有 `reviewed_at` 时，降级生成单条 judgment review receipt
  - 不改 review-page 写入格式、不改 metrics 顶层 key、不把 decision history 计入 judgment revisit
- **测试**:
  - `tests/test_metrics_io.py::test_judgment_review_history_counts_as_judgment_revisit_activity`
  - 既有 `test_page_review_history_counts_as_review_closure_activity` 保持
- **验证**:
  - focused judgment revisit tests 3/3
  - `bash scripts/verify.sh` exit 0；1498 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `metrics --json`: `judgment_revisit_rate` 从 `null/no judgment receipts` → `1.0`，sample_size=1
- **当前评估**: page review 活动现在能同时反馈 closure 与 revisit；剩余指标缺口主要是 `proposal_acceptance_rate=null`（L3 apply/revert receipt 未进入 proposal decision 口径）和 `elixir_reuse_count=0`（真实长期复用尚未发生）
