# 炼丹炉 Post-AGOS 风险计划

> Harness 可读 SoT，承接 [AGOS-9-Execution-Plan.md](./AGOS-9-Execution-Plan.md) 之后的 milestone。
> Track A 解除 9.0 发布阻塞；Track B 降低结构债。

## Track A — AGOS-9-BLOCKER

- 运行手册：[AGOS-9-Dogfood-Proof-Runbook.md](./AGOS-9-Dogfood-Proof-Runbook.md)
- 状态脚本：`bash scripts/agos9_dogfood_proof_status.sh`
- 门禁：`summarize --days 3` + compounding proof

## Track B — 风险 milestone（已实现）

| ID | 交付物 |
|----|--------|
| RISK-P1 | Receipt schema 校验 + maturity gate 内 legacy warn 计数 |
| RISK-P2A | 从 workflows 抽出 `runner/local_stats.py` |
| RISK-P2B | `protocol/library.py` + app_protocol shim |
| RISK-P2C | `memory/execution_surface_helpers.py` |
| RISK-P3 | `app_execution` → `render.paths` import 迁移 |
| RISK-P4 | `aiwiki-report-leaf` CSS + `schema/today-feed.json` |
| RISK-P5A-EXT | `backend-telemetry` CLI |
| RISK-P5B | [Furnace-Optional-Deps-Matrix.md](./Furnace-Optional-Deps-Matrix.md) |
| RISK-P6 | [analysis/F-Module-Owner-Map.md](./analysis/F-Module-Owner-Map.md) |

## 冻结清单

与 [Furnace Agent OS Slimdown Plan.md](./Furnace%20Agent%20OS%20Slimdown%20Plan.md) 一致，未变更。
