---
title: "炼丹炉架构文档索引"
kind: "index"
status: "active"
updated_at: 2026-07-14
---

# 炼丹炉架构文档索引

## Active（当前 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) | **终局架构 SoT**：loop-first agent 模型、persistent planes、L1/L2/L3 自主权红线 |
| [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) | **实现契约 SoT**：heavy/light alchemy、active corpus、金丹生命周期、L3 proposal |
| [Furnace Product Shell](<./Furnace Product Shell.md>) | **Obsidian Product Shell SoT**：一个输入端 + 一个输出端 + Advanced 抽屉；**Desktop-only** |
| [Furnace Runtime Operations](<./Furnace Runtime Operations.md>) | **运行手册 SoT**：watcher、nightly、LLM worker、四 API 后端与 fail-closed 策略 |
| [AGOS-9-Scorecard](<./AGOS-9-Scorecard.md>) | **AgentOS 评分与 release gate SoT**：证据分层、blocking gate、本地 release 口径 |
| [Furnace Investing Dogfood Plan](<./Furnace Investing Dogfood Plan.md>) | investing 协议 dogfood flow 与 receipt index（历史 contract + 实跑索引） |
| [Furnace Market Scan 2026Q2](<./Furnace Market Scan 2026Q2.md>) | 2026Q2 市场对标与差异化判断 |
| [Furnace Elixir](<./Furnace Elixir.md>) | 金丹机制产品思路 thesis（accepted） |

## Active Plans（阶段性，完成后归档）

| 文档 | 角色 |
|---|---|
| [Furnace Residual Clearance Plan 2026-07](<./Furnace Residual Clearance Plan 2026-07.md>) | Cleanup residual：C1/C2 seam、Demo Pack fixture、VaultQueue companion |
| [Furnace Cleanup Commercial Audit Plan 2026-07](<./Furnace Cleanup Commercial Audit Plan 2026-07.md>) | **当前清理 / 商业审计 / Obsidian 全平台评估执行计划**：Wave A/B/C、可售卖边界、Mac vs iPad/iOS |
| [Furnace Investing Demo Pack Spec](<./Furnace Investing Demo Pack Spec.md>) + [Demo Pack fixture](<../demos/investing-demo-pack/README.md>) | **商业 demo 规格与已交付 fixture**：10 分钟知识复利故事、脱敏素材类型、receipt / judgment / elixir 路径和合规话术 |
| [Furnace RuntimeClient Mobile Companion Design](<./Furnace RuntimeClient Mobile Companion Design.md>) | **移动 companion implemented-slice**：RuntimeClient 三实现、VaultQueue 协议、desktop drain、Desktop-only 主插件边界 |

## Direction context（非当前执行 SoT）

历史方向与已完成执行计划已移入 [docs/archive/](<./archive/README.md>)；当前执行以 Scorecard + Cleanup Plan + `PROGRESS.md` 为准。
`wiki/indexes/` 是 compile 生成的派生索引区；策略见 [wiki/indexes/README](<../wiki/indexes/README.md>)。

## Archived（已 superseded / 已完成，保留作史料）

见 [docs/archive/README.md](<./archive/README.md>)。

近期归档：
- [Furnace Next Direction P0-P3](<./archive/Furnace Next Direction P0-P3.md>) → 历史上由 Post-P4 接续；当前执行以 Cleanup Plan + Scorecard 为准
- [Furnace Next Direction P4](<./archive/Furnace Next Direction P4.md>) → P4-1~15 已完成，保留 dogfood F-fix 史料
- [Furnace Product UX Assessment](<./archive/Furnace Product UX Assessment.md>) → M-UX.1 已落地，当前 Product Shell 事实以 `Furnace Product Shell` 为准
- [Furnace Next Direction Post-P4](<./archive/Furnace Next Direction Post-P4.md>) → 当前方向以 Cleanup Plan + Scorecard + `PROGRESS.md` 为准
- [AGOS-9-Execution-Plan](<./archive/AGOS-9-Execution-Plan.md>) → release gate 以 Scorecard 为准
- [Furnace AgentOS Completion Plan](<./archive/Furnace AgentOS Completion Plan.md>) → 完成记录保留作史料
- [Furnace Agent OS Slimdown Plan](<./archive/Furnace Agent OS Slimdown Plan.md>) → 后续只按 Cleanup Plan 做 targeted seam
- [deepseek-comprehensive-evaluation-2026-05-03](<./archive/deepseek-comprehensive-evaluation-2026-05-03.md>) → LLM/运行口径以 Runtime Ops + Scorecard 为准

## 阅读顺序

1. 先看 [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) 建立世界观。
2. 再看 [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) 建立契约与实现边界。
3. 需要操作本机自动化时看 [Furnace Runtime Operations](<./Furnace Runtime Operations.md>)。
4. 当前清理 / 商业 / 全平台边界看 [Furnace Cleanup Commercial Audit Plan 2026-07](<./Furnace Cleanup Commercial Audit Plan 2026-07.md>) 和 `PROGRESS.md`。
5. 商业 demo 讲法看 [Furnace Investing Demo Pack Spec](<./Furnace Investing Demo Pack Spec.md>)；移动端 companion 只看 [Furnace RuntimeClient Mobile Companion Design](<./Furnace RuntimeClient Mobile Companion Design.md>)。
6. 需要看 Product Shell 时再看 [Furnace Product Shell](<./Furnace Product Shell.md>)（Desktop-only；iPad/iOS 不支持全功能）。
7. 历史方向与 AGOS/AOS 执行记录见 [archive](<./archive/README.md>)，不作为当前执行 SoT。

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
         | 阶段性清理与商业边界
         v
Cleanup Commercial Audit Plan 2026-07
         |
         | 商业 demo / mobile companion 规格
         v
Investing Demo Pack Spec + RuntimeClient Mobile Companion Design
```
