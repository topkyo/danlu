---
title: "炼丹炉工作台"
kind: "dashboard"
---

# 炼丹炉工作台

这里不是架构说明书，而是 `aiwiki` 在 Obsidian 里的日常入口。

你在这里主要做 4 件事：
- 投料
- 看状态
- 做查询
- 回流并审阅重要结论

## 最简流程

对人来说，只记住这 3 个地方就够了：

- 输入：`raw/`
- 输出：`output/`
- 沉淀：`wiki/`

如果展开一点，就是：

`raw/inbox/ -> wiki/sources + wiki/concepts + wiki/indexes -> output/ -> wiki/derived|decisions|judgments`

对应关系：

- 你把原料丢进 `raw/inbox/`，或用 `drop-*` 入口导入
- 系统把它编译到 `wiki/`
- 你从 `output/` 取报告、幻灯片、图表和 lint 结果
- 值得长期保留的结果，再回流到 `wiki/`

## 今日入口

- [[wiki/indexes/Raw Inbox|原料收件箱]]
- [[wiki/indexes/Wiki Hub|知识中枢]]
- [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- [[wiki/indexes/protocols|协议总览]]
- [[wiki/indexes/review-center|审阅中心]]
- [[wiki/indexes/graph-view|图谱视图]]
- [[wiki/indexes/Outputs|输出面板]]
- [[wiki/indexes/Search Presets|搜索预设]]

## 今日信号

- [[wiki/indexes/review-queue|审阅队列]]
- [[wiki/indexes/review-center|审阅中心]]
- [[wiki/indexes/repair-backlog|修复待办]]
- [[wiki/indexes/drift-report|漂移报告]]
- [[wiki/indexes/graph-health|图谱健康]]
- [[wiki/indexes/graph-view|图谱视图]]
- [[wiki/indexes/machine-memory|机器记忆]]
- [[schema/index|运行时规则]]
- [[schema/protocols/index|协议规则]]

## 日常循环

1. 把网页、PDF、图片、repo 或本地文件投进 `raw/inbox/`，或使用 `drop-*` 入口。
2. 让 watcher / compile / nightly 自动刷新 `wiki/`、`output/` 和状态页。
3. 在 `wiki/sources/`、`wiki/concepts/`、`wiki/indexes/` 里检查系统是否已经形成稳定知识。
4. 用 `ask` / `run-ask` 生成报告、幻灯片或图表 brief。
5. 把高价值结果 `file-back` 到 `wiki/derived/`、`wiki/decisions/`、`wiki/judgments/`，再进入审阅流。

## 现在去哪看

- 想确认新投料有没有进系统：看 [[wiki/indexes/Raw Inbox|原料收件箱]]
- 想看系统当前总览：看 [[wiki/indexes/Wiki Hub|知识中枢]]
- 想切换或查看当前协议：看 [[wiki/indexes/protocols|协议总览]]
- 想看 pending review：看 [[wiki/indexes/review-queue|审阅队列]]
- 想把 review / repair / aging 放到一个地方看：看 [[wiki/indexes/review-center|审阅中心]]，真正的本地审阅面板在 `output/review/review-center.html`
- 想看修复优先级：看 [[wiki/indexes/repair-backlog|修复待办]]
- 想看 retrieval / graph 是否健康：看 [[wiki/indexes/graph-health|图谱健康]] 和 [[wiki/indexes/machine-memory|机器记忆]]
- 想从统一入口看 machine-memory 图层：看 [[wiki/indexes/graph-view|图谱视图]]，真正的本地图谱产物在 `output/graph/machine-memory.html`
- 想看最终产物：看 [[wiki/indexes/Outputs|输出面板]]

## 路径职责

- `raw/inbox/`：原始材料和 ingest 生成的 capture notes
- `raw/assets/`：原始附件、页面图片、PDF、截图
- `wiki/sources/`：来源页
- `wiki/concepts/`：概念页
- `wiki/indexes/`：索引、状态、日志、漂移、图谱健康、审阅队列、修复待办
- `wiki/decisions/` 与 `wiki/judgments/`：高阶结论层
- `wiki/derived/`：回流后的派生 markdown
- `output/`：报告、幻灯片、图表和 lint 结果
- `schema/`：运行时规则
- `schema/protocols/`：领域协议覆盖层

## 使用边界

- Obsidian 是前端/IDE，不是编译器
- `aiwiki` 负责 ingest、compile、ask、lint、watch、nightly、provenance
- 原始证据留在 `raw/`
- 高价值综合沉到 `wiki/`
- 查询产物先出到 `output/`，确认后再回流

## 备注

- Obsidian 新建笔记默认落到 `raw/inbox/`
- Obsidian 新建附件默认落到 `raw/assets/`
- 如果你要理解整体结构，去看 [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- 如果你要看如何运行整个系统，去看 [README.md](./README.md)
