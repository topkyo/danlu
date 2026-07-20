---
title: "炼丹炉归档文档索引"
kind: "index"
status: "archive"
updated_at: 2026-07-15
---

# 炼丹炉归档文档索引

归档文档只作为历史和决策脉络参考，不作为当前执行事实源。当前 SoT 见 [docs/README.md](<../README.md>)、`PROGRESS.md`；已完成商业化清理计划见 [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>)（executed-reviewed-pass）。历史 harness contract 路径（如 `.codex/contracts/active.md`）仅作史料指针，不保证仍存在于本仓库。

| 文档 | 当前替代来源 |
|---|---|
| [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) | [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) + `PROGRESS.md`（executed-reviewed-pass） |
| [Alchemy Furnace](<./Alchemy Furnace.md>) | [Furnace Agent Architecture](<../Furnace Agent Architecture.md>) |
| [Furnace Ultimate Architecture](<./Furnace Ultimate Architecture.md>) | [Furnace Agent Architecture](<../Furnace Agent Architecture.md>) |
| [Furnace Protocols](<./Furnace Protocols.md>) | [Furnace Agent Architecture](<../Furnace Agent Architecture.md>) §9 |
| [Furnace Material Scaling](<./Furnace Material Scaling.md>) | [Furnace Evolution Mechanics](<../Furnace Evolution Mechanics.md>) |
| [Furnace Material State Model](<./Furnace Material State Model.md>) | [Furnace Evolution Mechanics](<../Furnace Evolution Mechanics.md>) |
| [Furnace Incremental Compile Plan](<./Furnace Incremental Compile Plan.md>) | [Furnace Evolution Mechanics](<../Furnace Evolution Mechanics.md>) |
| [architecture_optimization_v2](<./architecture_optimization_v2.md>) | `PROGRESS.md` + current LLM backend implementation |
| [Furnace Product Shell Plugin](<./Furnace Product Shell Plugin.md>) | [Furnace Product Shell](<../Furnace Product Shell.md>) |
| [Furnace Product Shell Runtime Plan](<./Furnace Product Shell Runtime Plan.md>) | [Furnace Product Shell](<../Furnace Product Shell.md>) + [Furnace Runtime Operations](<../Furnace Runtime Operations.md>) |
| [product_shell_ui_v3_review](<./product_shell_ui_v3_review.md>) | [Furnace Product Shell](<../Furnace Product Shell.md>) |
| [Furnace Next Direction P0-P3](<./Furnace Next Direction P0-P3.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) + Scorecard |
| [Furnace Next Direction P4](<./Furnace Next Direction P4.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) + `PROGRESS.md` |
| [Furnace Product UX Assessment](<./Furnace Product UX Assessment.md>) | [Furnace Product Shell](<../Furnace Product Shell.md>) |
| [AGOS-9-Execution-Plan](<./AGOS-9-Execution-Plan.md>) | [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) + `PROGRESS.md` |
| [Furnace AgentOS Completion Plan](<./Furnace AgentOS Completion Plan.md>) | [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) + `PROGRESS.md` |
| [Furnace Agent OS Slimdown Plan](<./Furnace Agent OS Slimdown Plan.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) + [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) |
| [Furnace Next Direction Post-P4](<./Furnace Next Direction Post-P4.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) + [Furnace Product Shell](<../Furnace Product Shell.md>) + [Furnace Runtime Operations](<../Furnace Runtime Operations.md>) |
| [deepseek-comprehensive-evaluation-2026-05-03](<./deepseek-comprehensive-evaluation-2026-05-03.md>) | [Furnace Runtime Operations](<../Furnace Runtime Operations.md>) + [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) |
| [Furnace Cleanup Commercial Audit Plan 2026-07](<./Furnace Cleanup Commercial Audit Plan 2026-07.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) + [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) |
| [Furnace Residual Clearance Plan 2026-07](<./Furnace Residual Clearance Plan 2026-07.md>) | [Furnace Commercial Grade Cleanup Plan 2026-07](<./Furnace Commercial Grade Cleanup Plan 2026-07.md>) |
| [Furnace AOS-003 Compat Shim Audit](<./Furnace AOS-003 Compat Shim Audit.md>) | [AGENTS.md](<../../AGENTS.md>) 架构清理定案；纯 facade 已清除 |
| [Furnace Post-AGOS Risk Plan](<./Furnace Post-AGOS Risk Plan.md>) | [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>) + `PROGRESS.md` |
| [Furnace-90-Plus-Context-Provenance-Hardening-Plan](<./Furnace-90-Plus-Context-Provenance-Hardening-Plan.md>) | [Furnace Runtime Operations](<../Furnace Runtime Operations.md>) + [AGOS-9-Scorecard](<../AGOS-9-Scorecard.md>)；四项 hardening 已落地 |
| [AGOS-9-Dogfood-Proof-Runbook](<./AGOS-9-Dogfood-Proof-Runbook.md>) | `scripts/run_dogfood_maturity.sh` + systemd dogfood maturity harness 已删；AGOS-9 maturity gate 逻辑以 Scorecard 为准 |
| [AGOS-9-Investing-Preflight-Runbook](<./AGOS-9-Investing-Preflight-Runbook.md>) | `scripts/investing_dogfood_preflight.sh` 已删；新 investing 上线预检走 `aiwiki advanced ...` 路径 |
| [Furnace Investing Dogfood Plan](<./Furnace Investing Dogfood Plan.md>) | 老 investing 协议 plan，被 Post-Cleanup Audit + Investing Demo Pack Spec 取代 |
| [Furnace Product Shell UX Test Checklist](<./Furnace Product Shell UX Test Checklist.md>) | [Furnace Product Shell](<../Furnace Product Shell.md>)（Desktop-only）已为现行事实；UX 验证通过 `bash scripts/verify.sh smoke` + acceptance 17 fixture 覆盖 |
| [Furnace-Optional-Deps-Matrix](<./Furnace-Optional-Deps-Matrix.md>) | 可选包矩阵被 acceptance-only verify + `tests/fixtures/` 兑现；动态依赖通过把 `failed-llm` 等 hint 写到 receipts，矩阵本体的 SoT 角色已弱化 |
| [Furnace Agentic Debt Autopilot](<./Furnace Agentic Debt Autopilot.md>) | autopilot 在 2026-06 dogfood proof 后无新推进；`scripts/dogfood_maturity_gate.py` 已删；Scorecard / PROGRESS 当前已不依赖 autopilot 路径 |
| [Furnace Market Scan 2026Q2](<./Furnace Market Scan 2026Q2.md>) | 季度对标（2026 Q2）已过；与活跃 shipped-feature 一线不一致，史料保留 |
| [Furnace RuntimeClient Mobile Companion Design](<./Furnace RuntimeClient Mobile Companion Design.md>) | 移动 companion implemented-slice 已交付；无独立 iOS 商店包（产品边界），进一步产品形态以后另起 plan |
| [Furnace First-Principles Evaluation Report 2026-07](<./Furnace First-Principles Evaluation Report 2026-07.md>) | [Post-Cleanup Audit](<../Furnace Post-Cleanup Audit and Next Direction 2026-07.md>) + Scorecard |
| [plans/](<./plans/>)（W1–W9、ingest-dedup、audit remediation 等） | 已完成执行计划；在途契约见 `docs/specs/2026-07-20-report-delete-provenance-gc.md` |
| [specs/](<./specs/>)（freeform-ask、compounding、ingest-dedup） | 已落地原则/功能规格史料 |
