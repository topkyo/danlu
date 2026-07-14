# Round 10 — Dogfood Queue Execution + Recovery Friction Fixes

status: 完成
commit: 

Round 10 — Dogfood Queue Execution + Recovery Friction Fixes — 完成
- **目的**: 在 Round 9 `review-queue` drilldown 后，真实执行一小批可回滚队列项，验证炼丹炉是否能从“看得见积压”推进到“能安全消化积压”
- **入场态**（dogfood vault `/home/tim/danlu/炼丹炉`）:
  - `ready_actions`: 7 条
  - `pending_judgments`: 1 条
  - `metrics`: `review_closure_rate=0.0`、`output_file_back_rate=0.0303`、`provenance_completeness=0.0`
- **真实执行**:
  - `apply-action ...-coverage --dry-run` → `apply-action ...-coverage`: 成功，receipt `output/control/execution-receipts/...coverage.json`
  - `apply-action ...-dataset --dry-run` → 首次 apply 因第一条 apply 后 compile 导致 bundle stale；重跑 dry-run 后 apply 成功，receipt `output/control/execution-receipts/...dataset.json`
  - `review-page wiki/judgments/judgment-20260428-054243-v3-6-vs-v3-5-slam-dogfood-judgment.md --status confirmed`: 成功
- **暴露摩擦与修复**:
  - `execution/machine_memory_actions.py`: stale bundle 错误从泛化 “re-run compile or apply-action --dry-run” 改为直接给出 `apply-action <id> --dry-run` 与后续 apply 命令
  - `cli/dispatch.py`: `review-queue --bucket ready_actions` 口径改为 accepted 且 actionable（`can_apply/can_review/can_revert` 任一为真），与 `today` 的 ready_actions 聚合对齐；排除 accepted-but-inert 历史项 `and/the`
- **测试**:
  - `tests/test_app.py::test_apply_machine_memory_action_rejects_stale_bundle` 断言 stale 错误含恢复命令
  - `tests/test_cli.py` review_queue focused 8/8，覆盖 ready_actions accepted/actionable 口径
- **验证**:
  - `bash scripts/verify.sh` exit 0；1491 unit + 13 acceptance；coverage 92%
- **出场态**:
  - `today --json`: machine_memory_actions 13、ready_actions 6、pending_judgments 已消失
  - `review-queue --bucket ready_actions --json`: 6 条，与 today 对齐（5 条 safe-apply + 1 条 `overloaded-concept-vlm` resolve command）
  - `review-queue --bucket pending_judgments --json`: total 0
  - `metrics --json`: `review_closure_rate=null reason=no review activity`，说明 metrics 目前未把 page review history 算作 review activity；记为 Round 11 指标口径候选
- **当前评估**: 执行闭环可用；single-writer + stale bundle safety 机制有效但需要更好的 batch UX。下一轮最高 ROI 是 metrics review activity 口径 + remaining ready actions 的 batch-safe apply 流程
