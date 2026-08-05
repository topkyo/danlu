---
title: "Multi-Agent Reevaluation R3 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R3（corpus + facade 后）

> **性质**：6 路只读扫描 + 交叉裁决。非 Active SoT 替代物。  
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → 傍晚 R2 **8.2** → **本轮 R3**。  
> **触发**：用户择「复评打分」量 corpus / facade / 优先债收口收益。

**HEAD**：`90e19dc`（含 PR #27 + CI mktemp/rg 修）  
**工作树**：clean（`main...origin/main`）  
**规模**：`src/aiwiki` **191** `.py` / **43,712** LOC

---

## 结论先行

**工程实测七维加权：8.3 / 10**（较 R2 **8.2**，**+0.1**）。

主增量来自架构（环断 + facade 清零门禁化）与文档/安全契约测；可维护性与产物横盘——hub 与 Commercial 三阻断未动，故涨幅克制。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.3** | 对内：结构债两刀落地后门禁更硬 |
| Scorecard Local Engineering | **9.05**（未重算八维） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

---

## 分维评分

| 维度 | 权重 | R2 | **R3** | Δ | Scorecard 自评 |
|---|---:|---:|---:|---:|---:|
| 架构与分层 | 20% | 8.3 | **8.5** | +0.2 | 9.4 |
| 代码质量 / 可维护性 | 15% | 8.1 | **8.1** | 0 | 9.0 |
| 测试与验证 | 20% | 8.1 | **8.2** | +0.1 | 8.9 |
| 产物完整性 / 发布 | 10% | 8.0 | **8.0** | 0 | — |
| 安全与治理 | 15% | 8.5 | **8.7** | +0.2 | 9.1 |
| 文档 SoT | 10% | 7.8 | **8.3** | +0.5 | 8.9 |
| 产品可用性（Shell） | 10% | 8.2 | **8.2** | 0 | 9.3 |
| **加权合计** | 100% | **8.2** | **8.3** | **+0.1** | **9.05** |

计算：`8.5×0.20 + 8.1×0.15 + 8.2×0.20 + 8.0×0.10 + 8.7×0.15 + 8.3×0.10 + 8.2×0.10 = 8.31 ≈ 8.3`。

---

## 交叉共识

1. **`verify.sh all` EXIT=0**：acceptance **24** / llm **85** / unit **153** / Jest **203**；coverage **69%**；0% 模块 **0**。
2. **`content ↛ memory`**：rg + AST + `docs_consistency` 三钉；`aiwiki.corpus` 承载 paths/scoring/ranks。
3. **Facade 清零**：`app_shell`/`app_linting` 无 `_CompatModule`；包级 import 禁令测绿。
4. **`machine_memory` 必传**：缺省 `{}` 风险已关；TypeError 契约测在。
5. **Hub / Commercial 未动**：views 921 等；EULA / PyPI / Demo 媒体仍开。
6. **CI**：Linux `rg` + portable `mktemp` 已修；main Verify 绿。

---

## 分维要点

### 架构 8.5（+0.2）
R2 两条 P0（环、facade）关闭并门禁化。余：memory→content 窄依赖、hub、memory 侧 corpus re-export。

### 可维护性 8.1（0）
except Exception 65；Top hub 未削。环改善不足以抬分。

### 测试 8.2（+0.1）
unit 143→153；文档钉对齐。coverage 69% 横盘；活路径低覆盖仍开。

### 产物 8.0（0）
drift 绿；PyPI 未上架；Shell 不进 wheel。

### 安全治理 8.7（+0.2）
alchemy-revert library 测 + untrusted_source 测 + facade 契约。余：acceptance revert fixture；`revert_supported: false` 语义缝。

### 文档 8.3（+0.5）
主链 153 对齐 + 分层硬钉。余：Architecture/AGENTS 缺 corpus 包叙事；PROGRESS 部分头条滞后。

### Shell 8.2（0）
today-feed 三方契约与 drift 维持。

### Commercial ~7.8（0）
三阻断全开。

---

## P0 / P1（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 | **无新 runtime P0** |
| H-1 | P1 | hub 单 seam（views / ask / io） |
| M-1 | P1 | memory→content 符号迁 corpus（S2） |
| G-1b | P1 | alchemy-revert acceptance fixture；`revert_supported` 语义 |
| D-1 | P1-doc | Architecture/AGENTS 写 corpus；PROGRESS 头条 153 |
| C-1 | P1 | Commercial 三阻断（人类） |

---

## 历史对照

```text
08-03  7.4 ──W0–W6──►
08-04  6.8 ──F-1~F-13──►
08-05 早 7.9 ──R-5/repair──►
08-05 R2 8.2 ──corpus+facade+优先债──►
08-05 R3 8.3  （本报告）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：+0.1 是「结构债两刀把门禁做硬」的收益，不是 hub 变瘦或可售。距工程 **8.5+** 需 hub 续刀；距可售仍差 Commercial 三阻断。
