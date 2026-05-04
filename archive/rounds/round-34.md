# Round 34 — Nightly Agent Loop Preview

status: 完成
commit: 

Round 34 — Nightly Agent Loop Preview — 完成
- **目的**: 把 `signals-replay -> planner-log-replay -> alchemy auto --dry-run` 接入 nightly 可见主线，让每日运行能看到下一步维护预演，但仍不执行 lane apply、不自动采纳 L3 proposal、不隐式切换 backend/model
- **实现**:
  - 新增 `aiwiki.agent_loop`：nightly 后执行 signals collection、observe-only planner-log、execute-mode planner-log，并生成 heavy/light `alchemy auto` dry-run 摘要
  - `run-nightly` 与 deterministic `nightly` 都把 `agent_loop` 写入 `.aiwiki/state/nightly-health.json`，返回 payload 也暴露同一摘要；LLM receipt 只记录预演状态，不记录为 apply
  - `preview_alchemy_lane` 新增 `allow_current_writer_lock`，仅允许 nightly 当前 writer lock 内部做 dry-run preview；普通调用仍保持 lock conflict 行为
  - `shell-status` summary 暴露 `nightly.agent_loop`，`today` / Product Shell 把它转成“预演下一步维护” action，不在标题/摘要中暴露 `planner-log`、`signal`、`receipt`、`lane` 等机制词
  - Product Shell source mirror 已更新并重建 `main.js`
- **边界**:
  - 本轮只写 signals/planner-log/nightly state，不执行 `alchemy auto --apply` 或 heavy/light lane apply
  - 不写 `prompts/*.md`、`schema/policies/*`，不自动 accept/apply proposal，不改变 `raw/` / `wiki/` / `output/` 分层规则
  - acceptance `case_light_primitives_nightly` golden 已更新，反映 nightly primitive 现在会补一条 observe-only planner-log 预演记录
- **验证**:
  - focused Round 34 tests: `tests.test_agent_loop tests.test_today_feed tests.test_product_shell_today_feed tests.test_runner.RunnerTests.test_run_nightly_returns_top_level_audit_summary tests.test_app.AiwikiFlowTests.test_nightly_health_persists_planner_execution_history_for_auto_bundle_candidates`，55/55 pass
  - `bash scripts/verify.sh` exit 0；1524 unit + 13 acceptance；coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / fresh-session / no findings
