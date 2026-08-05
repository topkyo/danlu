---
title: "Multi-Agent Reevaluation 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 交叉复评（2026-08-05）

> **性质**：6 路只读 agent 并行扫描 + 交叉裁决后的评分快照。  
> **非** Active SoT 替代物：架构以 `docs/Furnace Agent Architecture.md`、门禁以 `docs/AGOS-9-Scorecard.md`、执行计划以 Post-Cleanup 为准。  
> **前序**：08-03 六路审计综合 **7.4** → 收口 W0–W6；08-04 全量扫描综合 **6.8** → F-1~F-13 全关闭。本报告是收口后的复评。

**HEAD**：`24b6e6f`  
**工作树**：clean（`main...origin/main`）  
**规模**：`src/aiwiki` **194** `.py` / **44,674** LOC（↓ 自 ~51.6k / ~202 文件）

---

## 结论先行

**综合 7.9 / 10**（工程实测七维加权，口径同 08-04）。

F-1~F-13 收口后，08-04 的两个硬扣分项（bundle 漂移 4.5、覆盖/无 unit 门禁 5.5）已明显回升；系统从「verify 绿但机制有洞」回到「门禁可信、产物可复现」。  
仍不支持把 Scorecard **Local Eng 9.05** 直接当工程实测分：覆盖 64% 无阈值、Active 执行计划 Post-Cleanup 快照 stale、PyPI/插件打包未闭环。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **7.9** | 可对内说「收口后工程可信度明显回升」 |
| Scorecard Local Engineering | **9.05**（自评门禁加权，未本轮重算） | 可宣称 fixture/verify 就绪；**不可**冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8**（未重测，缺口仍在分发/法律） | **不可**说诚实可售 |

---

## 方法

| 路 | 维度 | 模型角色 |
|---|---|---|
| 1 | 架构与分层 | 只读探索 |
| 2 | 代码质量 / 可维护性 | 只读探索 |
| 3 | 测试与验证 | 跑 `verify.sh all` + coverage + docs_consistency |
| 4 | 产物完整性 + 安全与治理 | rebuild diff + security/治理反查 |
| 5 | 文档 SoT + Product Shell | Active 表 / 计数钉 / Jest / schema |
| Parent | 交叉裁决加权 | 否证冲突、统一 P0/P1 |

**证据分层**：全部为 `replay` / 静态可复核；**不含** live dogfood 断言。

---

## 分维评分

| 维度 | 权重 | 08-03 | 08-04 | **本次** | Δ vs 08-04 | Scorecard 自评 |
|---|---:|---:|---:|---:|---:|---:|
| 架构与分层 | 20% | — | 7.5 | **8.2** | +0.7 | 9.4 |
| 代码质量 / 可维护性 | 15% | — | 7.5 | **8.0** | +0.5 | 9.0 |
| 测试与验证 | 20% | — | 5.5 | **7.2** | +1.7 | 8.9 |
| 产物完整性 / 发布 | 10% | — | 4.5 | **8.0** | +3.5 | — |
| 安全与治理 | 15% | — | 7.5 | **8.5** | +1.0 | 9.1 |
| 文档 SoT | 10% | — | 7.0 | **7.5** | +0.5 | 8.9 |
| 产品可用性（Shell） | 10% | — | 7.0 | **7.5** | +0.5 | 9.3 |
| **加权合计** | 100% | **7.4** | **6.8** | **7.9** | **+1.1** | **9.05** |

计算：`8.2×0.20 + 8.0×0.15 + 7.2×0.20 + 8.0×0.10 + 8.5×0.15 + 7.5×0.10 + 7.5×0.10 = 7.855 ≈ 7.9`。

---

## 交叉共识（多路同时成立）

1. **`verify.sh all` EXIT=0**：acceptance **24** / llm **85** / unit **72** / Jest **203**；docs consistency OK；计数与 AGENTS/Scorecard/DEVELOPER 对齐。
2. **F-1 闭环**：committed `main.js` 与 rebuild **无 drift**；`product-shell-static` 含硬门禁；`sync_product_shell_plugin` 先 build。
3. **F-2 无回潮**：8 个无入口治理模块磁盘不存在；`execution/` 现存模块均可从 CLI/runner/compile/tests 到达。
4. **无 1000+ LOC 单文件**；F-11 三刀落地（concepts 812 / views 942 / phases 307）；总 LOC ~44.7k。
5. **安全边界硬化**：`utils/security.py` ~99% 覆盖；301/302/303 降级 + `PrivateAddressError`；`<untrusted_source>` 仍在。
6. **结构性余债未清**：`content↔memory` 双向依赖；top hub 仍 700–940 行；覆盖 **64%**、**10** 模块 0%。

---

## 分维要点

### 架构 8.2
- CLI 仅 `drop/today/advanced`；根级 `app_*.py` = 0；`memory↛execution`、`state↛protocol` 清零。
- LLM fail-closed、无隐式跨 backend fallback（集成测钉死）。
- **P1**：`content↔memory` 环；子包 re-export facade 残留。

### 可维护性 8.0
- `except Exception` **65**（↓）；裸 `pass` **0**；ruff F401 仍启用且绿。
- Top：`views` 942 / `ask` 888 / `io` 881 / `concepts` 812。
- **P1**：续削 views/ask/workflows_ask；防新 orphan mutation 簇。

### 测试 7.2
- unit 硬门禁 + coverage informational 已进 `verify all`；security 99%。
- 覆盖 64%（↑6pp）、0% 模块 10（↓自 20）。
- **P1**：关键低覆盖（如 `repair.py` 3%）；0% 模块需区分死代码 vs 欠测。
- **P2**：`verify.sh` usage 单行仍写 llm **83**（`all` 行已是 85）。

### 产物 8.0
- drift P0 已灭；本地 wheel 脚本存在。
- **P1**：PyPI 未上架；Product Shell 未进 wheel（仍依赖 checkout）。

### 安全与治理 8.5
- 治理 CLI（review-page / file-back / gc-orphans / alchemy-revert）仍可达。
- Scorecard Governance 9.1 仍偏乐观：revert 等主要靠 fixture 间接覆盖。

### 文档 SoT 7.5
- 核心三件套 + `docs_consistency_check` 钉绿。
- **P0-doc**：Active 计划 Post-Cleanup §1 仍写 Jest **206** / llm **79** / 已删 hub `machine_memory_actions`。
- **P0-doc**：Scorecard 主表 9.05 无工程实测 6.8/7.9 并列横幅（仅 changelog/PROGRESS 有）。
- **P1**：PROGRESS 改进方向表与会话交接模板残留 206/79。

### Product Shell 7.5
- Today-first + sync run-ask 单飞 + settings 分区；today-feed schema 三方钉死。
- **P1（部分已收）**：`proposal` feed 桶与「今日简报」术语已于 2026-08-05 收敛；Ask 长等待 UX 仍开。

---

## P0 / P1 收口清单（本轮新发现或仍开）

| ID | 级别 | 项 | Done 判据 |
|---|---|---|---|
| R-1 | P0-doc | 刷新 Post-Cleanup §1 计数/hub（或归档并换新执行计划 SoT） | **done 2026-08-05** |
| R-2 | P0-doc | Scorecard 主表并列「自评门禁 vs 工程实测」 | **done 2026-08-05** |
| R-3 | P1 | PROGRESS 改进方向 + 会话交接计数对齐 24/85/72/203 | **done 2026-08-05** |
| R-4 | P1 | `verify.sh` usage 行 llm 83→85 | **done 2026-08-05** |
| R-5 | P1 | 0% / 极低覆盖活模块归属（删或补测） | **done 2026-08-05**：删 7 孤儿；补 9 library surfaces 测；unit 81 |
| R-6 | P1 | Commercial：PyPI upload + plugin 打包策略 | INSTALL 可写真实 `pip install` 或明确永久 preview |
| R-7 | P1 | Shell：收敛 proposal UI 桶；术语统一 | **done 2026-08-05**：render_today 去 proposal 桶；USER_GUIDE/INSTALL→Today；Post-Cleanup 裁定暂不归档 |
| R-8 | P2 | content↔memory 环 / hub 续刀 | 单 seam；禁止 broad rewrite |

**本轮无新 runtime P0**（08-04 F-1 机制洞已关）。

---

## 与历史评分对照

```text
08-03 六路审计     7.4  ──收口 W0–W6──►
08-04 全量扫描     6.8  （挖出 drift + 覆盖 58% + 孤儿簇）──F-1~F-13──►
08-05 六路复评     7.9  （机制洞关闭；文档 Active 计划成最大 SoT 债）
Scorecard Local    9.05 （fixture 门禁加权；未本轮重算八维）
Commercial         ~7.8 （分发/法律；未本轮重测）
```

**解读**：6.8→7.9 的 +1.1 主要来自产物维 +3.5 与测试维 +1.7，不是「产品突然更好用」，而是「此前被低估的机制债已还」。距诚实工程 8.5+ 还需覆盖深度 + Active 文档卫生；距 Scorecard 9.x 叙事还需承认双尺子或下调自评维。

---

## 建议下一刀（择一）

1. **文档卫生快刀**（R-1~R-4）：半天量级，直接抬文档维与交接可信度。  
2. **Commercial Go-Live**：EULA 法律签收 / twine + tag / Demo 媒体（PROGRESS 原指针）。  
3. **覆盖归属**（R-5）：10 个 0% 模块二选一（删或补测），防 08-04 孤儿债复发形态。  
4. **勿**：用本报告 7.9 或 Scorecard 9.05 对外宣称 live / 可售。
