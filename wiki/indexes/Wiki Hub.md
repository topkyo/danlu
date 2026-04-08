---
title: "知识中枢"
kind: "dashboard"
---

# 知识中枢

这里是编译后的知识层。

## 主要区域

- `wiki/sources/`：摘要、溯源和来源级反向链接
- `wiki/indexes/`：库存页、状态页和操作看板
- `wiki/derived/`：回流后的报告、幻灯片和值得保留的派生笔记
- `wiki/decisions/` 与 `wiki/judgments/`：处于审阅流中的显式决策层和判断层
- `schema/`：ingest、引用、冲突、审阅、回流等运行时规则
- `schema/protocols/`：统一炉子的领域协议覆盖层
- `.aiwiki/state/`：给 agent 用的机器记忆状态和历史
- `.aiwiki/cache/`：图谱导出和可重建的机读索引

## 架构入口

- [[wiki/indexes/Alchemy Furnace|炼丹炉架构]]：`aiwiki` 的运行时架构
- [[wiki/indexes/Furnace Protocols|统一炼丹协议]]：一个炉子，多种领域协议
- [[wiki/indexes/protocols|协议总览]]：当前 active protocol 和可用协议库
- [[wiki/indexes/furnace-center|炉心面板]]：统一入口，先看今天该处理什么
- [[schema/index|运行时规则]]：compile、ask、lint 共同遵循的规则层
- [[schema/protocols/index|协议规则库]]：`general / investing / research` starter protocols
- [[wiki/indexes/review-center|审阅中心]]：把 review、aging、repair 和 concept rewrite 收到一起
- [[wiki/indexes/machine-memory|机器记忆]]：当前机器记忆摘要
- [[wiki/indexes/graph-view|图谱视图]]：machine-memory 的统一人读入口
- [[wiki/indexes/graph-health|图谱健康]]：当前图谱健康看板
- [[wiki/indexes/drift-report|漂移报告]]：最近一次结构漂移报告
- [[wiki/indexes/repair-backlog|修复待办]]：最近一次 nightly 修复队列
- [[wiki/indexes/review-queue|审阅队列]]：当前 decision/judgment 审阅队列

## 建议阅读顺序

1. 先从 `wiki/sources/` 里的来源页开始。
2. 需要看系统状态时，再看 `machine-memory`、`review-queue`、`repair-backlog`。
3. 再沿着索引页或 derived 页面继续跳转。
4. 配合右侧的 backlinks / outgoing links 浏览上下文。

## 搜索

- Obsidian 左侧预置搜索：`path:"wiki/sources" OR path:"wiki/indexes" OR path:"wiki/derived"`
