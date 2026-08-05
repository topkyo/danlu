---
title: "Multi-Agent Reevaluation R4 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R4（hub 三 seam + corpus S2 后）

> **性质**：6 路只读扫描 + 交叉裁决。非 Active SoT 替代物。
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → R2 **8.2** → R3 **8.3** → **本轮 R4**。
> **触发**：用户要求「多 agent 全量扫描 + 多维度评估 + 评审后评分」。

**HEAD**：`8e3a564`（含 PR #28 views/ask-report seam）
**工作树**：clean（`main...origin/main`）
**规模**：`src/aiwiki` **43,860** LOC；tests **5,460** LOC

---

## 结论先行

**工程实测七维加权：8.5 / 10**（较 R3 **8.3**，**+0.2**）。

主增量来自架构（hub 三 seam 真实落地 + corpus S2 闭环验证，8.5→9.0）与代码质量（Top hub 削减，8.1→8.3）、文档（主链钉死 unit 154，8.3→8.5）；测试 / 安全 / 产物 / Shell 横盘——coverage 69% 与 Commercial 三阻断未动，涨幅因此克制。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.5** | 对内：结构债三刀落地经实测确认 |
| Scorecard Local Engineering | **9.05**（未重算八维） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

---

## 分维评分

| 维度 | 权重 | R3 | **R4** | Δ | 核心依据 |
|---|---:|---:|---:|---:|---|
| 架构与分层 | 20% | 8.5 | **9.0** | +0.5 | 三 seam 行数与承诺一致；memory 零 content import 实测确认；corpus 零反向依赖；facade 零复活；CLI 严格三命令 |
| 代码质量 / 可维护性 | 15% | 8.1 | **8.3** | +0.2 | Top hub 削减；零新增死代码；`except Exception` 65 处零退化且多伴生 rollback+raise |
| 测试与验证 | 20% | 8.2 | **8.2** | 0 | verify all EXIT=0，24/85/154/203 精确复现；coverage 69% 横盘；新观察到一次 Jest 门禁环境性误败（重跑自愈） |
| 产物完整性 / 发布 | 10% | 8.0 | **8.0** | 0 | smoke/cli-smoke/wheel/dist 全实测通过；CHANGELOG 落后 ~15 commit 抵消收益 |
| 安全与治理 | 15% | 8.7 | **8.7** | 0 | 无新可利用漏洞；SSRF/路径/注入/凭据/LLM 五面防护完整；`revert_supported` 语义缝未修 |
| 文档 SoT | 10% | 8.3 | **8.5** | +0.2 | 主链钉死 154；DEVELOPER 补 corpus owner map；CHANGELOG 三处 153 漏网；Architecture/AGENTS 仍缺 corpus 叙事 |
| 产品可用性（Shell） | 10% | 8.2 | **8.2** | 0 | Jest 203 + drift 门禁实测绿；契约双向验证成熟；render_today.js 949 行、manifest author 错误未动 |
| **加权合计** | 100% | **8.3** | **8.5** | **+0.2** | |

计算：`9.0×0.20 + 8.3×0.15 + 8.2×0.20 + 8.0×0.10 + 8.7×0.15 + 8.5×0.10 + 8.2×0.10 = 8.46 ≈ 8.5`。

---

## 交叉共识（6 路 agent 一致确认）

1. **`verify.sh all` EXIT=0**（本轮实测）：acceptance **24** / llm **85** / unit **154** / Jest **203** / docs_consistency **43 [OK]**；coverage **69%** 横盘。
2. **hub 三 seam 真实落地**：views.py 921→669 / ask.py 894→666 / io.py 881→642（io 比宣称的 677 更低，有额外清理）；外提文件 docstring 均标注 seam 日期。
3. **corpus S2 闭环**：memory 下仅 3 条 aiwiki import 且全部指向 `aiwiki.corpus.*`；corpus 包零 aiwiki import（真叶子层）。
4. **facade 零复活**：根级 `app_*.py` 零文件；CLI 顶层严格 `drop/today/advanced`，alchemy 兼容别名 `help=SUPPRESS` 隐藏。
5. **无新 P0**：无该红却绿的门禁、无可利用安全漏洞、无分层红线破防。
6. **CHANGELOG 双 agent 交叉命中**：三处 unit 153 未刷 + 最近 ~15 commit（corpus/facade/seams）未入 Unreleased。

---

## 分维要点

### 架构 9.0（+0.5）
红线全守住。余债：`runner/workflows_ask.py` 786 行成新 hub（`_complete_run_ask_artifact` 226 行单函数）；`llm.py` 695；`ask_question` 仍 ~295 行上帝函数（编排+8 个写操作未拆）。

### 可维护性 8.3（+0.2）
`_frontmatter_string_list` **4 份行为不一致拷贝**（ask.py:97 / compound_suggest.py:82 / workflows_ask_frontmatter.py:15 / judgment_assets.py:217）；`metrics_io.py:97` 静默吞错（except 后 `return ()` 无日志）；事务边界自定义 `*HalfWriteError` 是 9 分档做法。

### 测试 8.2（0）
断言质量强（字节 golden + prompt-hash replay + 负向断言，零 returncode-only）。债：16 模块 coverage <40%（memory/status.py 10%、audit_reconciliation 14%、drop/repo 18%、drop/image 19%）；**6 命令零覆盖**（run-nightly / watch / review-queue / alchemy demote / drop pdf / drop image）；Jest 门禁 npm 环境性误败一次。

### 产物 8.0（0）
wheel 边界正确（Shell 三件套不在 wheel 内）；dist 今日新鲜；build 脚本诚实无 twine。CHANGELOG 失同步是唯一实质债。

### 安全治理 8.7（0）
SSRF（含 redirect 重校验、IPv4-mapped 归一化、跨 host 剥 auth）、路径 traversal、subprocess 全 argv、凭据 repr=False+redacted、untrusted_source 包裹+闭合标记中和，全部在位且有测。债：`build_elixir_promotion_receipt` 缺 `revert_supported: true`（audit 流误标 false）；acceptance 层 revert fixture 仍缺；`drop repo` git clone 无 SSRF（默认关闭，开启后裸奔）。

### 文档 8.5（+0.2）
主链（AGENTS/Scorecard/DEVELOPER/Post-Cleanup §1）全部钉 154。余：CHANGELOG 三处 153；AGENTS/Architecture 缺 corpus 包叙事（DEVELOPER 已补）；Scorecard 更新记录停 153→154 未记；Post-Cleanup §1 工程实测仍写 8.2。

### Shell 8.2（0）
bridge 超时/上限/清理成熟；契约 kind 双向验证；drift 门禁正反向严密。余：render_today.js 949 行；纯 JS 无类型；manifest author "OpenAI Codex" 品牌错误。

### Commercial ~7.8（0）
WS1/4/5 实质 done；三阻断全开（EULA 待法律签收 / PyPI 实测 404 / Demo assets 仅 README），均为人类依赖，代码侧无可推进项。

---

## P0 / P1（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 | **无新 runtime P0**（Commercial 三阻断仍为人类 P0） |
| Q-1 | P1 | 统一 `_frontmatter_string_list` 4 份拷贝 → `utils/markdown.py` |
| Q-2 | P1 | `metrics_io.py:97` 静默吞错改显式 observability |
| A-1 | P1 | `workflows_ask.py` 786 新 hub 拆 degraded 簇；`ask_question` 295 行拆编排/持久化 |
| T-1 | P1 | 6 命令零覆盖补最小契约测（run-nightly/watch/review-queue/demote/pdf/image） |
| T-2 | P1 | Jest 门禁 npm ci 后显式校验 jest 存在，失败给可操作消息 |
| G-1 | P1 | `revert_supported: true` 补进 promote receipt；acceptance revert fixture |
| D-1 | P1-doc | CHANGELOG 三处 153→154 + 补录 ~15 commit；AGENTS/Architecture 补 corpus 叙事；Scorecard 更新记录补 153→154；Post-Cleanup §1 8.2→8.3 |
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
08-05 R4 8.5  （本报告）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：+0.2 是「hub 三 seam + corpus S2 经独立实测确认」的兑现分。距工程 **9.0** 剩余路径清晰：workflows_ask 新 hub 拆分 + 6 命令零覆盖 + coverage 破 69% 横盘；距可售仍差 Commercial 三阻断（全部人类依赖）。

---

## 后记（P1 分修 · PR #29）

本报告扫描时点在 P1 前。随后 `fix/p1-split-fixes`（merge `5530d29`）关闭本表多项 P1：Q-1 / Q-2 / T-1 / G-1（promote `revert_supported`）/ D-1 / A-1 半开（writeback seam，`ask_question` 仍记债）。**post-P1 正式复评见 `docs/plans/2026-08-05-multi-agent-reevaluation-r5.md`（工程实测 8.6）。**
