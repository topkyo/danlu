# Round 9 — Review Queue Drilldown Console

status: 完成
commit: 

Round 9 — Review Queue Drilldown Console — 完成（active contract refreshed）
- **目的**: `.codex/contracts/active.md` 停在 Round 5，已落后于 HEAD `f6413a6`（Round 8C）。真实 dogfood 显示 `review-queue` 虽已存在，但 `review-queue --bucket machine_memory_actions` 只输出一行 “15 项待审”，不能展开具体 item / command，review throughput 仍被卡住
- **基线重建**:
  - HEAD: `f6413a6 Round 8C: refresh review surfaces and batch triage actions`
  - 已交付链: Round 5 `today --json` / retire batch / review-queue；Round 6 retroactive concept-noise rebuild；Round 7 review-concept；Round 8B reactivate override cleanup；Round 8C batch triage actions
  - dogfood vault `/home/tim/danlu/炼丹炉`: `today --json` 显示 machine_memory_actions 15、ready_actions 8、pending_judgments 1；`metrics --json` 显示 review/output 回流仍偏低
- **设计核心**:
  - 重写 `.codex/contracts/active.md` 为 Round 9 当前契约，不再以旧 Round 5 作为执行源
  - `cli/dispatch.py::review_queue_command` 保留原 `build_today_feed()` 聚合 bucket，但用 `summary.review_controls` / `summary.execution_controls` 为可识别 bucket 提供 drilldown item
  - 已展开 bucket: `machine_memory_actions`、`ready_actions`、`pending_judgments`、`pending_decisions`、`judgment_review_actions`、`counter_evidence_candidates`、`l3_proposals`
  - 每条 drilldown item 输出 `id/title/summary/target/protocol/kind/status/command/can_review/can_apply`；文本模式追加 `command:` 行
  - 不改 persisted state schema，不改 `today` 5-section contract，不执行 dogfood 写操作
- **测试**:
  - `tests/test_cli.py -k review_queue`: 8/8
  - 新增覆盖：machine_memory_actions drilldown、ready_actions 只取 can_apply、pending_judgments review-page command、text command 渲染
- **验证**:
  - `bash scripts/verify.sh` exit 0；1491 unit + 13 acceptance；coverage 92%
- **dogfood read-only smoke**:
  - `today --json`: 仍输出 6 个 needs_review 聚合信号
  - `review-queue --bucket machine_memory_actions --json`: 展开 15 条具体 action，含 `apply-action ... --dry-run` / `review-action ... --status accepted|resolved`
  - `review-queue --bucket ready_actions --json`: 展开 7 条 can_apply action
  - `review-queue --bucket pending_judgments --json`: 展开 1 条 judgment，含 `review-page ... --status confirmed`
- **当前评估**: 炼丹炉已经从“能产出高质量判断”推进到“能把积压转成可执行队列”；下一轮真正产品试运行应执行一批 ready_actions / review-actions，观察 metrics 的 `review_closure_rate`、`output_file_back_rate`、provenance 指标是否改善
