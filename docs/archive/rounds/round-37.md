# Round 37 — Remaining Gap Repair + Dogfood Runtime Assessment

status: 完成
commit: 

Round 37 — Remaining Gap Repair + Dogfood Runtime Assessment — 完成
- **目的**: 继续修复 Round 36 后剩余缺口中可确定、可本地闭环验证的部分，随后恢复监控并继续 `/home/tim/danlu/炼丹炉` 运行测试，重新评估炼丹炉当前状态与最终形态差距
- **提交基线**:
  - `1e56fd5 repair dogfood governance and light lane apply`
- **修复内容**:
  - lint 现在把 `review_concept` 合法写出的 active concept lifecycle override 识别为 review ack：`operation == "review"` 且 `lifecycle_state` 属于 `active/deferred/review` 时不再按 “expects retired” 报 warning
  - active non-review override 且状态非 `retired` 仍继续 warning，避免吞掉真正异常或未完成的 lifecycle override
  - 新增 focused regression 覆盖合法 active review ack 与非法 active non-review override 两条路径
- **dogfood baseline -> 修复后**:
  - Round 36 后 baseline `lint`: 0 errors / 125 warnings
  - 修复后 `lint`: 0 errors / 104 warnings
  - 消除 21 条 active `review` lifecycle override 假阳性；剩余 warnings 主要是 source placeholder summaries、soft concepts、judgment/decision structured metadata 与 placeholder sections
- **light lane 运行测试**:
  - `alchemy auto --dry-run --scope all --lane light`: status preview，light ready，selected_count=47，selected_primitives=`compile/lint/nightly`
  - `alchemy auto --apply --scope all --lane light`: status applied，applied_count=1；实际执行 deterministic maintenance primitives=`compile/lint/nightly`
  - 写入 receipted primitives：
    - `output/control/execution-receipts/alchemy-light-compile-20260430053207.json`
    - `output/control/execution-receipts/alchemy-light-lint-20260430053208.json`
    - `output/control/execution-receipts/alchemy-light-nightly-20260430053208.json`
  - runtime history 已记录 `alchemy-lane-started`、`alchemy-lane-completed`、`alchemy-auto-scheduler`
  - heavy lane 仍未执行；judge/distill/review/propose 仍按 light lane 边界被阻断为 deferred primitives
- **试运行结果**:
  - nightly health `2026-04-30T05:32:08+00:00`: `llm_used=false`，compile sources=32，concepts=30，changed_pages=8，drift_warnings=[]，machine_memory_core_reused=true
  - nightly lint: 0 errors / 104 warnings
  - agent_loop status=ok，side_effects_allowed=false；signals new=1 / duplicate=189 / invalid=10；planner execute new=1 / duplicate=145；auto_preview status=preview
  - `today --json` 显示“今日发现 1 个新变化，1 条维护路径可人工确认”
  - `review-queue --json` total=38，仍主要来自 machine_memory_actions=15、counter_evidence_candidates=9、judgment_review_actions=9、concept_backlog=9、review_concepts=6、revisit_concepts=3、l3_proposals=1、drift=1
  - metrics 维持健康：provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=1
- **监控状态**:
  - 手工写入 dogfood vault 前已停止 `aiwiki-watch.service`，闭环结束后恢复 active
  - `aiwiki-watch.service` active，入口为 `/home/tim/ai-wiki/scripts/run_watch.sh`，读取当前源码
  - `aiwiki-nightly.timer` active，下一次触发 `2026-05-01 00:00:00 CST`
- **当前评估**:
  - 已达到：错误级治理债保持清零；light lane 可在显式 `--apply` 下重复安全执行 deterministic maintenance；agent-loop/nightly/today/metrics/review queue 真实 dogfood 连通；review-ack lifecycle governance 不再制造假 warning backlog
  - 尚未达到最终形态：light lane 仍不是默认无人值守 scheduler；heavy semantic apply 仍被 contract 阻断；review-queue backlog 仍为 38；104 warnings 是真实内容治理债；LLM worker 仍是显式 worker 路径；source summaries 与 judgment/decision 结构化资产仍需语义治理
  - 结论：炼丹炉已是“可显式安全执行 light maintenance 的 dogfood controlled-runtime”，状态比 Round 36 更干净，但仍不是最终形态
- **验证**:
  - `tests/test_linting.py` pass：10/10
  - `bash scripts/verify.sh` exit 0；1528 unit + 13 acceptance；coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；无独立 reviewer session，本轮明确记录 fallback 原因
