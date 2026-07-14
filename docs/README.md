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
| [Furnace Cleanup Commercial Audit Plan 2026-07](<./Furnace Cleanup Commercial Audit Plan 2026-07.md>) | **当前清理 / 商业审计 / Obsidian 全平台评估执行计划**：Wave A/B/C、可售卖边界、Mac vs iPad/iOS |

## Direction context（非当前执行 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Next Direction Post-P4](<./Furnace Next Direction Post-P4.md>) | Post-P4 方向史料；执行以 Scorecard + Cleanup Plan + `PROGRESS.md` 为准 |
| [AGOS-9-Execution-Plan](<./AGOS-9-Execution-Plan.md>) | AGOS 执行历史；release 口径以 Scorecard 为准 |
| [Furnace AgentOS Completion Plan](<./Furnace AgentOS Completion Plan.md>) | AOS-C1..C8 完成记录 |
| [Furnace Agent OS Slimdown Plan](<./Furnace Agent OS Slimdown Plan.md>) | broad slimdown campaign 已结束；后续只做 targeted seam |

## Archived（已 superseded / 已完成，保留作史料）

见 [docs/archive/README.md](<./archive/README.md>)。

本轮新增归档：
- [Furnace Next Direction P0-P3](<./archive/Furnace Next Direction P0-P3.md>) → superseded by `Furnace Next Direction Post-P4`
- [Furnace Next Direction P4](<./archive/Furnace Next Direction P4.md>) → P4-1~15 已完成，保留 dogfood F-fix 史料
- [Furnace Product UX Assessment](<./archive/Furnace Product UX Assessment.md>) → M-UX.1 已落地，当前 Product Shell 事实以 `Furnace Product Shell` 为准

## 阅读顺序

1. 先看 [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) 建立世界观。
2. 再看 [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) 建立契约与实现边界。
3. 需要操作本机自动化时看 [Furnace Runtime Operations](<./Furnace Runtime Operations.md>)。
4. 当前清理 / 商业 / 全平台边界看 [Furnace Cleanup Commercial Audit Plan 2026-07](<./Furnace Cleanup Commercial Audit Plan 2026-07.md>) 和 `PROGRESS.md`。
5. 需要看 Product Shell 时再看 [Furnace Product Shell](<./Furnace Product Shell.md>)（Desktop-only；iPad/iOS 见 Cleanup Plan §3）。
6. 历史方向与 AGOS 执行记录见上方 Direction context，不作为当前执行 SoT。

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
```
