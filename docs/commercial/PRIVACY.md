---
title: "炼丹炉隐私与数据流说明"
kind: "commercial"
status: "active"
updated_at: "2026-07-14"
related_docs:
  - docs/commercial/BOUNDARIES.md
  - docs/commercial/PRICING.md
  - demos/investing-demo-pack/COMPLIANCE.md
---

# 炼丹炉隐私与数据流说明

> 炼丹炉是 local-first 知识复利 runtime。本文件说明数据在哪里处理、什么会离开本机、什么不会离开本机。

## 1. Local-first 数据流

默认情况下，以下数据全部存放在用户指定的本地 vault 文件系统中：

| 数据类型 | 默认存放位置 | 是否离开本机 |
|----------|--------------|--------------|
| 原始输入材料 | `<vault>/raw/` | 否 |
| 结构化 wiki | `<vault>/wiki/` | 否 |
| 派生输出（报告、图表等） | `<vault>/output/` | 否 |
| 机器记忆与状态 | `<vault>/.aiwiki/` | 否 |
| Execution receipt / audit | `<vault>/.aiwiki/` 与 `<vault>/.aiwiki/state/execution-receipts/` | 否 |
| Product Shell 配置 | `<vault>/.obsidian/plugins/furnace-product-shell/data.json` | 否 |

> 炼丹炉没有中央服务器来存储用户 vault 内容。所有写入都发生在用户本地文件系统。

## 2. LLM 数据流

当用户显式配置并调用 LLM provider 时，以下数据会发送到用户配置的 provider：

- **Prompt**：用户问题、任务描述、指令模板。
- **Context**：被选中的 vault 内容片段（如 source pages、judgments、decisions），用于回答或生成。
- **Provider 元数据**：backend、model、base URL 等由用户配置决定。

炼丹炉支持的 provider 包括：

- `deepseek-api`
- `opencode-api`
- `openai-api`
- `anthropic-api`

> 具体哪些内容被发送，取决于用户运行的命令（如 `run-ask`）与所选上下文范围。炼丹炉不会 secretly 扩大上下文范围。

## 3. 凭据存放

- **API key 只在本机**：用户配置的 LLM API key 存储在本机，不进入 `aiwiki` 服务器，也不进入 git。
- **推荐存放方式**：
  - Product Shell 插件：`data.json`（本机未跟踪文件，不应提交到 git）。
  - CLI / dogfood：`~/.aiwiki-secrets/<provider>.env`，建议父目录权限 `700`、文件权限 `600`。
- **禁止行为**：API key 不得写入 README、测试 fixture、`.envrc.dogfood` 或任何 git-tracked 文件。

## 4. 网络访问场景

炼丹炉本身不会主动连接网络，除非用户显式触发以下功能：

| 功能 | 网络访问目标 | 触发条件 |
|------|--------------|----------|
| LLM provider API | 用户配置的 provider endpoint | 运行 `run-ask` 等显式 LLM 命令 |
| Web fetching（`drop-url`） | 用户指定的 URL | 执行 `aiwiki drop url <url>` |
| Notification webhook | 用户配置的 webhook URL | 用户自行配置并触发 |
| 包管理器 / git | PyPI、npm、GitHub 等 | 用户自行执行 `pip install`、`npm install`、`git clone` |

> 离线可用的功能限于本地文件读写与不需要外部模型/网络服务的确定性检查。

## 5. 不收集

炼丹炉**不**执行以下行为：

- 不 telemetry；
- 不 phone-home；
- 不上传 vault 内容到炼丹炉服务器；
- 不收集用户身份、设备指纹或使用行为数据；
- 不把用户数据用于模型训练或 fine-tuning。

> 注：用户配置的第三方 LLM provider 可能有自己的数据使用政策，请用户自行审阅 provider 条款。

## 6. 用户责任

- 用户负责妥善保管本机 API key 与 vault 文件备份。
- 用户负责选择可信的 LLM provider 并审阅其隐私政策。
- 在共享设备或多用户环境中，用户需自行设置文件权限，避免 vault 内容被他人读取。

## 7. 变更记录

- 2026-07-14：初版，从 `demos/investing-demo-pack/COMPLIANCE.md` §LLM data flow 迁入并泛化为产品级隐私说明。
