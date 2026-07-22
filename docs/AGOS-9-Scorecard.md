---
title: "AgentOS 9.0 Scorecard"
kind: "scorecard"
status: "active"
updated_at: "2026-07-22"
---

# AgentOS 9.0 Scorecard

> **SoT**：统一评分与 release gate 口径。  
> **两套门禁**：**Local Engineering Gate**（fixture + verify，可诚实宣称 engineering 就绪）vs **Live Dogfood Gate**（historical / not-yet，**不阻塞** Local Engineering）。  
> **执行计划史料**：[AGOS-9-Execution-Plan.md](./archive/AGOS-9-Execution-Plan.md)  
> **基线 tag**：`v0.3.0-agentos-baseline`  
> **2026-07-22 全量复评**：[`archive/Furnace Multi-Ruler Reassessment 2026-07-22.md`](./archive/Furnace%20Multi-Ruler%20Reassessment%202026-07-22.md)

## 评分原则

1. **Evidence-driven**：每维须有可检查 artifact 或命令。
2. **Proof 分层**：`historical` / `fixture` / `replay` / `live` — 不得混标 PASS。
3. **Blocking fail**：任一**该门禁** blocking gate 失败，该门禁不得宣称 ≥ 9.0。
4. **非目标不变**：hosted service、multi-user sync、heavy RAG、fine-tuning、隐式 cross-backend routing。

## 现行 verify gate（Local Engineering，2026-07-22 实测）

| 组件 | 数量 | 命令 |
|---|---:|---|
| Acceptance | **17** passed | `bash scripts/verify.sh acceptance` |
| LLM integration | **76** passed | `bash scripts/verify.sh llm-integration` |
| Product Shell Jest | **179** passed | `bash scripts/verify.sh product-shell-static` |
| 全量 | 7 步 | `bash scripts/verify.sh all` |
| Docs consistency | exit 0 | `bash scripts/docs_consistency_check.sh` |
| CI | exists | `.github/workflows/verify.yml` |

**不含**：旧 AOS-C8 的 2439 unit tests + coverage 92%（2026-07-15 已退役）；`dogfood_maturity_gate.py`、`agos9_release_audit.sh` 已删。

## 两套 Release Gate

| 门禁 | 测什么 | 可否宣称 ≥9.0 | Dogfood live blocking? |
|---|---|---|---|
| **Local Engineering** | verify / acceptance / Jest / path harden / docs SoT | 见下方加权 | **否** |
| **Live Dogfood** | 当前 vault 3-day maturity + compounding + receipt integrity | **否**（not-yet） | **是** |

### Local Engineering — 加权（2026-07-22 复评）

| 维度 | 权重 | 分 | 加权 |
|------|------|---:|-----:|
| Dogfood / fixture & historical | 20% | 8.9 | 1.780 |
| Product Shell | 12% | 9.3 | 1.116 |
| Runtime correctness | 15% | 9.4 | 1.410 |
| Planner / signal | 10% | 8.7 | 0.870 |
| LLM reliability | 12% | 9.0 | 1.080 |
| Governance | 13% | 9.1 | 1.183 |
| Maintainability | 8% | 9.0 | 0.720 |
| Docs SoT | 10% | 8.9 | 0.890 |
| **合计** | 100% | — | **9.05** |

**历史对照**：2026-07-18 ≈ **9.07**；2026-07-19 audit 漂移 ≈ **8.4**；2026-07-22 Ask sync 后回升至 **9.05**（架构净简化 + verify 全绿；Live 仍 not-yet）。

**并列尺子（非本表加权）**：Commercial Go-Live ≈ **7.8**（未达诚实可售 ≥8.0）；Ask 架构子尺 A/B 各 **8.0**。详见复评报告。

### Live Dogfood — 状态摘要（2026-07-22）

| 维度 | 分 | 说明 |
|------|---:|---|
| Dogfood / live | **7.0** | background 队列已清；近日 ask 全 `llm-success`；3-day natural maturity **not-yet** |
| 估算加权 | **~8.3** | 不得对外宣称 AgentOS 9.0 **live** |

## AOS-C8 史料（2026-05-24，frozen）

**historical only** — 不得标为当前 clean vault **live** PASS。

| 项 | 值 | 备注 |
|---|---|---|
| Full verify | PASS | 2439 unit + coverage 92% + acceptance 17 |
| Live dogfood 3-day | PASS | 2026-05-21/22/23 UTC |
| Compounding | PASS | AOS-C2/C8 |
| Release audit scripts | PASS | `agos9_release_audit.sh` 等 — **2026-07-15 已删** |
| Maturity script | PASS | `dogfood_maturity_gate.py` — **已删** |

**Post-cleanup 等价 gate**（现行）：`bash scripts/verify.sh all` + `docs_consistency_check.sh` + CI。

## 八维摘要（Local Engineering）

| 维度 | 权重 | 分 | Blocking? | 现行证据 |
|------|------|---:|---|---|
| Dogfood / fixture | 20% | 8.9 | no（live 维 blocking 在 Live gate） | acceptance **17** replay + AOS-C8 **historical** |
| Product Shell | 12% | 9.3 | yes | Jest **179** + sync `run-ask` 单飞 + Today-first |
| Runtime correctness | 15% | 9.4 | no | path harden + fail-closed LLM；无 background submit/resume |
| Planner / signal | 10% | 8.7 | no | internal modules；CLI 已删；acceptance replay |
| LLM reliability | 12% | 9.0 | no | llm-integration **76** + receipt 聚合 |
| Governance | 13% | 9.1 | yes | review-page / alchemy-revert / receipts；**无** L3 apply CLI / auto_adopt |
| Maintainability | 8% | 9.0 | no | 顶层 `app_*.py` = 0；Ask 路径净删 background |
| Docs SoT | 10% | 8.9 | yes | active docs 对齐；本轮刷新计数 |

> **AOS-C8 frozen**：2026-05 三天 live PASS 仍作 **historical** 证据；Local Engineering 用 fixture + historical 计 Dogfood 维 8.9，**不伪造** live。

## Local Engineering Release Checklist

| # | Gate | 现行命令 |
|---|------|----------|
| 1 | Full verify | `bash scripts/verify.sh all` |
| 2 | Acceptance | **17** — `bash scripts/verify.sh acceptance` |
| 3 | LLM integration | **76** — `bash scripts/verify.sh llm-integration` |
| 4 | Product Shell | Jest **179** — `bash scripts/verify.sh product-shell-static` |
| 5 | Docs consistency | `bash scripts/docs_consistency_check.sh` |
| 6 | CI | `.github/workflows/verify.yml` |

**不自动执行**：git push、Release、systemd 安装、凭据配置。

## Active SoT 集合

**唯一枚举**：[docs/README.md](./README.md) 的 **Active** 表（架构 / 契约 / 运行 / Product Shell / 商业 / 安装与用户指南等）。

**本文件角色**：AgentOS **评分与 release gate** SoT；工程文档子集见上表，不在此重复维护平行文件列表。

历史 / thesis：`docs/Furnace Elixir.md`、`docs/archive/*`

## Milestone 映射

| Milestone | 维度 |
|-----------|------|
| AGOS-001~009 | 见 [Execution Plan](./archive/AGOS-9-Execution-Plan.md) |

## 更新记录（摘要）

- 2026-05-20~24：AGOS-001~009；AOS-C8 local release evidence（unit+coverage 口径，**已退役**）。
- 2026-07-15：verify 收缩为 acceptance-only + llm-integration；coverage / unit pytest 退役。
- 2026-07-18：Local / Live 双门禁；W3 AgentOS CLI 裁剪。
- 2026-07-19：audit remediation；P2-9 hub 归零证据刷新；Docs/Maint 漂移 → Local Eng ≈8.4。
- 2026-07-20：Wave 3 docs 缩略；verify 实测 acceptance **16**、llm-integration **76**、Jest **174**。
- 2026-07-22：Ask sync-chat（删 submit/resume/background）后四路复评 — Local Eng **9.05**；Live 维 **7.0**（Gate not-yet）；Commercial **7.8**；Ask 架构 A/B **8.0**。verify：acceptance **17** / Jest **179** / llm **76**。
