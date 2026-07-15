# Round 12 — Ready Actions Batch Helper Dogfood

status: 完成
commit: 

Round 12 — Ready Actions Batch Helper Dogfood — 完成
- **目的**: Round 11 后指标闭环已恢复，但真实 dogfood vault 仍有 `ready_actions=6`，其中 5 条 accepted low-risk action 需要逐条 dry-run/apply；现有 batch apply 入口不容易从 `review-queue` 发现
- **当前效果评估**:
  - 炼丹炉已经能从真实研究材料产出 reports / judgment / decision memo，并沉淀到 wiki/output
  - review/execution 队列可展开，`review-page` 与 action apply 结果能进入 metrics；`review_closure_rate=1.0`
  - 主要产品摩擦从“能不能生成”转为“能不能高吞吐、安全地消化积压”
  - 仍未到最终效果：`provenance_completeness=0.0`、`output_file_back_rate=0.0303`、`elixir_reuse_count=0`，说明证据完整性、输出回流和金丹复用还没有形成稳定复利
- **设计核心**:
  - `cli/dispatch.py`: 新增 `_ready_actions_batch_helper()`，当 ready bucket 中 `can_apply` item 数量 > 1 时追加派生 helper item
  - helper `id=batch-apply-all-accepted-low-risk`，`kind=batch-helper`，command 为 `apply-action --all-accepted-low-risk --dry-run`
  - 不改 persisted schema、不改 batch apply 执行语义、不污染 `machine_memory_actions` 原始明细 bucket
- **测试**:
  - `tests/test_cli.py::test_review_queue_ready_actions_adds_batch_helper_for_multiple_apply_items`
  - `tests/test_cli.py::test_review_queue_ready_actions_omits_batch_helper_for_single_apply_item`
  - 既有 ready_actions / text command tests 保持
- **验证**:
  - focused unittest review-queue cases: 4/4
  - `bash scripts/verify.sh` exit 0；1494 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `review-queue --bucket ready_actions --json`: 5 条 `can_apply` + 1 条 `review-action ... --status resolved` + 1 条 batch helper
  - `apply-action --all-accepted-low-risk --dry-run`: `operation=action-dry-run-batch`，`count=5`，未执行真实 apply
- **当前评估**: 试运行已进入“判断资产可生产、队列可消化、指标可反馈”的阶段；下一轮最高 ROI 是执行该 batch apply 后验证 `ready_actions` 归零/下降、再处理 `overloaded-concept-vlm` 与 provenance/output 回流指标
