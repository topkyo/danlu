---
title: "AGOS-9 Investing 预检运行手册"
kind: "runbook"
status: "active"
updated_at: "2026-07-15"
---

# AGOS-9 Investing 预检运行手册

> **性质**：P1-C 预检；验证 investing 链路可启动。**不等于** P0 三日 maturity 或 compounding pass。

## 与 P0 的边界

| 项 | 预检（本文） | P0 运营证明 |
|----|--------------|-------------|
| maturity receipt | 默认不写 | 连续 3 UTC 日 |
| compounding | 不验证 | 必须 pass |
| 投资 PDF 全链路 | 可选 smoke | 必须完整 |

## 前置

- Vault：`$AIWIKI_DOGFOOD_VAULT`（或 `AIWIKI_DOGFOOD_VAULT`）
- 可选：`source .envrc.dogfood`

## 命令

```bash
export AIWIKI_DOGFOOD_VAULT=$AIWIKI_DOGFOOD_VAULT
bash scripts/backend_probe_matrix.sh
bash scripts/investing_dogfood_preflight.sh
# 可选：写一条 note 并 compile
bash scripts/investing_dogfood_preflight.sh --smoke-drop-markdown
```

## 通过标准

- `llm-check --probe` 可读；默认只读记录 credential/DNS 缺口，`BACKEND_PROBE_STRICT=1` 时才要求至少一个 compatible backend；需落盘证据时显式 `BACKEND_PROBE_WRITE=1`
- `protocol-set investing` 成功
- `wiki/judgments/`、`schema/`、`prompts/ask.md` 存在

## 下一步（P0 gate 后）

见 [AGOS-9-Dogfood-Proof-Runbook.md](./AGOS-9-Dogfood-Proof-Runbook.md)。
