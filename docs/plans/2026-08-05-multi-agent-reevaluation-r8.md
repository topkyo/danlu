---
title: "Multi-Agent Reevaluation R8 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R8（全量扫描独立裁决）

> **性质**：7 路只读独立扫描 + 主 agent 交叉裁决与关键事实抽检。非 Active SoT 替代物。
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → R2 **8.2** → R3 **8.3** → R4 **8.5** → R5/R6 **8.6** → R7 草稿 **8.7**（PR #31 窄透镜）→ **本轮 R8**。
> **触发**：用户要求多 agent 了解项目、全量扫代码、多维度分析后评审评分。

**HEAD**：`ec7bc7c`（含 PR #31 R6 findings 修复）  
**工作树**：仅本报告与既有未跟踪 R7 草稿；代码树相对 `origin/main` clean。  
**原始分维报告**：`tmp/r8-{arch,quality,tests,security,docs,shell,release}.md`

---

## 结论先行

**工程实测七维加权：8.6 / 10**（与 R5/R6 **持平**；**不采信**同 HEAD 上 R7 草稿的 **8.7**）。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.6** | 对内：全量扫描维持工程就绪；PR #31 事实成立但不额外抬分 |
| Scorecard Local Engineering | **9.05**（八维未重算） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

**与 R7 草稿的关系**：R7 是「PR #31 声明验证」窄透镜，逐条证实 ask 拆分 / argv 六测 / coverage·CHANGELOG 钉，并据此 +0.1→8.7。R8 是七维全量结构扫描：PR #31 事实**全部复核成立**，但新定价了 R7 未计入的长期债（包级双向环、memory 纯 facade 残留、Playwright DNS rebinding 窗口、planner/vision 缺 `untrusted_source`、frontmatter 写入仍双份）。按 R4–R6 校准锚点，这些债抵消 PR #31 的边际加分，**维持 8.6**。

---

## 分维评分

| 维度 | 权重 | R6/R7 | Agent 原始 | **R8 裁决** | Δ vs R6 | 裁决要点 |
|---|---:|---:|---:|---:|---:|---|
| 架构与分层 | 20% | 9.1 / 9.2 | 7.0 | **9.0** | −0.1 | 红线全绿 + `ask_question` 38 行编排属实；拒 7.0（重校准）；−0.2 相对 R7：10+ 未文档化包环 + `memory/{scoring,action_rank}` 纯 facade |
| 代码质量 / 可维护性 | 15% | 8.5 / 8.7 | 7.4 | **8.5** | 0 | `except Exception`=65 且无静默吞错；拒 7.4；相对 R7 下压：`_render_backlog_markdown` 35 参 / frontmatter 写入双份 |
| 测试与验证 | 20% | 8.3 / 8.5 | 8.8 | **8.5** | +0.2 vs R6 | 166/24/85/203/71% 全绿；argv 真走 dispatch；拒 8.8（G-1b 仍开、argv 面仍稀） |
| 产物完整性 / 发布 | 10% | 8.1 / 8.1 | 8.2 | **8.2** | +0.1 | CHANGELOG/coverage/jest 机制钉落地；PyPI/tag 仍封顶 |
| 安全与治理 | 15% | 8.8 / 8.8 | 8.0 | **8.5** | −0.3 | `safe_fetch`+fail-closed 扎实；拒 8.0；扣 DNS rebinding（Playwright）+ planner/vision 信任边界 |
| 文档 SoT | 10% | 8.5 / 8.6 | 8.6 | **8.6** | +0.1 vs R6 | 主链 24/85/166/203/71% + consistency **46 [OK]** |
| 产品可用性（Shell） | 10% | 8.2 / 8.2 | 8.4 | **8.3** | +0.1 | Today-first + drift 硬门禁扎实；S-1 author 仍 `"OpenAI Codex"` 封死更高 |
| **加权合计** | 100% | **8.6** / **8.7** | — | **8.6** | **0 vs R6** | |

计算：`9.0×0.20 + 8.5×0.15 + 8.5×0.20 + 8.2×0.10 + 8.5×0.15 + 8.6×0.10 + 8.3×0.10 = 8.56 ≈ 8.6`。

---

## 项目画像（一句话 + 结构）

`aiwiki` 是炼丹炉的 local-first、stdlib-first、file-based runtime：`raw/ → wiki/ → machine memory → schema → outputs`，CLI 顶层仅 `drop / today / advanced`，Product Shell 为 Desktop Obsidian 插件。

| 包簇 | 角色（实测） |
|---|---|
| `content` / `memory` / `corpus` | wiki 内容、机器记忆、只读共享层（环已断） |
| `compile` / `render` / `execution` | 编译管线、渲染、ask/alchemy/review 治理 |
| `drop` / `runner` / `cli` | 投喂、LLM 编排、命令面 |
| `app_shell` / Product Shell | Shell 契约 + Obsidian UI |

`src/aiwiki` ≈ **199** 个 `.py`、**~44k** 行；Top hub：`drop/url` 790 / `lifecycle/knowledge` 788 / `runner/prompts` 778 / `execution/ask` 764。

---

## 关键事实抽检（主 agent）

| 声明 | 结果 |
|---|---|
| unit 166 / acceptance 24 / llm 85 / Jest 203 / coverage 71% | **证实**（tests agent 分项实测；docs_consistency **46 [OK]**） |
| `ask_question` 296→38 真拆分 | **证实**（`:684` 编排；prepare/materialize/finalize 三段） |
| `except Exception` = 65、无 `pass` 吞错 | **证实** |
| memory ↛ content / content ↛ memory / 根级 `app_*.py`=0 | **证实** |
| `memory/scoring.py` + `action_rank.py` 纯 re-export facade | **证实**（文件头自署 Compat） |
| planner `payload` / vision OCR 无 `<untrusted_source>` | **证实** |
| Shell `manifest.json` author = `"OpenAI Codex"` | **证实** |
| Commercial 三阻断（EULA 审阅 / PyPI / Demo 媒体） | **仍全开** |
| 本环境 `verify.sh product-shell-static` 默认 Jest OOM | **证实**（`NODE_OPTIONS=4096` 后 203 绿；计环境债非逻辑回归） |

---

## Hub Top 10（`wc -l`）

| 文件 | 行数 | 备注 |
|---|---:|---|
| drop/url.py | 790 | 文件级 hub，最大函数 ~114 |
| lifecycle/knowledge.py | 788 | 文件级 hub |
| runner/prompts.py | 778 | `_build_ask_prompt` 复杂度高 |
| execution/ask.py | 764 | 函数级已拆；`_finalize` 仍 ~183 |
| compile/ranking.py | 731 | 文件级 hub |
| content/concepts.py | 728 | 文件级 hub |
| app_shell/summary.py | 709 | |
| llm.py | 694 | |
| memory/graph_query.py | 673 | `_build_machine_memory_query_json` ~374 |
| render/views.py | 668 | |

---

## P0 / P1 / P2（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 runtime | **无** |
| C-B1/B2/B3 | P0 Commercial | EULA 法律签收 / PyPI+tag / Demo 媒体（人类，仍开） |
| A-1 | P1 | 包级双向环入库文档 + 红线自动化门禁（content↔memory 等已声明项） |
| A-2 | P1 | 删 `memory/scoring.py` / `action_rank.py` 纯 facade，调用方直引 `corpus` |
| Q-1 | P1 | `_render_backlog_markdown` 35 位置参数 → context 对象 / keyword-only |
| Q-2 | P1 | frontmatter 字符串列表写入收敛进 `utils/markdown.py` |
| G-1 | P1 | Playwright drop-url：关闭 DNS rebinding（pin 或禁浏览器直连） |
| G-2 | P1 | planner payload + vision OCR 统一 `<untrusted_source>` |
| G-1b | P1 | acceptance 级 alchemy-revert fixture（仍开） |
| S-1 | P1 | Shell manifest `author` 品牌修正（仍开） |
| T-1 | P1 | CI/`verify` 设 `NODE_OPTIONS` 防 Jest OOM 误红 |
| A-3 | P2 | 文件级 hub 六座（按需 seam，非函数级） |
| D-1 | P2 | Scorecard 八维 Docs 子分 8.9 与工程尺 8.6 并列标注 |

---

## 历史对照

```text
08-03  7.4 ──W0–W6──►
08-04  6.8 ──F-1~F-13──►
08-05 早 7.9 ──R-5/repair──►
08-05 R2 8.2 ──corpus+facade+优先债──►
08-05 R3 8.3 ──hub seam + corpus S2──►
08-05 R4 8.5 ──P1 分修──►
08-05 R5/R6 8.6 ──独立验证──►
08-05 R7 草稿 8.7  （PR #31 窄透镜；本轮不采信抬分）
08-05 R8 8.6  （本报告 · 七维全量扫描）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：工程分在 **8.6** 平台期。再涨需要文件级 hub / 安全边界闭合 / G-1b；可售仍卡在 Commercial 三阻断。Agent 原始分跨度大（架构 7.0 ↔ 测试 8.8）——主 agent 按 R4–R6 锚点拒「更严尺子重标定」与「乐观加分」，只对**新证实且此前未定价**的债做有限下压。

---

## Agent 原始分一览（供审计）

| 维度 | Agent | 文件 |
|---|---:|---|
| 架构 | 7.0 | `tmp/r8-arch.md` |
| 质量 | 7.4 | `tmp/r8-quality.md` |
| 测试 | 8.8 | `tmp/r8-tests.md` |
| 安全 | 8.0 | `tmp/r8-security.md` |
| 文档 | 8.6 | `tmp/r8-docs.md` |
| Shell | 8.4 | `tmp/r8-shell.md` |
| 产物 | 8.2 | `tmp/r8-release.md` |
