---
title: "炼丹炉架构文档索引"
kind: "index"
status: "active"
---

# 炼丹炉架构文档索引

## Active（当前 SoT）

| 文档 | 角色 |
|---|---|
| [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) | **终局架构 SoT**：loop-first agent 模型、persistent planes、L1/L2/L3 自主权红线 |
| [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) | **实现契约 SoT**：heavy/light alchemy、active corpus、金丹生命周期、L3 proposal |
| [Furnace Elixir](<./Furnace Elixir.md>) | 金丹机制产品思路 thesis（accepted） |

## Archived（已 superseded，保留作史料）

见 [docs/archive/](./archive/)：

- `Alchemy Furnace.md` → `Furnace Agent Architecture.md`
- `Furnace Ultimate Architecture.md` → `Furnace Agent Architecture.md`
- `Furnace Protocols.md` → `Furnace Agent Architecture.md` §9
- `Furnace Material Scaling.md` → `Furnace Evolution Mechanics.md` §2 / §3 / §5 / §6
- `Furnace Material State Model.md` → `Furnace Evolution Mechanics.md` §6
- `Furnace Incremental Compile Plan.md` → `Furnace Evolution Mechanics.md` §4 / §5
- `architecture_optimization_v2.md` → `PROGRESS.md`（执行真相源）
- `Furnace Product Shell Plugin.md` → `README.md` / `PROGRESS.md`（当前 Product Shell 事实）+ 归档史料
- `Furnace Product Shell Runtime Plan.md` → `README.md` / `PROGRESS.md`（当前 shell-runtime 事实）+ 归档史料
- `product_shell_ui_v3_review.md` → EP-024 UI 重构评估史料；核心 SoT 不引用，保留作历史参考

## 阅读顺序

1. 先看 [Furnace Agent Architecture](<./Furnace Agent Architecture.md>) 建立世界观。
2. 再看 [Furnace Evolution Mechanics](<./Furnace Evolution Mechanics.md>) 建立契约与实现边界。
3. 参考 [Furnace Elixir](<./Furnace Elixir.md>) 理解金丹产品思路。
4. 需要看 Product Shell 时再看对应 surface / runtime 文档。

## 关系

```
Furnace Agent Architecture  (终局世界观 / 架构 SoT)
         │
         │ 实现契约
         ▼
Furnace Evolution Mechanics (heavy/light, corpus, elixir, L3 proposal)
         │
         │ 金丹产品思路背书
         ▼
Furnace Elixir (thesis, accepted)
```
