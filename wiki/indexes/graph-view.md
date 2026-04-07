---
title: "图谱视图"
kind: "dashboard"
---

# 图谱视图

这里是炼丹炉的人用图谱入口，负责把 machine memory 的几类图相关页面收拢起来。

## 先看哪里

- [机器记忆](./machine-memory.md)：看 term index、digest、动作/提案数量
- [机器记忆拓扑](./machine-memory-topology.md)：看 hub、Mermaid 拓扑切片
- [图谱健康](./graph-health.md)：看 component、isolated/singleton/bridge 信号
- [漂移报告](./drift-report.md)：看最近一次 machine-memory 结构变化
- [概念质量](./concept-quality.md)：看图谱问题如何传导到 concept rewrite
- [本地图谱 HTML](../../output/graph/machine-memory.html)：直接看可视化图谱产物

## 怎么读

1. 先看 component、hub 和 drift 是否稳定。
2. 再看 link suggestion、action queue 和 repair proposal。
3. 最后回到具体 `wiki/concepts/` 或 `wiki/sources/` 页面处理。
4. 需要真正看图时，优先打开 `output/graph/machine-memory.html`。

## 边界

- 这里展示的是 `aiwiki` 的 machine-memory 视角，不等于 Obsidian 自带的 Graph View。
- Obsidian Graph 更适合看笔记链接；这里更适合看知识编译后的机读层状态。
