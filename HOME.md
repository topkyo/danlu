---
title: "炼丹炉工作台"
kind: "dashboard"
---

# 炼丹炉工作台

这里是炼丹炉在 Obsidian 里的日常入口。底层 runtime 仍然叫 `aiwiki`，但你日常使用面对的是“炼丹炉”这个系统。

- 原料放哪
- 今天看哪
- 结果去哪
- 现在先做什么

## 最简模型

只记住这 3 个地方：

- 输入：`raw/`
- 沉淀：`wiki/`
- 输出：`output/`

展开就是：

`raw/inbox/ -> wiki/sources + wiki/concepts + wiki/indexes -> output/ -> wiki/derived|decisions|judgments`

## 今天先做什么

1. 把新材料放进 `raw/inbox/`，或用 `drop-*` 导入。
2. 看 `furnace-center`、`review-queue`、`execution-center`，确认今天真正要处理什么。
3. 用 `ask / run-ask` 出报告、幻灯片或图表。
4. 把高价值结果 `file-back` 到 `wiki/derived / decisions / judgments`。
5. 用 `review`、`nightly` 和 `execution` 维持系统质量。

## 今日入口

- [[wiki/indexes/Raw Inbox|原料收件箱]]
- [[wiki/indexes/Wiki Hub|知识中枢]]
- [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- [[wiki/indexes/Furnace Ceiling Roadmap|上限路线图]]
- [[wiki/indexes/Furnace Ultimate Architecture|最终极形态]]
- [[wiki/indexes/furnace-center|炉心面板]]
- [[wiki/indexes/execution-center|执行中心]]
- [[wiki/indexes/execution-audit|执行审计]]
- [[wiki/indexes/agent-workbench|Agent Workbench]]
- [[wiki/indexes/cognitive-history|认知历史]]
- [[wiki/indexes/output-packs|输出 Pack 总览]]
- [[wiki/indexes/domain-pilots|领域 Pilot 总览]]
- [[wiki/indexes/protocols|协议总览]]
- [[wiki/indexes/review-center|审阅中心]]
- [[wiki/indexes/judgment-assets|判断资产]]
- [[wiki/indexes/graph-view|图谱视图]]
- [[wiki/indexes/Outputs|输出面板]]
- [[wiki/indexes/Search Presets|搜索预设]]

## 今日信号

- [[wiki/indexes/review-queue|审阅队列]]
- [[wiki/indexes/review-center|审阅中心]]
- [[wiki/indexes/execution-center|执行中心]]
- [[wiki/indexes/execution-audit|执行审计]]
- [[wiki/indexes/agent-workbench|Agent Workbench]]
- [[wiki/indexes/cognitive-history|认知历史]]
- [[wiki/indexes/output-packs|输出 Pack 总览]]
- [[wiki/indexes/domain-pilots|领域 Pilot 总览]]
- [[wiki/indexes/repair-backlog|修复待办]]
- [[wiki/indexes/rewrite-proposals|Rewrite 提案]]
- [[wiki/indexes/drift-report|漂移报告]]
- [[wiki/indexes/graph-health|图谱健康]]
- [[wiki/indexes/graph-view|图谱视图]]
- [[wiki/indexes/machine-memory|机器记忆]]
- [[schema/index|运行时规则]]
- [[schema/protocols/index|协议规则]]

## 现在去哪看

- 想看总控页：[[wiki/indexes/furnace-center|炉心面板]]
  本地 HTML：`output/control/furnace-center.html`
- 想看执行：[[wiki/indexes/execution-center|执行中心]]
  本地 HTML：`output/control/execution-center.html`
- 想看 apply / revert 历史：[[wiki/indexes/execution-audit|执行审计]]
  本地 HTML：`output/control/execution-audit.html`
- 想看审阅和 aging：[[wiki/indexes/review-center|审阅中心]]
  本地 HTML：`output/review/review-center.html`
- 想看图谱：[[wiki/indexes/graph-view|图谱视图]]
  本地 HTML：`output/graph/machine-memory.html`
- 想看领域协议现状：[[wiki/indexes/domain-pilots|领域 Pilot 总览]]
- 想看输出 pack：[[wiki/indexes/output-packs|输出 Pack 总览]]
- 想看判断资产：[[wiki/indexes/judgment-assets|判断资产]]
- 想看历史复查：[[wiki/indexes/cognitive-history|认知历史]]

## 路径职责

- `raw/inbox/`：原始材料和 capture notes
- `raw/assets/`：图片、附件、PDF、页面资源
- `wiki/sources/`：来源页
- `wiki/concepts/`：概念页
- `wiki/indexes/`：索引、状态、队列、健康页
- `wiki/decisions/`：决策页
- `wiki/judgments/`：判断页
- `wiki/derived/`：回流后的派生页面
- `output/`：报告、幻灯片、图表、lint
- `output/packs/`：review packs、decision memos、SOP drafts
- `output/pilots/`：各协议 pilot scorecards
- `schema/`：运行时规则
- `schema/protocols/`：领域协议

## 当前边界

- Obsidian 是前端，不是编译器
- 底层由 `aiwiki` 负责 ingest、compile、ask、lint、nightly、execution
- `raw/` 不被派生结论覆盖
- safe execution 只开放低风险动作
- 当前运行模型是 `single writer, many readers`

## 备注

- 新建笔记默认进 `raw/inbox/`
- 新建附件默认进 `raw/assets/`
- 详细运行说明看 [README.md](./README.md)
- 详细架构看 [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
