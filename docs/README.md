---
title: "炼丹炉架构文档索引"
kind: "index"
status: "active"
updated_at: 2026-07-15
---

# 炼丹炉架构文档索引

## Active（当前 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) | **终局架构 SoT**：loop-first agent 模型、persistent planes、L1/L2/L3 自主权红线 |
| [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) | **实现契约 SoT**：heavy/light alchemy、active corpus、金丹生命周期、L3 proposal |
| [Furnace Product Shell](<./Furnace Product Shell.md>) | **Obsidian Product Shell SoT**：一个输入端 + 一个输出端 + Advanced 抽屉；**Desktop-only** |
| [Furnace Runtime Operations](<./Furnace Runtime Operations.md>) | **运行手册 SoT**：watcher、确定性 nightly、显式 LLM ask、universal drop plan/execute、四 API 后端与 fail-closed 策略 |
| [AGOS-9-Scorecard](<./AGOS-9-Scorecard.md>) | **AgentOS 评分与 release gate SoT**：证据分层、blocking gate、本地 release 口径 |
| [Furnace Elixir](<./Furnace Elixir.md>) | 金丹机制产品思路 thesis（accepted） |
| [INSTALL](<./INSTALL.md>) | **安装指南**：源码安装 + `pip install -e .` 预览路径；PyPI 正式发布待定 |
| [USER_GUIDE](<./USER_GUIDE.md>) | **用户指南**：日常 drop（含 plan/万能 payload）/ compile / ask / review 路径 |
| [DEVELOPER](<./DEVELOPER.md>) | **开发者指南**：owner map、verify targets、LLM/自动化细节 |
| [commercial/PRICING](<./commercial/PRICING.md>) | 商业定价与 SKU（首发仅询价、无公开标价） |
| [commercial/EULA](<./commercial/EULA.md>) | 商业许可条款草案与书面流程指针 |
| [commercial/BOUNDARIES](<./commercial/BOUNDARIES.md>) | 开源版 vs 商业版边界 + 商业 license 获取 |
| [commercial/PRIVACY](<./commercial/PRIVACY.md>) | local-first 隐私与 egress 声明 |
| [commercial/SUPPORT](<./commercial/SUPPORT.md>) | 支持通道与响应预期 |
| [commercial/COMPARE](<./commercial/COMPARE.md>) | 与常见知识工具对照 |
| [LICENSE](<../LICENSE>) | AGPL-3.0 / Commercial Dual License |
| [CHANGELOG](<../CHANGELOG.md>) | 版本变更记录 |

## Active Plans（阶段性，完成后归档）

| 文档 | 角色 |
|---|---|
| [Furnace Post-Cleanup Audit and Next Direction 2026-07](<./Furnace Post-Cleanup Audit and Next Direction 2026-07.md>) | **当前执行计划**：cleanup 后再审计报告 + Commercial Go-Live WS1–WS6 |
| [W2 Compounding Rank + Suggest plan](<./plans/2026-07-18-w2-compounding-rank-suggest.md>) | **已完成**：ranking / `used_refs` / 稀缺 `compound_suggest` + Today CTA（2026-07-18） |
| [W3 Governance Side-Cuts plan](<./plans/2026-07-18-w3-governance-side-cuts.md>) | **已完成**：删除 AgentOS governance CLI；保留 alchemy min-chain / compile / lint / ask / review-page（2026-07-18） |
| [W6 Compounding Gap Close plan](<./plans/2026-07-18-w6-compounding-gap-close.md>) | **已完成**：query cache elixir、锁 LLM compile/lint 侧门、Shell dead hooks + Today 收窄、Active docs 收尾（2026-07-18） |
| [Audit Remediation 2026-07-19](<./plans/2026-07-19-audit-remediation.md>) | **已执行**：`--protocol` 死命令、Chromium SSRF 默认关、DEVELOPER/Scorecard 刷新、graph facade/manifest/docs gate；能力层后续见 `5d6bcef` |

> Commercial Grade Cleanup Plan 2026-07 已归档（`executed-reviewed-pass`），见下方 Archived。
> Investing Demo Pack（`delivered-fixture`）与 RuntimeClient Mobile Companion（`implemented-slice`）已交付规格，见下方 Delivered specs；残留 go-to-market 工作并入上表 Go-Live 计划。

## Delivered specs（已交付，非活跃执行）

| 文档 | 角色 |
|---|---|
| [Furnace Investing Demo Pack Spec](<./Furnace Investing Demo Pack Spec.md>) + [Demo Pack fixture](<../demos/investing-demo-pack/README.md>) | 商业 demo 规格与已交付 fixture（截图/录屏资产见 Go-Live WS3） |

## Direction context（非当前执行 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace First-Principles Evaluation Report 2026-07](<./Furnace First-Principles Evaluation Report 2026-07.md>) | **方向评估**：多 agent 全量扫描 + 开源 LLM-Wiki 对标 + 第一性原理建议；**不替代** Post-Cleanup 执行计划 |

历史方向与已完成执行计划已移入 [docs/archive/](<./archive/README.md>)；当前执行以 [Post-Cleanup Audit](<./Furnace Post-Cleanup Audit and Next Direction 2026-07.md>) + Scorecard + `PROGRESS.md` 为准。
`wiki/indexes/` 是 compile 生成的派生索引区；策略见 [wiki/indexes/README](<../wiki/indexes/README.md>)。

## Archived（已 superseded / 已完成，保留作史料）

见 [docs/archive/README.md](<./archive/README.md>)。

近期归档：
- [Furnace Commercial Grade Cleanup Plan 2026-07](<./archive/Furnace Commercial Grade Cleanup Plan 2026-07.md>) → **executed-reviewed-pass**；商业化清理 Waves A–D + Phase5/D4 已收口
- [Furnace Next Direction P0-P3](<./archive/Furnace Next Direction P0-P3.md>) → 历史上由 Post-P4 接续；当前执行以 Scorecard + `PROGRESS.md` 为准
- [Furnace Next Direction P4](<./archive/Furnace Next Direction P4.md>) → P4-1~15 已完成，保留 dogfood F-fix 史料
- [Furnace Product UX Assessment](<./archive/Furnace Product UX Assessment.md>) → M-UX.1 已落地，当前 Product Shell 事实以 `Furnace Product Shell` 为准
- [Furnace Next Direction Post-P4](<./archive/Furnace Next Direction Post-P4.md>) → 当前方向以 Scorecard + `PROGRESS.md` 为准
- [AGOS-9-Execution-Plan](<./archive/AGOS-9-Execution-Plan.md>) → release gate 以 Scorecard 为准
- [Furnace AgentOS Completion Plan](<./archive/Furnace AgentOS Completion Plan.md>) → 完成记录保留作史料
- [Furnace Agent OS Slimdown Plan](<./archive/Furnace Agent OS Slimdown Plan.md>) → 后续只按 Scorecard / 新计划做 targeted seam
- [Furnace-90-Plus-Context-Provenance-Hardening-Plan](<./archive/Furnace-90-Plus-Context-Provenance-Hardening-Plan.md>) → 已归档；context/provenance 口径以 Architecture + Scorecard 为准
- [deepseek-comprehensive-evaluation-2026-05-03](<./archive/deepseek-comprehensive-evaluation-2026-05-03.md>) → LLM/运行口径以 Runtime Ops + Scorecard 为准

## 阅读顺序

1. 先看 [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) 建立世界观。
2. 再看 [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) 建立契约与实现边界。
3. 需要操作本机自动化时看 [Furnace Runtime Operations](<./Furnace Runtime Operations.md>)。
4. 当前评分 / release gate 看 [AGOS-9-Scorecard](<./AGOS-9-Scorecard.md>)；**下一波执行**看 [Post-Cleanup Audit and Next Direction](<./Furnace Post-Cleanup Audit and Next Direction 2026-07.md>) 与 `PROGRESS.md`。
5. 已完成的商业化清理见 [archive/Furnace Commercial Grade Cleanup Plan 2026-07](<./archive/Furnace Commercial Grade Cleanup Plan 2026-07.md>)。
6. 商业 demo 讲法看 [Furnace Investing Demo Pack Spec](<./Furnace Investing Demo Pack Spec.md>)。
7. 需要看 Product Shell 时再看 [Furnace Product Shell](<./Furnace Product Shell.md>)（Desktop-only；iPad/iOS 不支持全功能）。
8. 历史方向与 AGOS/AOS 执行记录见 [archive](<./archive/README.md>)，不作为当前执行 SoT。

## 关系

```text
Furnace Agent Architecture  (终局世界观 / 架构 SoT)
         |
         | 实现契约
         v
Furnace Evolution Mechanics (heavy/light, corpus, elixir, L3 proposal)
         |
         | 运行与产品入口
         v
Furnace Runtime Operations + Furnace Product Shell (Desktop-only)
         |
         | 评分 / release gate
         v
AGOS-9-Scorecard + PROGRESS.md
         |
         | 下一波执行（审计 + go-live）
         v
Post-Cleanup Audit and Next Direction 2026-07
         |
         | 已归档 cleanup 史料
         v
Commercial Grade Cleanup Plan 2026-07 (archive)
         |
         | 已交付规格（非活跃执行）
         v
Investing Demo Pack Spec
```
