---
title: "原料收件箱"
kind: "dashboard"
---

# 原料收件箱

这里是新原料进入系统的入口面。

## 适合放什么

- 网页剪藏内容
- `drop-url`、`drop-pdf`、`drop-image`、`drop-repo` 生成的来源笔记
- 需要进入正式来源层的手工 markdown 笔记

## 搜索

- Obsidian 左侧预置搜索：`path:"raw/inbox"`
- CLI 自动化入口：`watch` 或已安装的 `aiwiki-watch.service`

## 预期约束

- 这里的笔记应在 frontmatter 里保留 provenance
- 附件应放在 `raw/assets/`，不要和笔记混放
- watcher 会把这里的内容编译成 `wiki/sources/` 页面
