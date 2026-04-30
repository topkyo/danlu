---
title: "图谱视图"
kind: "dashboard"
---

# 图谱视图

这里是炼丹炉的人用关系图谱入口，负责把机器记忆里的“材料 → 判断 → 概念 → 决策”关系用中文收拢起来。

默认工作流仍然是先看报告；只有当你想追溯报告背后的证据链、判断来源或概念关系时，再打开这里。

## 先看哪里

- [本地图谱 HTML](../../output/graph/machine-memory.html)：直接看中文关系图谱
- [图谱健康](./graph-health.md)：看关系组、孤立来源、桥接概念、过载概念
- [机器记忆拓扑](./machine-memory-topology.md)：看 hub 和 Mermaid 拓扑切片
- [机器记忆](./machine-memory.md)：看 term index、digest、动作/提案数量
- [漂移报告](./drift-report.md)：看最近一次机器记忆结构变化
- [概念质量](./concept-quality.md)：看图谱问题如何传导到概念改写

## 怎么读

1. 先看报告和 Today，不把图谱当默认入口。
2. 需要追溯时打开 `output/graph/machine-memory.html`。
3. 按中文关系读图：材料提到概念、材料支撑判断、概念相关、判断支持、判断冲突、决策依据、因果关系。
4. 再回到具体 `wiki/sources/`、`wiki/judgments/`、`wiki/concepts/` 页面处理。

## 边界

- 这里展示的是 `aiwiki` 的机器记忆视角，不等于 Obsidian 自带的 Graph View。
- Obsidian Graph 更适合看笔记链接；这里更适合看知识编译后的证据、判断、概念和决策关系。
- 图谱关系是辅助解释层；最终用户默认仍应看报告和少量关键确认。
- Linux 上若 `output/graph/machine-memory.html` 在 Obsidian 内打开后跳到 Mihomo/Clash 等代理客户端，是系统把 `text/html` 默认程序绑给了它；在浏览器里打开或在系统设置里改默认程序即可。
