# Round 21 — Today Action Backlog Count Alignment

status: 完成
commit: 

Round 21 — Today Action Backlog Count Alignment — 完成
- **目的**: Round 20 后主指标全绿；继续推进 `today` 建议动作时发现 `review-queue --bucket machine_memory_actions` 实际 total=6，但 `today --json` 仍显示 `machine_memory_actions` summary=8，说明炉心入口和 drilldown 口径不一致
- **真实 dogfood 队列推进**:
  - `review-action singleton-concept-growth --status accepted --note "Round 21 dogfood accepted suggested singleton growth repair."`
  - `review-action singleton-concept-growth --status resolved --note "Round 21 dogfood: reviewed Growth as source-specific; no safe concept expansion without a second source, comparable metric, or counterexample."`
  - `ready_actions`: 0；`machine_memory_actions` drilldown: 7 → 6
- **设计核心**:
  - `app_shell.summary._action_review_backlog_counts()`: 从 `execution_controls.actions` 的真实 actionable controls 计算 `machine_memory_actions` 和 `ready_actions`
  - `build_shell_summary()` 用该结果覆盖 memory health 中可能滞后的 aggregate count
  - 使 `today` summary 与 `review-queue` drilldown 同源，避免顶部待审数字误导
- **测试**:
  - `tests/test_app_shell_summary.py::test_action_review_backlog_counts_follow_actionable_controls`
  - `tests/test_app_shell_summary.py::test_action_review_backlog_counts_treat_bad_controls_as_empty`
- **验证**:
  - focused shell summary tests 2/2
  - `bash scripts/verify.sh` exit 0；1501 unit + 13 acceptance；coverage 92%
- **dogfood smoke**:
  - `today --json`: `machine_memory_actions` summary 从 8 修正为 6
  - `review-queue --bucket ready_actions --json`: total 0
  - `review-queue --bucket machine_memory_actions --json`: total 6
- **当前评估**: 炉心入口和 drilldown 口径重新一致；剩余 6 条 bridge-concept proposed action 需要人工语义判断，不应自动批量接受
