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

- 输入端：Ask / Drop / Capture Note
- 输出端：Today / Today's Reports / Previous Reports
- 更多工具：审阅、执行、运行记录、指标、LLM 状态

## 关键入口

- [[README|使用说明]]
- [[wiki/indexes/README|索引策略（compile 后生成面板页）]]

`wiki/indexes/` 下的炉心 / 审阅 / 判断资产等面板页由 `compile` 生成，不入库；先跑 compile 再打开。

## 备用命令

```bash
./scripts/aiwiki-launcher.sh shell-status
./scripts/aiwiki-launcher.sh compile
./scripts/aiwiki-launcher.sh ask "总结今天的关键变化" --format report
./scripts/aiwiki-launcher.sh nightly
```

写操作遵守单写约束：不要同时在 Obsidian 和终端里各跑一个 `compile / nightly / apply / revert`。

日常优先用 Product Shell；命令行只作备用。
