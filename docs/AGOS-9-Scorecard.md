---
title: "AgentOS 9.0 Scorecard"
kind: "scorecard"
status: "active"
updated_at: "2026-07-26"
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

## 现行 verify gate（Local Engineering，2026-08-04 实测）

| 组件 | 数量 | 命令 |
|---|---:|---|
| Acceptance | **24** passed | `bash scripts/verify.sh acceptance` |
| LLM integration | **83** passed | `bash scripts/verify.sh llm-integration` |
| Unit（library 级） | **67** passed | `bash scripts/verify.sh unit` |
| Product Shell Jest | **203** passed | `bash scripts/verify.sh product-shell-static` |
| Bundle drift | gate（正反向实测） | 含于 `product-shell-static` |
| Coverage | **64%**（informational，无门禁） | `bash scripts/verify.sh coverage` |
| 全量 | 9 步 | `bash scripts/verify.sh all` |
| Docs consistency | exit 0 | `bash scripts/docs_consistency_check.sh` |
| CI | exists | `.github/workflows/verify.yml` |

**不含**：旧 AOS-C8 的 2439 unit tests + coverage 92%（2026-07-15 已退役）；`dogfood_maturity_gate.py`、`agos9_release_audit.sh` 已删。现行 unit 仅 `tests/test_security.py` + `tests/test_vault_plugin.py` 两个 library 级文件；coverage 只报告不卡线。

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
| Dogfood / fixture | 20% | 8.9 | no（live 维 blocking 在 Live gate） | acceptance **24** replay + AOS-C8 **historical** |
| Product Shell | 12% | 9.3 | yes | Jest **203** + bundle drift 硬门禁 + sync `run-ask` 单飞 + Today-first |
| Runtime correctness | 15% | 9.4 | no | path harden + fail-closed LLM；无 background submit/resume |
| Planner / signal | 10% | 8.7 | no | internal modules；CLI 已删；acceptance replay |
| LLM reliability | 12% | 9.0 | no | llm-integration **83** + receipt 聚合 |
| Governance | 13% | 9.1 | yes | review-page / alchemy-revert / gc-orphans / file-back receipts；无入口 mm_actions 治理簇 2026-08-04 已整簇删除 |
| Maintainability | 8% | 9.0 | no | 顶层 `app_*.py` = 0；cli facade 归零；Ask 路径净删 background；治理孤儿簇 −4.6k 行 |
| Docs SoT | 10% | 8.9 | yes | active docs 对齐；本轮刷新计数 |

> **AOS-C8 frozen**：2026-05 三天 live PASS 仍作 **historical** 证据；Local Engineering 用 fixture + historical 计 Dogfood 维 8.9，**不伪造** live。

## Local Engineering Release Checklist

| # | Gate | 现行命令 |
|---|------|----------|
| 1 | Full verify | `bash scripts/verify.sh all` |
| 2 | Acceptance | **24** — `bash scripts/verify.sh acceptance` |
| 3 | LLM integration | **83** — `bash scripts/verify.sh llm-integration` |
| 4 | Product Shell | Jest **203** + bundle drift gate — `bash scripts/verify.sh product-shell-static` |
| 5 | Unit | **67** — `bash scripts/verify.sh unit` |
| 6 | Docs consistency | `bash scripts/docs_consistency_check.sh` |
| 7 | CI | `.github/workflows/verify.yml` |

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
- 2026-07-22（eng-debt radar）：Jest 实测 **180**；llm-integration 增 multipart HTTP body parse → **77**。
- 2026-07-22（shell settings less · batch 3）：Jest 实测 **169**（settings fold 测试断言调整；AGENTS/Scorecard 对齐）。
- 2026-07-24：质保 Round1–3 + DEF-R2-01 后 verify 实测 acceptance **18** / Jest **189** / llm **78**；AGENTS/Scorecard 计数对齐（**已被 2026-07-26 实测 24/79/206 取代**）。
- 2026-07-26：沉淀/金丹写端瘦身 + curated Properties leaf sync + WS2 wheel 后实测 acceptance **24** / Jest **200** / llm **79**；同日晚 SoT 卫生对齐 Jest **206**（实测）。
- 2026-08-03：多 agent 全量审计（综合 **7.4/10**）+ 收口计划 `docs/plans/2026-08-03-multi-agent-audit-remediation.md` 全部 7 波执行完毕——W0 rewrite-proposal 清理归属守卫（P0 数据安全）；W1 ruff F401 启用（1594 处死 import 清除）+ 脚本加固；W2 死代码删除（`vault_queue.py` 等，Python + JS）；W3 bridge launcher 180s 超时 + 4MB 输出上限；W4 today-feed schema 对齐 Python SoT（修掉 JS 幻影 `proposal` kind）+ compile-state 键注册表收敛；W5 prompt 注入边界包装（`<untrusted_source>`）+ planner/distill/vision LLM receipts + fetch_raw 失败挪出正文 + config env 解析保护；W6 巨石四刀外提（graph_query 474→375 / workflows_ask 490→226 / repair 416→78 / mm_actions 361→328 行；JS 刀评估后保留，差异有测试锁定）。verify 实测 acceptance **24** / Jest **203** / llm **82**。
- 2026-08-04：独立全量复评（综合 **6.8/10**，证据与收口清单见 `docs/plans/2026-08-04-full-scan-evaluation.md`）+ 4-agent 收口执行——F-1 main.js bundle 漂移修复（W4 修复此前未进产物）+ verify 新增 drift 硬门禁（正反向实测）+ `sync_product_shell_plugin` 前置 build；F-2 无入口治理簇 8 模块 ~4.6k 行整簇删除（用户裁定）；F-3 `utils/security.py` 覆盖 39%→**99%**（56 例）；F-4 vault plugin/bootstrap 11 例 + verify 新增 `unit` 硬门禁（**67**）与 `coverage` 无门禁报告（实测 **64%**）；F-5~F-8 facade 归零 / POSIX classifier / 计数修正 / `analyze_image` 重试 parity。复审收尾：`autonomy_domains` 死模块删除、`analyze_image` 重试测试锁定、`verify_target_rules` 映射 unit、一致性检查新增计数钉。verify 实测 acceptance **24** / llm **83** / Jest **203** / unit **67**。
