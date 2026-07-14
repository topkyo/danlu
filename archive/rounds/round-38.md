# Round 38 — Unattended Light-Lane Automation + Governance Debt Policy

status: 完成
commit: 

Round 38 — Unattended Light-Lane Automation + Governance Debt Policy — 完成
- **目的**: 执行下一步，把已验证安全的 light deterministic maintenance 接入 nightly 的显式 opt-in 静默自动执行，并明确剩余治理债的自动化处理分层
- **提交基线**:
  - `5424566 repair lifecycle review ack lint`
- **实现内容**:
  - `run-nightly` 现在读取 `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1`，启用后 nightly agent-loop 会在当前 writer lock 内自动执行 light lane `compile/lint/nightly`
  - `run_alchemy_auto` / lane dry-run / lane apply 增加内部 `allow_current_writer_lock` 参数；CLI 默认锁语义不变，只有 nightly 内部显式 opt-in 可复用当前 writer lock
  - `agent_loop` 继续默认 dry-run preview；启用 auto apply 时写入压缩后的 `auto_apply` 摘要，保留 primitive receipt 路径，避免把完整 plan 膨胀进 Today
  - `attach_agent_loop_to_nightly_state` 会合并当前 nightly state，避免 light apply 的 deterministic `nightly` primitive 刷新 state 后覆盖 agent-loop；同时保留本轮 `run-nightly` 的 `llm_used=true` 事实
  - Today feed 在 auto apply 成功后显示“已自动维护”，不再继续展示“预演下一步维护”
  - README 增加治理债自动化策略：L0 静默 apply、L1 静默生成候选、L2 显式采纳 gate
- **dogfood 运行测试**:
  - 手工写入前停止 `aiwiki-watch.service`，闭环结束后恢复 active
  - 使用 dogfood 已显式配置的 `codex-cli/gpt-5.5` 运行：
    - `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1 ... run-nightly --compile-limit 5 --no-semantic-lint`
  - `run-compile` 成功处理 5 个 source summaries：attempted_pages=5，succeeded_pages=5，failed_pages=0，duration_ms=284182
  - `run-nightly` 成功：`llm_used=true`，`agent_loop_auto_apply_light=true`，duration_ms=285623
  - agent_loop mode=`observe_dry_run_and_light_apply`，side_effects_allowed=true，signals_new=25，planner_execute_new=25
  - auto_apply status=applied，applied_count=1，执行 light primitives=`compile/lint/nightly`
  - 写入 receipted primitives：
    - `output/control/execution-receipts/alchemy-light-compile-20260430055200.json`
    - `output/control/execution-receipts/alchemy-light-lint-20260430055200.json`
    - `output/control/execution-receipts/alchemy-light-nightly-20260430055201.json`
- **dogfood 状态变化**:
  - nightly lint: 0 errors / 104 warnings -> 0 errors / 99 warnings
  - source placeholder summary warning 减少 5 条；剩余 warnings 主要是 soft concepts 与 judgment/decision 结构化语义债
  - review-queue total: 38 -> 41；原因是新增 source summaries 触发了更多 counter-evidence / machine memory / concept治理候选，这符合“静默生成候选，不静默采纳语义结论”的策略
  - metrics 保持健康：provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=112
  - Today 已显示“已自动维护：今日发现 25 个新变化，已静默执行 1 条维护路径”
- **监控状态**:
  - `/home/tim/.config/aiwiki/aiwiki-nightly.env` 已设置 `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1`
  - `aiwiki-watch.service` active，入口为 `/home/tim/ai-wiki/scripts/run_watch.sh`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-05-01 00:00:00 CST`
- **当前评估 / 治理债处理策略**:
  - L0 deterministic hygiene 已可静默处理：compile/lint/nightly、陈旧状态清理、派生索引 refresh 走 receipt/audit
  - L1 semantic enrichment 应静默生成候选或低风险派生更新：source summaries 可由 `run-compile` 写回派生 source page；judgment refresh、decision counter-evidence、concept split/merge 应先进入 candidates/review queue
  - L2 meaning-changing adoption 仍必须显式 gate：接受 machine memory action、采纳 L3 proposal、改写 judgment/decision 状态、更新 prompts/policies target
  - 结论：炼丹炉已具备 opt-in unattended light maintenance；仍未达到最终形态，因为 semantic candidate generation / adoption pipeline 还没有完全产品化，review-queue 仍有 41 个待处理候选
- **验证**:
  - focused tests pass：`tests/test_agent_loop.py` 4/4，`tests/test_runner.py` 40/40，`tests/test_alchemy_lanes.py` 66/66，Today/Product Shell 95/95
  - `bash scripts/verify.sh` exit 0；1531 unit + 13 acceptance；coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；无独立 reviewer session，本轮明确记录 fallback 原因
