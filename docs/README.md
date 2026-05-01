---
title: "炼丹炉架构文档索引"
kind: "index"
status: "active"
updated_at: 2026-05-01
---

# 炼丹炉架构文档索引

## Active（当前 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) | **终局架构 SoT**：loop-first agent 模型、persistent planes、L1/L2/L3 自主权红线 |
| [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) | **实现契约 SoT**：heavy/light alchemy、active corpus、金丹生命周期、L3 proposal |
| [Furnace Product Shell](<./Furnace Product Shell.md>) | **Obsidian Product Shell SoT**：一个输入端 + 一个输出端 + Advanced 抽屉 |
| [Furnace Runtime Operations](<./Furnace Runtime Operations.md>) | **运行手册 SoT**：watcher、nightly、LLM worker、NV NIM fallback |
| [Furnace Next Direction Post-P4](<./Furnace Next Direction Post-P4.md>) | **当前方向 SoT**：Round 52 后的真实 gap、dogfood 和后续方向 |
| [Furnace Investing Dogfood Plan](<./Furnace Investing Dogfood Plan.md>) | investing 协议端到端 dogfood flow 与 receipt index |
| [Furnace Market Scan 2026Q2](<./Furnace Market Scan 2026Q2.md>) | 2026Q2 市场对标与差异化判断 |
| [Furnace Elixir](<./Furnace Elixir.md>) | 金丹机制产品思路 thesis（accepted） |

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
4. 继续开发时看 [Furnace Next Direction Post-P4](<./Furnace Next Direction Post-P4.md>) 和 `PROGRESS.md`。
5. 需要看 Product Shell 时再看 [Furnace Product Shell](<./Furnace Product Shell.md>)。

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
Furnace Runtime Operations + Furnace Product Shell
         |
         | 当前执行方向
         v
Furnace Next Direction Post-P4 + PROGRESS.md
```
