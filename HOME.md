---
title: "炼丹炉工作台"
kind: "dashboard"
---

# 炼丹炉

这里是炼丹炉在 Obsidian 里的产品入口。默认从主区的 Product Shell 开始：投料、提问、看 Today、打开报告；其他治理和调试入口收在 Advanced。

## 日常路径

1. 在 Product Shell 输入框里投 URL / 文件 / 图片，或直接问一个问题。
2. 看 Today：报告点 `Open`，审阅点 `Open Review`，命令先 `Copy command`。
3. 把有价值的报告回流为判断、决策或金丹。
4. 需要排障时再展开 Advanced；不要先从目录结构开始工作。

## 首屏模型

- 输入端：Ask / Drop / Capture Note
- 输出端：Today / Today's Reports / Previous Reports
- 高级入口：Review、Execution、Recent Runs、Metrics、LLM health

## 关键入口

- [[README|使用说明]]
- [[wiki/indexes/furnace-center|炉心面板索引]]
- [[wiki/indexes/Outputs|输出面板]]
- [[wiki/indexes/judgment-assets|判断资产]]
- [[docs/Furnace Product Shell|Product Shell 设计]]
- [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]]
- [[docs/Furnace Evolution Mechanics|进化机制]]
- [[docs/Furnace Elixir|金丹机制]]

## 备用命令

```bash
./scripts/aiwiki-launcher.sh shell-status
./scripts/aiwiki-launcher.sh compile
./scripts/aiwiki-launcher.sh ask "总结今天的关键变化" --format report
./scripts/aiwiki-launcher.sh nightly
```

写操作遵守单写约束：不要同时在 Obsidian 和终端里各跑一个 `compile / nightly / apply / revert`。
