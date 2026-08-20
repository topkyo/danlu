---
title: "炼丹炉工作台"
kind: "dashboard"
---

# 炼丹炉

这里是炼丹炉在 Obsidian 里的产品入口。默认从主区的 Product Shell 开始：投料、提问、看 Today、打开报告；其他治理和调试入口收在更多工具。

## 日常路径

1. 在 Product Shell 输入框里投 URL / 文件 / 图片，或直接问一个问题。
2. 看 Today：报告点 `Open`，审阅点 `Open Review`，命令先 `Copy command`。
3. 把有价值的报告回流为判断、决策或金丹。
4. 需要排障时再展开更多工具；不要先从目录结构开始工作。

左侧文件树是用户视图：日常只需要报告。`raw/wiki/schema` 和 `output/` 的其他产物仍存在，但默认不作为用户入口。

## 首屏模型

- Product Shell（读 `output/control/shell-summary.json`）：输入端 Ask / Drop / Capture Note；输出端 Today / Today's Reports / Previous Reports；审阅、运行记录、指标、LLM 状态收在更多工具。
- 炉心面板是 compile 生成的 Markdown 首屏（今天做什么 / 最近输出 / 快速跳转）；治理细节去审阅中心、修复待办等专页，不再堆在炉心里。

## 关键入口

- [[README|使用说明]]
- [[wiki/indexes/README|索引策略（含炉心面板等页面清单；先在 Product Shell 跑一次 Compile 再打开）]]

写操作遵守单写约束：同一时刻只保留一个写入口，不要在 Obsidian 和终端里同时跑 compile / nightly 这类写入任务。

日常用 Product Shell；终端 `aiwiki` CLI 留给脚本与自动化（用法见 [docs/USER_GUIDE.md](./docs/USER_GUIDE.md)）。
