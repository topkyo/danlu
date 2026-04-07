---
title: "aiwiki 首页"
kind: "dashboard"
---

# aiwiki 首页

这个 vault 把 Obsidian 当作 `aiwiki` 的前端。

`aiwiki` 负责 ingest、compile、ask、lint、provenance 和自动化；Obsidian 负责浏览本地目录树和检查管线产物。

## 快速入口

- [[wiki/indexes/Raw Inbox|原料收件箱]]
- [[wiki/indexes/Wiki Hub|知识中枢]]
- [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- [[wiki/indexes/machine-memory|机器记忆]]
- [[wiki/indexes/graph-health|图谱健康]]
- [[wiki/indexes/drift-report|漂移报告]]
- [[wiki/indexes/repair-backlog|修复待办]]
- [[wiki/indexes/review-queue|审阅队列]]
- [[schema/index|运行时规则]]
- [[wiki/indexes/Outputs|输出面板]]
- [[wiki/indexes/Search Presets|搜索预设]]

## 目录说明

- `raw/inbox/`：新投喂的来源笔记和直接丢进来的原料
- `raw/assets/`：采集时保存的 PDF、图片和页面附件
- `schema/`：运行时 ingest、引用、冲突、审阅、回流规则
- `.aiwiki/state/`：manifest、机器记忆状态和历史
- `.aiwiki/state/nightly-health.json`：最新 nightly 健康快照
- `.aiwiki/cache/`：图谱导出和可重建的机读侧产物
- `wiki/sources/`：每个 raw 条目对应一页编译后的来源页
- `wiki/indexes/`：看板、索引、状态页和操作笔记
- `wiki/decisions/` 与 `wiki/judgments/`：显式决策层和判断层
- `wiki/derived/`：回流后的报告和派生笔记
- `output/`：报告、幻灯片、图表和 lint 结果

## 工作方式

1. 把原料丢进 `raw/inbox/`，或用 `drop-*` 入口导入。
2. 让 watcher 自动编译来源页并刷新 lint / 索引结果。
3. 定期跑 `nightly` 或 `run-nightly`，生成修复待办。
4. 在 Obsidian 里主要看 `wiki/sources/`、`wiki/indexes/review-queue.md`、`wiki/indexes/repair-backlog.md` 和 `output/`。
5. 把高价值输出回流，并显式审阅 decision/judgment 页面。

## 备注

- 在 Obsidian 里新建笔记时，默认会落到 `raw/inbox/`。
- 在 Obsidian 里新建附件时，默认会落到 `raw/assets/`。
- 左侧预置搜索页签已经按 `raw`、`wiki`、`output` 分好范围。
