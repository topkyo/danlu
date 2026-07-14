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

> `bash scripts/backend_probe_matrix.sh` 默认只读；需要生成证据时显式 `BACKEND_PROBE_WRITE=1`。勿提交 secrets。默认无 compatible backend 只告警，`BACKEND_PROBE_STRICT=1` 时才 exit 1。

| 日期 (UTC) | 命令 | compatible | 备注 |
|------------|------|------------|------|
| 2026-05-21 | `backend_probe_matrix.sh` | 视本机凭据 | sandbox 无 DNS/凭据时多为 `requires_credential`；dogfood 实跑前在本机重探 |
