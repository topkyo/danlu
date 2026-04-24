---
title: "输出面板"
kind: "dashboard"
---

# 输出面板

`output/` 是查询产物的落点，在你决定是否回流前，它们先停在这里。

## 输出区域

- `output/reports/`：markdown 报告
- `output/slides/`：Marp 幻灯片
- `output/figures/`：图表 brief 和图像导向输出
- `output/lint/`：deterministic / semantic lint 报告

## 审阅模式

1. 先看最新输出。
2. 检查引用是否确实回到了 `wiki/sources/`。
3. 如果值得长期保留，再用 `file-back` 移入 `wiki/derived/`、`wiki/decisions/` 或 `wiki/judgments/`。

## 搜索

- Obsidian 左侧预置搜索：`path:"output/reports" OR path:"output/slides" OR path:"output/figures" OR path:"output/lint"`
