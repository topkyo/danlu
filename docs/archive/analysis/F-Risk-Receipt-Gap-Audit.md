# F — Execution Receipt 缺口审计

> 仅报告性质。补充 RISK-P1 receipt schema 校验（legacy 计数为 warn-only）。

## 权威写入点

- `src/aiwiki/execution/receipts.py::write_execution_receipt()` — 所有新 receipt 要求非空 `operation`、`status`、`target_file`。

## 已确认的 receipt 路径

| Operation | 模块 | 说明 |
|-----------|------|------|
| `run-ask` | `runner/workflows.py` | resume 完成时写入 success |
| `file-back` | `execution/ask.py` | target = output artifact |
| machine-memory apply | `execution/machine_memory_actions.py` | 批量与单条 |
| L3 apply/revert | `execution/l3_proposals.py` | hash-gated |
| alchemy lanes | `runner/alchemy.py` | Receipt-tier TX |

## Legacy 兼容（warn-only）

- JSON receipt 或 history 行中 `status` 为空时，maturity gate compounding 匹配器仍视为 success。
- maturity `collect` snapshot 输出 `legacy_empty_status_receipts`，用于弃用跟踪。

## 缺口（非阻塞）

- 部分旧 CLI 路径可能只写 history、无 JSON 镜像；通过 `execution/audit_reconciliation.py` 对账。
- 无匹配 receipt 的 UI 历史 artifact 仍从 Today 主 feed 过滤（TDA-001）。

## 后续硬化（延后）

- 仅对新 vault：当 `legacy_empty_status_receipts.count > 0` 时，将 maturity gate 从 warn-only 改为 fail。
