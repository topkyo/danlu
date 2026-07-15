---
title: "炼丹炉可选依赖矩阵"
kind: "reference"
status: "active"
updated_at: "2026-07-15"
---

# 炼丹炉可选依赖矩阵

> Operator SoT：local-first runtime 依赖（RISK-P5B）。

## Python 可选 import

| 功能 | 包 | 何时需要 |
|------|-----|----------|
| `drop url`（静态 HTML） | `beautifulsoup4` | HTTP 抓取解析 |
| `drop url`（动态页面） | `playwright` + 浏览器 | JS 重度页面 |
| 核心 runtime | 仅 stdlib | 始终 |

## LLM backend

| Backend | 要求 |
|---------|------|
| `deepseek-api` | `AIWIKI_DEEPSEEK_API_KEY` 或 `DEEPSEEK_API_KEY` |
| `opencode-api` | `AIWIKI_OPENCODE_API_KEY` 或 `AIWIKI_LLM_API_KEY` |
| `openai-api` | `AIWIKI_LLM_API_KEY` 或 `OPENAI_API_KEY` |
| `anthropic-api` | `AIWIKI_ANTHROPIC_API_KEY` 或 `ANTHROPIC_API_KEY` |

## 凭据 SoT

- CLI/dogfood：`~/.aiwiki-secrets/<provider>.env`（权限 600）
- Product Shell：插件 `data.json`（本地、不跟踪）
- 切勿将 key 提交到 git

## 遥测

- LLM 运行：`aiwiki advanced llm-telemetry --limit N`
- Execution receipt：`aiwiki advanced backend-telemetry --limit N`
- 探测 vs 运行：`aiwiki advanced llm-check --probe` 与运行遥测分离

## 保留策略

见 [Furnace Runtime Operations.md](./Furnace%20Runtime%20Operations.md) AGOS-008 章节。

## Backend 探测结果（operator 填写）

> 2026-07-15 scripts 清理：`scripts/backend_probe_matrix.sh` 已删除（属于耗时 auxiliary probe）。当前 backend 探测请在本机手动执行 `aiwiki advanced llm-check --probe`，结果写在本节。

| 日期 (UTC) | 命令 | compatible | 备注 |
|------------|------|------------|------|
| (历史 2026-05-21) | `backend_probe_matrix.sh`（已删除） | 视本机凭据 | sandbox 无 DNS/凭据时多为 `requires_credential` |
