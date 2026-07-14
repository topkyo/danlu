# 图谱视图

炼丹炉有两种图谱，用途不同，不要混用。

## 证据关系图（Obsidian 原生 Graph）

- **入口**：Obsidian 侧边栏 Graph；枢纽页 [证据关系总览](../evidence-graph.md)。
- **节点**：`output/reports`、`wiki/sources`、`raw/inbox`、`raw/assets`；协议下可有 `wiki/judgments`。
- **边**：报告 → 来源页 → 原料文件（wikilink）；**不含** `wiki/concepts`。
- **默认行为**：打开 Obsidian 侧边栏 Graph 即是证据关系图，**无需手动设置筛选**。证据链靠 **报告/来源/原料之间的 wikilink** 生成；`wiki/concepts` 页不再向来源/彼此输出可索引链接（避免概念节点被拉进图）。`.obsidian/graph.json` 另加 `-path:"wiki/concepts"` 作为兜底排除。

默认工作流仍然是先看 Today 和报告；需要看「报告连到哪些材料」时，直接打开 Obsidian Graph 或 [证据关系总览](../evidence-graph.md)。

## 机器记忆图谱（HTML）

- **入口**：[本地图谱 HTML](../../output/graph/machine-memory.html)
- **节点**：来源、**概念**、判断、金丹/决策等机器记忆资产。
- **边**：材料提到概念、材料支撑判断、概念相关、判断支持等（中文关系标签）。
- **维护**： [图谱健康](./graph-health.md)、[机器记忆](./machine-memory.md)、[概念质量](./concept-quality.md)

需要追溯报告背后的完整语义网络（含概念聚类）时，打开 HTML；日常证据链用 Obsidian 证据关系图即可。

## 怎么读

1. 先看报告和 Today，不把任何图谱当默认入口。
2. 需要「报告引用了哪些 PDF/笔记」→ Obsidian 证据关系图或 `wiki/evidence-graph.md`。
3. 需要「主题/概念如何串联多份材料」→ `output/graph/machine-memory.html`。
4. 只有做维护时，才回到 `wiki/sources/`、`wiki/judgments/`、`wiki/concepts/`、`wiki/elixirs/` 具体页面。

## 边界

- Obsidian Graph ≠ HTML 机器记忆图；两边节点集合 intentionally 不同。
- 概念页是机器记忆索引，不是原料副本；不应与 `raw/` 并列出现在证据关系图里。
- 图谱关系是辅助解释层；最终用户默认仍应看报告和少量关键确认。
- Linux 上若 HTML 在 Obsidian 内打开后跳到代理客户端，是系统 `text/html` 默认程序问题；在浏览器打开或改系统默认程序即可。
