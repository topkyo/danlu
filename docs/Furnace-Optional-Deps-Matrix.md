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
| `opencode-api` | `AIWIKI_OPENCODE_API_KEY` 或 `AIWIKI_LLM_API_KEY` |
| `nvidia-nim-api` | env 或 `~/.aiwiki-secrets/nvidia-nim.env` 中的 NIM API key |
| `codex-cli` | PATH 上有 `codex` 二进制 |
| `claude-cli` | PATH 上有 `claude` 二进制 |
| `copilot-cli` | PATH 上有 `copilot` 二进制 |

## 凭据 SoT

- CLI/dogfood：`~/.aiwiki-secrets/<provider>.env`（权限 600）
- Product Shell：插件 `data.json`（本地、不跟踪）
- 切勿将 key 提交到 git

## 遥测

- LLM 运行：`aiwiki llm-telemetry --limit N`
- Execution receipt：`aiwiki backend-telemetry --limit N`
- 探测 vs 运行：`llm-check --probe` 与运行遥测分离

## 保留策略

见 [Furnace Runtime Operations.md](./Furnace%20Runtime%20Operations.md) AGOS-008 章节。
