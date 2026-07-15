# Round 35 — Monitoring Restart + Agent Loop Dogfood Assessment

status: 完成
commit: 

Round 35 — Monitoring Restart + Agent Loop Dogfood Assessment — 完成
- **目的**: 在 Round 34 提交后重启/确认监控，继续 `/home/tim/danlu/炼丹炉` 试运行，用真实 dogfood state 评估炼丹炉当前状态、功能完整度与最终形态差距
- **提交基线**:
  - `2556c44 surface nightly agent loop preview`
- **监控状态**:
  - `aiwiki-watch.service` 已重启并 active，当前命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-05-01 00:00:00 CST`
  - watcher/nightly service 均通过 `PYTHONPATH=/home/tim/ai-wiki/src` 读取当前源码
- **试运行结果**:
  - dogfood deterministic `nightly` 成功，`llm_used=false`，sources=32，concepts=30，drift_warnings=[]，machine_memory_core_reused=true
  - Round 34 agent-loop preview 在真实 vault 生效：signals new=142，planner observe new=142，planner execute new=142，`side_effects_allowed=false`
  - `alchemy auto --dry-run --scope all` 显示 heavy lane skipped（empty execute plan），light lane ready，selected_count=46，候选 primitives=`compile/lint/nightly`，未执行 apply
  - `today --json` 已显示“预演下一步维护”；Product Shell shell-summary 已刷新到 `output/control/shell-summary.json`
- **发现并修复的问题**:
  - Today agent-loop 文案把 `signals.new_count` 与派生的 `planner.execute.new_count` 相加，首次 backfill 显示“284 个新变化”，属于用户可见双计数
  - 已修为取源信号/派生决策的上界，不重复计算同一变化；dogfood Today 复查后显示“今日发现 142 个新变化，1 条维护路径可人工确认”
  - Product Shell JS mirror 与 `main.js` 已同步重建
- **dogfood 健康度**:
  - metrics: provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=1
  - review-queue total=38：machine_memory_actions=15，counter_evidence_candidates=9，judgment_review_actions=9，concept_backlog=9，review_concepts=6，revisit_concepts=3，l3_proposals=1，drift=1
  - nightly lint 仍有 11 errors / 134 warnings：主要是 2 个 execution consistency issue、9 个 missing lifecycle override target pages、source placeholder summaries、soft concepts 与 judgment/decision 结构化 metadata 缺口
- **当前评估**:
  - 已达到：local-first 文件分层、watcher deterministic ingest、nightly health、signals/planner-log、dry-run agent-loop、metrics、review queue、Product Shell Today 均能在真实 vault 连通
  - 未达到最终形态：light lane 仍只预演不自动安全执行；heavy lane judge/distill/review/propose 仍受 contract 阻断；dogfood backlog 需要人工治理；LLM worker 本轮未作为常驻/自动 agent 纳入闭环；source summaries 和 judgment/decision 结构化资产仍有质量债
  - 结论：炼丹炉是可 dogfood 的 controlled-runtime / agent-loop preview system，不是最终形态；下一阶段应优先把 safe light-lane apply、lifecycle override repair、structured judgment refresh 做成受 receipt/audit 约束的可回滚闭环
- **验证**:
  - focused Today/Product Shell tests pass，50/50
  - `node --check .obsidian/plugins/furnace-product-shell/main.js` pass
  - `node --check .obsidian/plugins/furnace-product-shell/src/today_feed.js` pass
  - dogfood `today --json` 复查 pass，双计数已消除
