---
title: "搜索预设"
kind: "reference"
---

# 搜索预设

这些查询和 Obsidian workspace 里预加载的搜索页签保持一致。

## 原料入口

```text
path:"raw/inbox"
```

## 编译知识层

```text
path:"wiki/sources" OR path:"wiki/indexes" OR path:"wiki/derived"
```

## 输出层

```text
path:"output/reports" OR path:"output/slides" OR path:"output/figures" OR path:"output/lint"
```

## 未补摘要

```text
"Pending LLM summary." path:"wiki/sources"
```

## 缺失溯源

```text
"Missing source page:" path:"output/lint"
```
