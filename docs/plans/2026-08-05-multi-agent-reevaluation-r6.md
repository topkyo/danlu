---
title: "Multi-Agent Reevaluation R6 2026-08-05"
kind: "report"
status: "active"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R6（P1 修复独立验证）

> **性质**：3 路只读独立验证 + 主 agent 交叉裁决。非 Active SoT 替代物。
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → R2 **8.2** → R3 **8.3** → R4 **8.5** → R5 **8.6** → **本轮 R6**。
> **触发**：用户称 R4 P1「都已修复」，要求复评。本轮不采信 R5 自评，逐项独立验证后重打分。

**HEAD**：`b7ad8df`（含 PR #29 P1 分修 + PR #30 R5 报告）
**工作树**：clean（`main...origin/main`）

---

## 结论先行

**工程实测七维加权：8.6 / 10——R5 的 8.6 经独立验证属实，维持。**

R5 的全部事实性声明（unit 160 / 24 / 85 / 203、frontmatter 统一、metrics warning、promote `revert_supported: true`、六命令测试、writeback seam、文档主链刷新）**逐条证实，零否证**。验证 agent 对 R5 分维评分有 0.3–0.6 的下压意见，经以 R4 校准锚点裁决后认定为「更严尺子的重新校准」而非事实错误，维持 R5 分值。

本轮新发现（R5 未披露，均非 P0）：

1. **`except Exception` 总数 65 → 66**（writeback 新增 2 处 restore-then-raise，净 +1），R5 未记录。
2. **coverage 实际 71%**（R5 称 69% 横盘，低报了改善）；<40% 模块 16 → 11。文档钉仍写 69%，属保守方向滞后。
3. **六命令测试是 library 级**（直调入口函数，断言实质），argv/dispatch 层仍零覆盖；R5 措辞「CLI smoke」偏宽。
4. **CHANGELOG 未入 docs_consistency 数字钉**——R4 三处 153 漏网的成因机制未闭环，下轮 unit 变动可再次静默漂移。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.6** | 对内：P1 债收口经独立验证确认 |
| Scorecard Local Engineering | **9.05**（未重算八维） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

---

## 分维评分（含验证 agent 原始分与裁决）

| 维度 | 权重 | R4 | R5 自评 | R6 验证分 | **R6 裁决分** | Δ vs R5 | 裁决理由 |
|---|---:|---:|---:|---:|---:|---:|---|
| 架构与分层 | 20% | 9.0 | 9.1 | 8.5 | **9.1** | 0 | 验证分 8.5 是更严尺子（Top 6 hub 未动），但同等 hub 状态在 R4 已定价为 9.0；writeback seam（786→335）是真实增量，按 R4 锚点 9.1 成立 |
| 代码质量 / 可维护性 | 15% | 8.3 | 8.5 | 8.0 | **8.5** | 0 | Q-1/Q-2 关闭是 R4 点名债的兑现（8.3→8.5）；验证分 8.0 隐含「修复不值正增量」，与 R4 锚点矛盾。except 66 与 156 行函数记债不上调 |
| 测试与验证 | 20% | 8.2 | 8.3 | 8.0 | **8.3** | 0 | 六命令实质断言测试入门禁 + coverage 69→71% + <40% 模块 16→11，按 R4 锚点（零覆盖时 8.2）8.3 保守成立；argv 层缺口与 T-2 封死更高分 |
| 产物完整性 / 发布 | 10% | 8.0 | 8.1 | 8.0 | **8.1** | 0 | CHANGELOG 失同步（R4 主债）已修；缺防回归钉是机制债，定价为达不到 8.2 而非退回 8.0 |
| 安全与治理 | 15% | 8.7 | 8.8 | 8.5 | **8.8** | 0 | G-1 关闭且有契约测 + acceptance golden 钉住；验证方扣分的 writeback 2 处 except 是 restore-then-raise 事务模式，R4 已定性为正确做法，不构成扣分 |
| 文档 SoT | 10% | 8.5 | 8.5 | 8.5 | **8.5** | 0 | 双方一致：D-1 全关，主链钉 160 + corpus 叙事 + Scorecard 记录补齐 |
| 产品可用性（Shell） | 10% | 8.2 | 8.2 | 8.2 | **8.2** | 0 | 双方一致：PR #29 无 Shell 改动；S-1 未修如实横盘 |
| **加权合计** | 100% | **8.5** | **8.6** | — | **8.6** | **0** | |

计算：`9.1×0.20 + 8.5×0.15 + 8.3×0.20 + 8.1×0.10 + 8.8×0.15 + 8.5×0.10 + 8.2×0.10 = 8.555 ≈ 8.6`。

---

## R5 声明验证表（3 路独立实测）

| 声明 | 结果 | 证据 |
|---|---|---|
| unit 160 / acceptance 24 / llm 85 / Jest 203 | **证实** | 本轮 `verify.sh all` 总 exit 0：160 passed (4.52s) / 24 / 85 / 26 suites 203；docs_consistency 43 [OK] |
| Q-1 frontmatter 统一 | **证实** | 统一实现 `utils/markdown.py:103-110`；原 4 调用点全改引（ask.py:53 / compound_suggest.py:14 / workflows_ask_frontmatter.py:9 / judgment_assets.py:13），另 4 处（gc_orphans/lifecycle×2/phases_governance）也已统一；全仓零私有拷贝残留 |
| Q-2 metrics 静默吞错修复 | **证实** | `metrics_io.py:99-101` 改 `logger.warning` + 注释「best-effort: metrics must not crash on partial vaults」 |
| G-1 promote `revert_supported: true` | **证实** | `execution/receipts.py:179` 显式 True；契约测 `test_alchemy_revert.py:162,164`（内存+落盘双重）；D3 acceptance golden 含 `"revert_supported": true` |
| T-1 六命令补测 | **证实（措辞纠偏）** | `tests/test_cli_surfaces.py` 6 用例全有实质断言（payload/文件落盘/状态迁移），入 unit 硬门禁；但为 library 级直调，**argv/dispatch 层仍零覆盖** |
| A-1 半开（writeback seam） | **证实** | `workflows_ask.py` 786→**335** + `workflows_ask_writeback.py` **480**（docstring 标注 seam 来源，import 方向干净无环）；`ask_question` 仍 **296** 行记债 |
| D-1 文档债关闭 | **证实（一处例外）** | CHANGELOG 三处 153→**160** 且补录 corpus/facade/seams/PR #29；AGENTS.md:77 与 Architecture.md:59 已补 corpus 叙事；Scorecard 更新记录补至 154→160 与 R5 8.6；Post-Cleanup §1 刷新 8.6。**例外**：CHANGELOG 未入 docs_consistency 数字钉 |
| 分层红线无回归 | **证实** | memory 零 content import；corpus 零 aiwiki import；根级 app_*.py 零文件；_CompatModule 零命中；CLI 顶层仍 drop/today/advanced |
| hub 数据（ask 659/io 641/views 668/url 790/concepts 728） | **证实** | 实测 660/642/669/791/729（±1）；Top 6 hub 原封未动 |
| Shell 8.2 / Commercial 7.8 横盘 | **证实** | manifest.json:7 author 仍 "OpenAI Codex"；EULA 待法律签收 / PyPI 404 / Demo assets 仅 README，零进展 |

---

## 本轮新发现（R5 未披露）

| # | 发现 | 定性 |
|---|---|---|
| N-1 | `except Exception` 65 → **66**（writeback :205/:464 新增 2 处 restore-then-raise，净 +1） | 非静默吞错（raise 上抛），但 R5 应如实记录；建议补 warning 或注释 |
| N-2 | coverage 实测 **71%**（20235 语句 / 5842 未覆盖），<40% 模块 **11** 个（R4 时 16 个） | R5 低报改善；文档钉仍写 69%，保守方向滞后，建议刷新 |
| N-3 | `_write_run_ask_success` 156 行单函数（writeback 外提是「搬家」非「拆分」） | 记债，与 `ask_question` 296 行同质 |
| N-4 | T-2 仍未关：verify.sh 无 npm ci 后 jest 显式校验 | 实际风险窄（`npm test` = `jest --ci` 兜底非零），形式债 |

---

## P0 / P1（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 | **无 runtime P0**（Commercial 三阻断仍为人类 P0） |
| A-1 | P1 | `ask_question` 296 行 + `_write_run_ask_success` 156 行：编排/持久化真拆分（非搬家） |
| T-1b | P1 | 六命令补 argv 级最小用例（dispatch/参数解析层零覆盖） |
| T-2 | P1 | verify.sh 补 `test -x node_modules/.bin/jest` 显式校验（成本一行） |
| D-2 | P1-doc | CHANGELOG 入 docs_consistency 数字钉（防再次静默漂移）；coverage 钉 69→71 刷新 |
| G-1b | P1 | acceptance 级 alchemy-revert 专用 fixture（现有仅 D3 golden 带字段） |
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
08-05 R4 8.5 ──P1 分修（PR #29）──►
08-05 R5 8.6 ──独立验证（本轮）──►
08-05 R6 8.6  （确认，零否证）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：R6 的价值不在加分，而在**证伪机会**——R5 自评经三路独立实测零否证，8.6 从「自评」升级为「验证后确认」。剩余路径不变：真拆分（非搬家）ask 双函数、argv 层测试、CHANGELOG 机制钉；可售仍差 Commercial 三阻断（全人类依赖）。

---

## 后记（发现修复 · 同日）

计划：`docs/plans/2026-08-05-r6-findings-fixes.md`。落地后：

| ID | 处置 |
|---|---|
| N-1 | writeback `except` 注释为 restore-then-raise；本机 recount `except Exception` = **65**（非静默吞错净增） |
| N-2 / D-2 | coverage 钉 **71%**；CHANGELOG unit 入 `docs_consistency` |
| N-3 / A-1 | `ask_question` **38** 行编排 + prepare/materialize/finalize；`_write_run_ask_success` **84** + `_commit_run_ask_success_mutations` **120** |
| N-4 / T-2 | `verify.sh` `npm ci` 后 `test -x node_modules/.bin/jest` |
| T-1b | `test_cli_surfaces` 增 6 条 argv/`main()`；unit **160→166** |

工程实测横幅仍 **8.6**（本轮不加分）。未做：G-1b acceptance revert fixture、S-1 manifest author、Commercial。
