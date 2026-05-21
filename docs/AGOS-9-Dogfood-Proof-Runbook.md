# AGOS-9 线上 Dogfood 证明运行手册

> 解除 [AGOS-9-Scorecard.md](./AGOS-9-Scorecard.md) 发布门禁：连续 3 个 UTC 日的 maturity receipt + knowledge compounding 样本。

## 前置条件

- Vault：`/home/tim/danlu/炼丹炉`（或 `AIWIKI_DOGFOOD_VAULT`）
- 为显式 `run-ask` 配置 LLM 凭据（无跨 backend fallback）
- 可选：`AIWIKI_INSTALL_DOGFOOD_MATURITY=1` 启用 systemd timer

## 每日循环（3 个 UTC 日）

```bash
export AIWIKI_DOGFOOD_VAULT=/home/tim/danlu/炼丹炉
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
| 笔记 | `aiwiki drop note --title "..." --body "..."` |
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
python3 scripts/dogfood_maturity_gate.py --root "$AIWIKI_DOGFOOD_VAULT" summarize --recent 3
```

- `operational_maturity.status=pass`
- `consecutive_days=true`（3 个不同 UTC 日）
- `knowledge_compounding_proof.status=pass`
- 无占位式 LLM success artifact

## Wall-clock 说明

第 2–3 日的 receipt 需要真实日历时间；脚本无法模拟连续日。
