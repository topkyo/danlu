---
title: "Multi-Agent Reevaluation R7 2026-08-05"
kind: "report"
status: "superseded"
created_at: "2026-08-05"
---

# 炼丹炉多 Agent 复评 R7（R6 findings 修复独立验证）

> **状态**：已被 R8 全量扫描取代抬分结论（工程分维持 **8.6**，不采信本报告 **8.7**）。见 `docs/plans/2026-08-05-multi-agent-reevaluation-r8.md`。PR #31 事实验证表仍可作史料。
> **性质**：3 路只读独立验证 + 主 agent 交叉裁决（hub 行数经主 agent 实测修正）。非 Active SoT 替代物。
> **前序**：08-03 **7.4** → 08-04 **6.8** → 08-05 早 **7.9** → R2 **8.2** → R3 **8.3** → R4 **8.5** → R5 **8.6** → R6 **8.6**（确认）→ **本轮 R7**。
> **触发**：PR #31（R6 findings 修复）后用户要求复评。PR 自述「不加分」，本轮独立验证后重新裁定。

**HEAD**：`ec7bc7c`（含 PR #31 R6 findings 修复）
**工作树**：clean（`main...origin/main`）

---

## 结论先行

**工程实测七维加权：8.7 / 10**（较 R6 **8.6**，**+0.1**）。

PR #31 的全部声明经独立验证**零否证**：`ask_question` 296→38 行编排是真拆分（非搬家）、argv 层 6 命令测试真实走 dispatch、T-2/D-2 机制钉落地、unit **166** / docs_consistency **46 [OK]** 全绿。PR 自述「不加分」属保守——R4 以来的头号架构债（296 行上帝函数）与 R6 全部测试债的实质关闭，按既有校准锚点值 +0.1。

诚实注记：ask.py 文件行数 660→**764**（拆分显式化接口的代价），上帝函数消失但文件未瘦身；`_finalize_ask_question` 仍 186 行。

| 尺子 | 分 | 可否对外怎么说 |
|---|---:|---|
| 本报告工程实测（七维） | **8.7** | 对内：R6 findings 修复经独立验证确认 |
| Scorecard Local Engineering | **9.05**（未重算八维） | fixture 就绪；不可冒充 live / 可售 |
| Live Dogfood | **not-yet** | 不得宣称 AgentOS 9 live |
| Commercial Go-Live | **~7.8** | 三阻断仍开；不可诚实可售 |

---

## 分维评分

| 维度 | 权重 | R5 | R6 | **R7** | Δ | 核心依据 |
|---|---:|---:|---:|---:|---:|---|
| 架构与分层 | 20% | 9.1 | 9.1 | **9.2** | +0.1 | A-1 关闭：ask_question 38 行编排 + prepare(72)/materialize(104)/finalize(186) 三段正交；红线全绿 |
| 代码质量 / 可维护性 | 15% | 8.5 | 8.5 | **8.7** | +0.2 | 上帝函数消失；`_write_run_ask_success` 156→84 + commit 120；except Exception 回 **65**；restore-then-raise 注释到位 |
| 测试与验证 | 20% | 8.3 | 8.3 | **8.5** | +0.2 | T-1b argv 层真覆盖（argparse→dispatch→JSON）；T-2/D-2 关闭；unit 166 实测两轮一致 |
| 产物完整性 / 发布 | 10% | 8.1 | 8.1 | **8.1** | 0 | 本轮无产物面改动 |
| 安全与治理 | 15% | 8.8 | 8.8 | **8.8** | 0 | 无安全面改动；G-1b 仍 open |
| 文档 SoT | 10% | 8.5 | 8.5 | **8.6** | +0.1 | D-2 闭环：coverage 钉 71%、CHANGELOG unit 入钉；Active SoT 五处全对齐 166/71% |
| 产品可用性（Shell） | 10% | 8.2 | 8.2 | **8.2** | 0 | 无 Shell 改动；S-1 仍 open |
| **加权合计** | 100% | **8.6** | **8.6** | **8.7** | **+0.1** | |

计算：`9.2×0.20 + 8.7×0.15 + 8.5×0.20 + 8.1×0.10 + 8.8×0.15 + 8.6×0.10 + 8.2×0.10 = 8.655 ≈ 8.7`。

**裁决说明**：测试验证 agent 原始分 8.6，主 agent 下压至 8.5——新 argv 用例与 library 级 1:1 镜像（边际价值有重叠）、`test_cli_surfaces.py:157` promote 断言为三选一 OR 弱断言（被 demote 断言间接兜底）、T-2 新写失败消息内修复路径 `product-shell/obsidian-plugin` 不存在（真实路径 `.obsidian/plugins/furnace-product-shell`）——本 PR 自产的消息瑕疵封死 8.6。可维护性验证 agent 原始分 8.8，下压至 8.7——`_finalize_ask_question` 186 行与 `_commit_run_ask_success_mutations` 21 参数仍记债。

---

## PR #31 声明验证表（3 路独立实测）

| 声明 | 结果 | 证据 |
|---|---|---|
| unit 160→166（+6 argv 用例） | **证实** | 两轮实测 166 passed；`test_cli_surfaces.py` 12 条 = 6 library（L32-85）+ 6 argv（L99-173），argv 经 `cli.dispatch.main()` 真走 argparse→路由→JSON，零 mock |
| ask_question 296→38 真拆分 | **证实** | `execution/ask.py:684-721` 编排 38 行；prepare `:322-393` / materialize `:394-497` / finalize `:498-683`；8 个写操作全部仍在执行路径且顺序不变，llm-integration 用例钉住副作用 |
| _write_run_ask_success 156→84 + commit 120 | **证实** | `workflows_ask_writeback.py:466-544`（lock+snapshot+restore）/ `:344-464`（持久化 mutations 集中）；restore-then-raise 注释 `:205-206`/`:536-537` |
| except Exception 回 65 | **证实** | rg 逐文件求和 = 65（R6 实测 66，净 -1） |
| T-2 jest 显式校验 | **证实（瑕疵）** | `verify.sh:175-179` `[[ ! -x node_modules/.bin/jest ]]` + exit 1；但 :177 修复提示路径已失效（P2） |
| D-2 coverage 71% + CHANGELOG 入钉 | **证实** | `docs_consistency_check.sh:143`（CHANGELOG unit 166）/`:144-145`（coverage 71% ×2）；探针实证改错数字门禁会红；docs_consistency 43→**46 [OK]** |
| 分层红线无回归 | **证实** | 无新环；memory 零 content；corpus 叶子；facade 零复活 |
| 全量门禁 | **证实** | `verify.sh all` EXIT=0：166/24/85/203/46 [OK]；coverage 71%（11 个 <40% 模块与 R6 持平） |

---

## Hub 现状（主 agent 实测修正）

验证 agent 的 hub 表部分为估值，主 agent `wc -l` 实测 Top 10：

| 文件 | 行数 | 备注 |
|---|---:|---|
| drop/url.py | 790 | 未动 |
| lifecycle/knowledge.py | 788 | 未动 |
| runner/prompts.py | 778 | 未动 |
| execution/ask.py | **764** | 660→764（+104：拆分显式接口代价；最大函数从 296→186） |
| compile/ranking.py | 731 | 未动 |
| content/concepts.py | 728 | 未动 |
| app_shell/summary.py | 709 | 未动 |
| llm.py | 694 | 未动 |
| memory/graph_query.py | 673 | 未动 |
| render/views.py | 668 | 未动 |

**解读**：函数级债（上帝函数）已还，文件级 hub 未瘦。下轮架构分再上需要文件级拆分（url/knowledge/prompts/ask），而非函数级。

---

## P0 / P1 / P2（本轮）

| ID | 级别 | 项 |
|---|---|---|
| — | P0 | **无 runtime P0**（Commercial 三阻断仍为人类 P0） |
| A-2 | P1 | 文件级 hub：url 790 / knowledge 788 / prompts 778 / ask 764 / ranking 731 / concepts 728 |
| A-3 | P2 | `_finalize_ask_question` 186 行可再拆；`_commit_run_ask_success_mutations` 21 参数可考虑 context 对象 |
| T-3 | P2 | `test_cli_surfaces.py:157` promote 三选一 OR 弱断言改确定字段 |
| T-4 | P2 | `verify.sh:177` jest 失败消息修复路径改 `.obsidian/plugins/furnace-product-shell` |
| D-3 | P2 | CHANGELOG 钉为全文件 presence 匹配（3 处冗余稀释敏感度），可锚定 Unreleased 小节 |
| G-1b | P1 | acceptance 级 alchemy-revert 专用 fixture（仍 open） |
| S-1 | P1 | Shell manifest author 品牌修正（分发前，仍 open） |
| C-1 | P1 | Commercial 三阻断（人类，仍 open） |

---

## 历史对照

```text
08-03  7.4 ──W0–W6──►
08-04  6.8 ──F-1~F-13──►
08-05 早 7.9 ──R-5/repair──►
08-05 R2 8.2 ──corpus+facade+优先债──►
08-05 R3 8.3 ──hub 三 seam + corpus S2──►
08-05 R4 8.5 ──P1 分修（PR #29）──►
08-05 R5 8.6 ──独立验证确认（R6）──►
08-05 R6 8.6 ──R6 findings 修复（PR #31）──►
08-05 R7 8.7  （本报告 · 独立验证后裁定）
Scorecard Local  9.05
Commercial       ~7.8
```

**解读**：+0.1 是「R4 头号架构债（296 行上帝函数）+ R6 全部测试债」实质关闭的兑现。工程分进入 8.7 后，剩余路径全部变重：文件级 hub 六座（790/788/778/764/731/728）、coverage 无门禁、G-1b fixture；可售仍差 Commercial 三阻断（全人类依赖）。PR #31 自述「不加分」是保守，独立裁定 +0.1。
