---
title: "Multi-Agent Reevaluation R5 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R5（P1 分修合入后）

> **性质**：6 路只读扫描 + 交叉裁决。非 Active SoT 替代物。  
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → R2 **8.2** → R3 **8.3** → R4 **8.5** → **本轮 R5**。  
> **触发**：PR #29 merge 后用户要求正式复评并刷新工程实测。

**HEAD**：`5530d29`（含 PR #29 P1 分修）  
**工作树**：clean（`main...origin/main`，本报告提交前）  
**规模**：`src/aiwiki` **199** `.py` / **43,872** LOC

---

## 结论先行

**工程实测七维加权：8.6 / 10**（较 R4 **8.5**，**+0.1**；较 R3 **8.3**，**+0.3**）。

主增量：P1 关闭 R4 所列代码/治理/测试/文档债（frontmatter 统一、metrics warning、promote `revert_supported`、六命令烟测、writeback seam、CHANGELOG+corpus 叙事）；架构与可维护性抬升。Commercial 三阻断与 coverage **69%** 横盘，故涨幅克制。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.6** | 对内：P1 债收口后结构更硬 |
| Scorecard Local Engineering | **9.05**（未重算八维） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

---

## 分维评分

| 维度 | 权重 | R3 | R4 | **R5** | Δ vs R4 | 核心依据 |
|---|---:|---:|---:|---:|---:|---|
| 架构与分层 | 20% | 8.5 | 9.0 | **9.1** | +0.1 | writeback seam；分层红线全绿；facade 零复活 |
| 代码质量 / 可维护性 | 15% | 8.1 | 8.3 | **8.5** | +0.2 | frontmatter 四拷贝清零；metrics 可观测；workflows_ask 786→334 |
| 测试与验证 | 20% | 8.2 | 8.2 | **8.3** | +0.1 | unit **160**；六命令 CLI smoke；verify unit EXIT=0 |
| 产物完整性 / 发布 | 10% | 8.0 | 8.0 | **8.1** | +0.1 | CHANGELOG 补录；wheel 边界不变；PyPI 未上架 |
| 安全与治理 | 15% | 8.7 | 8.7 | **8.8** | +0.1 | promote/`audit` `revert_supported: true`；SSRF 契约未退化 |
| 文档 SoT | 10% | 8.3 | 8.5 | **8.5** | 0 | 主链钉 160 + corpus 叙事；本轮刷新工程实测横幅 |
| 产品可用性（Shell） | 10% | 8.2 | 8.2 | **8.2** | 0 | Jest 203 + drift；PR #29 无 Shell 改动 |
| **加权合计** | 100% | **8.3** | **8.5** | **8.6** | **+0.1** | |

计算：`9.1×0.20 + 8.5×0.15 + 8.3×0.20 + 8.1×0.10 + 8.8×0.15 + 8.5×0.10 + 8.2×0.10 = 8.555 ≈ 8.6`。

---

## 交叉共识（6 路）

1. **`verify.sh unit` EXIT=0**：unit **160**；acceptance/llm pins 仍 **24** / **85**；docs_consistency 绿。
2. **R4 P1 清单大部分关闭**：Q-1 / Q-2 / T-1 / G-1 / D-1；A-1 半开（writeback 落地，`ask_question` ~294 行仍记债）。
3. **分层红线**：`content ↛ memory` / `memory ↛ content` / `corpus` 真叶子；根级 `app_*.py` **0**；`_CompatModule` **0**。
4. **Hub**：`workflows_ask` **334** + writeback **479**；`ask` **659** / `io` **641** / `views` **668**；`url` **790** / `concepts` **728** 仍偏大。
5. **无新 runtime P0**；Commercial 三阻断（EULA 法律 / PyPI / Demo 媒体）仍为人类依赖。
6. **coverage ~69%** 与 Jest npm 环境性 flake 风险横盘。

---

## 分维要点

### 架构 9.1（+0.1 vs R4）
writeback seam 关掉 R4 点名的 workflows_ask 786 hub。余：`ask_question`；`llm.py` / `url` / `concepts`。

### 可维护性 8.5（+0.2）
四拷贝与静默吞错已关。余：`_complete_run_ask_artifact` 仍偏长；写 frontmatter 变体分散；`except Exception` **65** 横盘。

### 测试 8.3（+0.1）
六命令 smoke 入门禁。余：测深仍浅；coverage 69%；Jest npm ci flake。

### 产物 8.1（+0.1）
CHANGELOG 同步改善。PyPI / Shell-not-in-wheel 不变。

### 安全治理 8.8（+0.1）
promote revert 语义缝关闭。余：acceptance 级 alchemy-revert fixture；`drop repo` clone SSRF（默认关）。

### 文档 8.5（0 vs R4）
pin/corpus 已齐；本报告刷新工程实测横幅（Post-Cleanup/Scorecard 曾停 8.2/8.3）。

### Shell 8.2（0）
`render_today.js` 949；manifest author 品牌错未动。

### Commercial ~7.8（0）
三阻断全开。

---

## P0 / P1（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 | **无新 runtime P0**（Commercial 三阻断仍为人类 P0） |
| A-1 | P1 | `ask_question` ~294 行单 seam（编排 vs 持久化） |
| T-2 | P1 | Jest 门禁：`npm ci` 后显式校验 jest，失败给可操作消息 |
| G-1b | P1 | acceptance 级 alchemy-revert fixture |
| S-1 | P1 | Shell manifest author 品牌修正（分发前） |
| C-1 | P1 | Commercial 三阻断（人类） |

---

## 历史对照

```text
08-03  7.4 ──W0–W6──►
08-04  6.8 ──F-1~F-13──►
08-05 早 7.9 ──R-5/repair──►
08-05 R2 8.2 ──corpus+facade+优先债──►
08-05 R3 8.3 ──hub 三 seam + corpus S2──►
08-05 R4 8.5 ──P1 前扫描──►
08-05 R5 8.6  （本报告 · P1 合入后）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：+0.1 vs R4 是「R4 自己点名的 P1 被关掉」的兑现分，不是新架构跃迁。距可售仍差 Commercial 三阻断。
