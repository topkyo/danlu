---
title: "AGOS-9 线上 Dogfood 证明运行手册"
kind: "runbook"
status: "active"
updated_at: "2026-07-15"
---

# AGOS-9 线上 Dogfood 证明运行手册

> 解除 [AGOS-9-Scorecard.md](./AGOS-9-Scorecard.md) 发布门禁：连续 3 个 UTC 日的 maturity receipt + knowledge compounding 样本。

## 前置条件

- Vault：`$AIWIKI_DOGFOOD_VAULT`（或 `AIWIKI_DOGFOOD_VAULT`）
- 为显式 `run-ask` 与 maturity nightly 配置 LLM 凭据（无跨 backend fallback；release proof 禁用 deterministic nightly fallback）
- 可选：`AIWIKI_INSTALL_DOGFOOD_MATURITY=1` 启用 systemd timer

## 每日循环（3 个 UTC 日）

```bash
export AIWIKI_DOGFOOD_VAULT=$AIWIKI_DOGFOOD_VAULT
source .envrc.dogfood  # 可选加速器

# 每个 UTC 日一次（若已有 receipt 则跳过，除非 FORCE=1）
AIWIKI_DOGFOOD_MATURITY_FORCE=0 bash scripts/run_dogfood_maturity.sh

# 状态看板
bash scripts/agos9_dogfood_proof_status.sh
```

## 输入覆盖（live）

| 类型 | 命令示例 |
|------|----------|
| URL | `aiwiki drop url https://example.com` |
| Markdown / 文本材料 | `aiwiki drop markdown --title "..." --text "..."` |
| 仓库 | `aiwiki drop repo /path/to/repo` |
| PDF | `aiwiki drop pdf /path/to/report.pdf` |

## Compounding 证明

需要 `wiki/judgments/*.md`，以及一次新的 `run-ask` 报告（frontmatter 中 `source_files` 引用上述 judgment），并配有匹配的 execution receipt。

1. 投喂投资 PDF → compile
2. 确保 judgment 存在（file-back 或手动 wiki 页面）
3. `aiwiki run-ask --format report --direct "基于已有 judgment 复盘…"`
4. 验证：`dogfood_maturity_gate.py collect` → `knowledge_compounding_proof.status=pass`

## 通过标准

```bash
python3 scripts/dogfood_maturity_gate.py --root "$AIWIKI_DOGFOOD_VAULT" summarize --days 3
```

- `operational_maturity.status=pass`
- `consecutive_days=true`（3 个不同 UTC 日）
- `deterministic_only_runs=[]`（debug-only deterministic receipt 不计入 release proof）
- `knowledge_compounding_proof.status=pass`
- 无占位式 LLM success artifact

## Wall-clock 说明

第 2–3 日的 receipt 需要真实日历时间；脚本无法模拟连续日。

## 可选 systemd timer

验证期可安装 user-level timer 自动跑每日 receipt。若 LLM 配置保存在本机 `.envrc.dogfood`，只保存该文件路径，不复制或打印凭据：

```bash
AIWIKI_INSTALL_DOGFOOD_MATURITY=1 \
AIWIKI_DOGFOOD_MATURITY_ENVRC=/Users/ht/github/danlu/.envrc.dogfood \
AIWIKI_DOGFOOD_VAULT=$AIWIKI_DOGFOOD_VAULT \
bash scripts/install_user_service.sh
```

Timer 默认 `00:15 UTC` 运行；若当天已有 maturity receipt，`scripts/run_dogfood_maturity.sh` 会跳过，除非显式设置 `AIWIKI_DOGFOOD_MATURITY_FORCE=1`。
