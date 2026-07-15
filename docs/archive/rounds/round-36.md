# Round 36 — Dogfood Governance Repair + Safe Light-Lane Apply Test

status: 完成
commit: 

Round 36 — Dogfood Governance Repair + Safe Light-Lane Apply Test — 完成
- **目的**: 修复 Round 35 暴露的主要可闭环缺口，继续 `/home/tim/danlu/炼丹炉` 运行测试，并重新评估炼丹炉当前状态、功能完整度与是否达到最终形态
- **提交基线**:
  - `2556c44 surface nightly agent loop preview`
- **修复内容**:
  - lifecycle refresh 现在会把 active concept lifecycle override 中指向已消失 `wiki/concepts/*.md` 的项自动转为历史项，写入 `cleared_at` / `cleared_note` / `cleared_reason_codes=["missing-target"]`，不再让陈旧 review-ack 永久污染 lint
  - lint 只把 active override 的缺失 target 视为错误；inactive 历史 override 保留审计价值，不再作为当前运行错误
  - execution consistency 不再要求 history-only / closed 的 monitor action 必须有 apply receipt；只对有实际安全执行状态面的 `manual-link-state` / `citation-snapshot-refresh` resolved action 强制要求最新 apply receipt
- **dogfood baseline -> 修复后**:
  - baseline `lint`: 11 errors / 134 warnings
  - 修复后 `lint`: 0 errors / 125 warnings
  - 自动清理 9 个 stale lifecycle overrides：`base`、`bearing`、`body`、`clearing`、`cloud`、`distance`、`edge`、`graph`、`growth`
  - 2 个 execution consistency false positive 已消失：`singleton-concept-growth`、`overloaded-concept-vlm`
- **light lane 运行测试**:
  - `alchemy auto --dry-run --scope all --lane light`: status preview，light ready，selected_count=46，selected_primitives=`compile/lint/nightly`
  - `alchemy auto --apply --scope all --lane light`: status applied，applied_count=1；实际执行 deterministic maintenance primitives=`compile/lint/nightly`
  - 写入 receipted primitives：
    - `output/control/execution-receipts/alchemy-light-compile-20260430051815.json`
    - `output/control/execution-receipts/alchemy-light-lint-20260430051815.json`
    - `output/control/execution-receipts/alchemy-light-nightly-20260430051816.json`
  - runtime history 已记录 `alchemy-lane-started`、`alchemy-lane-completed`、`alchemy-auto-scheduler`
  - heavy lane 仍未执行；judge/distill/review/propose 仍按 contract 被 light lane 阻断
- **试运行结果**:
  - nightly health `2026-04-30T05:18:16+00:00`: `llm_used=false`，compile sources=32，concepts=30，drift_warnings=[]，machine_memory_core_reused=true
  - nightly lint: 0 errors / 125 warnings；剩余 warnings 主要是 source placeholder summaries、active deferred lifecycle ack、soft concepts、judgment/decision structured metadata 与 placeholder sections
  - agent_loop status=ok，side_effects_allowed=false；signals new=1；planner observe/execute new=2，duplicate=142
  - `today --json` 显示“今日发现 2 个新变化，1 条维护路径可人工确认”
  - `review-queue --json` total=38，仍主要来自 machine_memory_actions=15、counter_evidence_candidates=9、judgment_review_actions=9、concept_backlog=9、review_concepts=6、revisit_concepts=3、l3_proposals=1、drift=1
  - metrics: provenance_completeness=1.0，stale_ratio=0.0，review_closure_rate=1.0，proposal_acceptance_rate=1.0，judgment_revisit_rate=0.5，output_file_back_rate=0.8333，elixir_reuse_count=1
- **监控状态**:
  - `aiwiki-watch.service` 已恢复 active，命令为 `python3 -m aiwiki.cli --root /home/tim/danlu/炼丹炉 watch --interval 5 --compile-limit 5 --deterministic-only`
  - `aiwiki-nightly.timer` active，下一次触发 `2026-05-01 00:00:00 CST`
- **当前评估**:
  - 主要错误级治理债已清零，light lane 已能在显式 `--apply` 下安全执行 deterministic maintenance，不再只是 dry-run 能力
  - 仍未达到最终形态：light lane 尚未成为无人值守自动 scheduler；heavy lane semantic apply 仍被 contract 阻断；review-queue backlog 仍为 38；125 warnings 代表真实内容治理债；LLM worker 仍是显式 worker 路径；source summaries 与 judgment/decision 结构化资产仍需后续治理
  - 结论：炼丹炉已从 controlled-runtime / agent-loop preview 推进到“可显式安全执行 light maintenance 的 dogfood runtime”，但仍不是最终形态
- **验证**:
  - focused regression tests pass：4/4
  - `tests/test_linting.py` pass：8/8
  - `bash scripts/verify.sh` exit 0；1526 unit + 13 acceptance；coverage 92%
  - QA review gate `.codex/gates/qa-review.md`: pass / self-review fallback；无独立 reviewer session，本轮明确记录 fallback 原因
