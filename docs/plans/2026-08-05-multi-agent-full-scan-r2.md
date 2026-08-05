---
title: "Multi-Agent Full Scan R2 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 全量扫描复评 R2（2026-08-05 傍晚）

> **性质**：6 路只读 agent 并行扫描 + 交叉裁决后的评分快照。  
> **非** Active SoT 替代物：架构以 `docs/Furnace Agent Architecture.md`、门禁以 `docs/AGOS-9-Scorecard.md`、执行计划以 Post-Cleanup 为准。  
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9**（`2026-08-05-multi-agent-reevaluation.md`）。本报告是 R-5 / repair 补测 / R-7 之后的第二轮全量复评。

**HEAD**：`334d606`  
**工作树**：clean（`main...origin/main`）  
**规模**：`src/aiwiki` **187** `.py` / **43,807** LOC（↓ 自 08-05 早 194 / ~44.7k）

---

## 结论先行

**工程实测七维加权：8.2 / 10**（较 08-05 早 **7.9**，**+0.3**）。

主增量来自测试维（unit **72→143**、coverage **64%→69%**、0% 模块 **10→0**）与 Product Shell 契约收口（proposal 桶 / Today 术语）。架构与安全维基本横盘；Commercial 仍卡在 EULA / PyPI / Demo 媒体，**~7.8 未过诚实可售 8.0**。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.2** | 可对内说「门禁可信 + 覆盖/孤儿债明显减轻」 |
| Scorecard Local Engineering | **9.05**（自评门禁加权，未本轮重算八维） | 可宣称 fixture/verify 就绪；**不可**冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | **不可**说诚实可售 |

---

## 方法

| 路 | 维度 | 角色 |
|---|---|---|
| 1 | 架构与分层 | 只读探索 |
| 2 | 代码质量 / 可维护性 | 只读探索 + ruff |
| 3 | 测试与验证 | `verify.sh all` + coverage + docs_consistency |
| 4 | 产物完整性 + 安全与治理 | drift / security / 治理 CLI |
| 5 | 文档 SoT + Product Shell | Active 表 / 计数钉 / Jest / schema |
| 6 | Commercial Go-Live | WS1–WS6 / EULA / PyPI / Demo |
| Parent | 交叉裁决加权 | 否证冲突、统一 P0/P1 |

**证据分层**：全部为 `replay` / 静态可复核；**不含** live dogfood 断言。

---

## 分维评分

| 维度 | 权重 | 08-03 | 08-04 | 08-05 早 | **本次 R2** | Δ vs 早 | Scorecard 自评 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 架构与分层 | 20% | — | 7.5 | 8.2 | **8.3** | +0.1 | 9.4 |
| 代码质量 / 可维护性 | 15% | — | 7.5 | 8.0 | **8.1** | +0.1 | 9.0 |
| 测试与验证 | 20% | — | 5.5 | 7.2 | **8.1** | +0.9 | 8.9 |
| 产物完整性 / 发布 | 10% | — | 4.5 | 8.0 | **8.0** | 0 | — |
| 安全与治理 | 15% | — | 7.5 | 8.5 | **8.5** | 0 | 9.1 |
| 文档 SoT | 10% | — | 7.0 | 7.5 | **7.8** | +0.3 | 8.9 |
| 产品可用性（Shell） | 10% | — | 7.0 | 7.5 | **8.2** | +0.7 | 9.3 |
| **加权合计** | 100% | **7.4** | **6.8** | **7.9** | **8.2** | **+0.3** | **9.05** |

计算：`8.3×0.20 + 8.1×0.15 + 8.1×0.20 + 8.0×0.10 + 8.5×0.15 + 7.8×0.10 + 8.2×0.10 = 8.17 ≈ 8.2`。

---

## 交叉共识（多路同时成立）

1. **`verify.sh all` EXIT=0**：acceptance **24** / llm **85** / unit **143** / Jest **203**；docs consistency 硬门禁钉绿；coverage informational **69%**。
2. **R-5 / repair 补测落地**：0% 模块清零；`repair.py` / `repair_plan.py` / `patch_plan.py` → 100%/100%/99%；unit **81→143**。
3. **F-1 仍闭环**：committed `main.js` 与 rebuild 无 drift；sync 前置 build。
4. **无 1000+ LOC 单文件**；Top hub `views` 921 / `ask` 888 / `io` 881；总 LOC ~43.8k / 187 文件。
5. **安全边界 intact**：`utils/security.py` 61 专项测；301/302/303 降级；`PrivateAddressError`；`<untrusted_source>` 仍在（缺单测）。
6. **结构性余债未清**：`content↔memory` 双向依赖；`app_shell`/`app_linting` 重 facade；compile 静态 SCC 密度高。
7. **Commercial 三阻断未动**：EULA 法律签收 / PyPI 上架 / Demo 媒体（0 截图 0 录屏）。

---

## 分维要点

### 架构 8.3（+0.1）
- CLI 仅 `drop/today/advanced`；根级 `app_*.py` = 0；`memory↛execution`、`state↛protocol` 清零；LLM 主路径 fail-closed。
- orphan 模块已删；`render/__init__.py` 已 doc-only。
- **P0 结构债**：content↔memory 环；`app_shell`/`app_linting` 重 facade。

### 可维护性 8.1（+0.1）
- `except Exception` 仍 **65**；裸 `except:` **0**；ruff F401 绿；TODO/FIXME 注释 **0**。
- **P1**：续削 views/ask/io；收窄 alchemy 宽 except；compile 簇解耦。

### 测试 8.1（+0.9）— 本轮最大涨幅
- unit 硬门禁翻倍；coverage 64%→69%；0% 模块 10→0。
- **P1（测试）**：活路径低覆盖 — `memory/status` 10%、`audit_reconciliation` 14%、`drop/*` 18–32%、`trace` 30%。
- **P1（文档，不重复扣测试分）**：Scorecard/DEVELOPER 仍写 coverage **64%**；Post-Cleanup/CHANGELOG 仍写 unit **81**。

### 产物 8.0（0）
- drift P0 已灭；本地 wheel 脚本可用。
- **P1**：PyPI 未上架；Product Shell 未进 wheel。

### 安全与治理 8.5（0）
- 四条治理 CLI 可达；无入口治理簇不回潮。
- **P1**：`alchemy-revert` 零直接 fixture；`<untrusted_source>` 无单测；promotion `revert_supported: false` 与实现能力语义不一致。

### 文档 SoT 7.8（+0.3）
- 主链 AGENTS / Scorecard / DEVELOPER / verify / PROGRESS 交接已对齐 **24/85/143/203**。
- **P0-doc**：Active 计划 Post-Cleanup §1/§8 仍写 unit **81**（`docs_consistency` 不钉该文件）。
- **P1**：Scorecard「两个 library 级 unit 文件」过时（实为 4）；INSTALL「today 简报」术语尾巴。

### Product Shell 8.2（+0.7）
- Today-first + sync run-ask 单飞 + today-feed schema 三方一致（无 `proposal`）。
- Jest **203** + drift gate 绿。
- **P1**：INSTALL 术语卫生；Ask 长等待 UX 仍开。

### Commercial ~7.8（0）
- WS4/WS5 巩固；WS1 法律签收 / WS2 PyPI / WS3 媒体 / WS6 live 仍开。
- **必须与工程 8.2 分标**；过诚实可售 8.0 最低集：EULA 签收 + PyPI + Demo 媒体。

---

## P0 / P1 收口清单（本轮）

| ID | 级别 | 项 | Done 判据 |
|---|---|---|---|
| D-1 | **P0-doc** | Post-Cleanup §1/§8 unit 81→**143**；文末 72→143 | `docs_consistency` 可选扩钉；或归档换新计划 |
| D-2 | P1-doc | Scorecard/DEVELOPER coverage 64%→**69%**；「两个 unit 文件」→四文件 | 主表与描述一致 |
| T-1 | P1 | 低覆盖活路径：`memory/status`、`audit_reconciliation`、`drop/*`、`trace` | 关键模块 ≥50% 或标注 defer |
| G-1 | P1 | `alchemy-revert` 直接 acceptance/fixture | promote→revert round-trip + receipt 哈希 |
| S-1 | P1 | `<untrusted_source>` 单测 | closing-tag neutralization + wrap 格式 |
| A-1 | P1 | content↔memory 环 / hub 续刀 | 单 seam；禁止 broad rewrite |
| R-6 | P1 | Commercial：EULA 签收 + PyPI + Demo 媒体 | 过 Commercial ≥8.0 |

**本轮无新 runtime P0。**

---

## 与历史评分对照

```text
08-03 六路审计     7.4  ──收口 W0–W6──►
08-04 全量扫描     6.8  （drift + 覆盖 58% + 孤儿簇）──F-1~F-13──►
08-05 早 六路复评  7.9  （机制洞关闭）──R-5/repair/R-7──►
08-05 傍晚 R2      8.2  （测试维 +0.9；Shell +0.7）
Scorecard Local    9.05 （fixture 门禁加权；未本轮重算八维）
Commercial         ~7.8 （分发/法律/媒体；三阻断未动）
```

**解读**：7.9→8.2 主要是「补测与孤儿清理把测试维从偏弱拉到中上」，不是产品面突变。距工程诚实 **8.5+** 还需活路径覆盖深度 + 结构债续刀；距可售仍差 Commercial 三阻断。

---

## 建议下一刀（择一）

1. **文档快刀（D-1/D-2）**：Post-Cleanup unit 143 + coverage 69% 对齐 — 半小时量级，抬文档维。  
2. **Commercial Go-Live**：EULA 法律签收 / twine + tag / Demo 媒体。  
3. **治理可证（G-1）**：`alchemy-revert` fixture，收窄 Scorecard Governance 9.1 与实测 8.5 的缝。  
4. **勿**：用本报告 8.2 或 Scorecard 9.05 对外宣称 live / 可售。
