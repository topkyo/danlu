---
title: "炼丹炉 Product Shell Runtime Plan"
kind: "plan"
status: "active"
---

# 炼丹炉 Product Shell Runtime Plan

这份文档回答的是：

**在真正开始做 Obsidian Product Shell Plugin 之前，`aiwiki` runtime 还缺哪些前台契约，以及应该按什么顺序补。**

它不是插件设计稿，也不是 sprint contract。

它是 `Product Shell` 落地前的 runtime 实施计划。

对应关系：

- Product Shell 设计稿：[[wiki/indexes/Furnace Product Shell Plugin|炼丹炉 Product Shell Plugin]]
- 当前这份：Product Shell 所依赖的 runtime contract 实施计划

## 背景

当前设计已经明确：

- `aiwiki` 是炉心
- Obsidian 插件是炉壳
- 插件不能直接把 `.aiwiki/state/*` 当成公共 UI 接口

这意味着，在写插件之前，runtime 必须先提供一个稳定的 shell-facing contract。

## 当前缺口

当前仓库还没有下面这些 runtime 入口：

- `output/control/shell-summary.json`
- `aiwiki shell-status`
- repo-local launcher

所以现在的问题不是“插件长什么样”，而是：

- 插件该读哪份稳定摘要
- 插件该调哪个稳定命令
- 插件该如何稳定调用本 repo 的 `aiwiki`

## 目标

先把 Product Shell 需要的 runtime 契约补齐，再开始插件实现。

这轮目标只做：

- summary contract
- shell-status command
- repo-local launcher
- 对应测试和闭环

## 非目标

- 不实现 Obsidian 插件本体
- 不重写 `nightly` 或 `compile` 的大聚合器
- 不把 `.aiwiki/state/*` 暴露成前端长期公共接口
- 不引入 daemon / service / server

## 计划项

### 1. `shell-summary.json`

新增：

- `output/control/shell-summary.json`

它是 Product Shell 默认读取的前台摘要文件。

建议字段：

- `contract_version`
- `generated_at`
- `generated_by`
- `active_protocol`
- `available_protocols`
- `llm_status`
- `review_backlog_counts`
- `aging_summary`
- `recent_outputs`
- `recent_receipts`
- `recent_runs`
- `links`
- `capabilities`

其中：

- `contract_version` 用于前后端协商
- `capabilities` 用于 graceful degradation

### 2. `aiwiki shell-status`

新增 CLI 命令：

- `aiwiki shell-status`

语义：

- 刷新 `output/control/shell-summary.json`
- stdout 返回同结构 JSON
- 只做只读摘要刷新
- 不推进 lifecycle / archive / execution 状态

### 3. Repo-local launcher

新增：

- `scripts/aiwiki-launcher.sh`

职责：

- 固化 repo-local `PYTHONPATH`
- 固化 `--root <repo>`
- 给 Product Shell 一个稳定调用入口

第一版明确按 repo-local 模式设计，不先做通用全局安装发现。

### 4. Recent Runs normalization

Product Shell 不直接读 hidden `runtime-history.jsonl`。

runtime 需要把最近运行历史整理进 `shell-summary.json`，至少覆盖：

- `query`
- `review`
- `archive-apply`
- `archive-revert`
- `knowledge-lifecycle-override`
- `nightly`

### 5. Graceful degradation

`shell-summary.json` 需要显式告诉前台：

- 当前支持哪些 Product Shell 能力
- 哪些页面或产物当前可打开
- 哪些摘要当前不可用

避免插件通过“文件在不在”去猜 runtime 能力。

## 推荐执行顺序

1. 先补 path helper 与 summary builder
2. 再补 `shell-status`
3. 再补 launcher
4. 再补测试
5. 最后才开始插件 scaffold

## 成功标准

- `output/control/shell-summary.json` 能稳定生成
- `aiwiki shell-status` 返回 machine-readable JSON
- summary 带 `contract_version` 与 `capabilities`
- summary 不依赖 hidden state 作为插件主读取契约
- launcher 能稳定调用 repo-local `aiwiki`
- `bash scripts/verify.sh` 通过

## 后续插件依赖

只有当上面这些 runtime contract 稳定后，插件 MVP 才值得开工。

插件 Phase 1 只依赖：

- `shell-summary.json`
- `aiwiki shell-status`
- repo-local launcher
- 现有 markdown/html 控制面与 output artifact

这就是 Product Shell 从“设计稿”进入“可实现工程”的分界线。
