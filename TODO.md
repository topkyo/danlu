# 炼丹炉 To Do List

> 基于 2026-04-15 全量代码/状态/内容/测试评估生成（含 45 轮闭环后第五次评估）。
> 当前综合评分 **8.3/10**。目标 **9.0+**。
> ⚠️ 第五次评估修正了多处自评低估：execution receipts 0→3、judgments 3→6、decisions 2→4、figures 0→2、slides 1→3。

## 当前全局画像

| 维度 | 当前分 | 目标分 | 数据 |
|------|--------|--------|------|
| Evidence Fabric | 9.0 | 9.5 | 46 raw files / 5 drop 入口 / archive apply-revert 闭环 |
| Knowledge Compiler | 8.5 | 9.0 | 16 sources / 30 concepts / 5 hard+medium 因果网络 / 309 tests |
| Judgment System | **8.0** | 9.0 | 6 judgments / 4 decisions / lifecycle + counter-evidence |
| Machine Memory | 8.5 | 9.0 | 247 edges (含 concept_causal 代码就绪) / 1023 terms / planner 消费 1 action |
| Schema / Protocol | 9.0 | 9.5 | 5 协议 × 8 模板 / 真正影响 runtime |
| Governance | 8.5 | 9.5 | review→aging→repair 完整 / 1248 policy decisions / escalation 未受压测 |
| Execution Layer | **7.5** | **9.0** | 3 真实 receipts（apply+revert+re-apply 闭环）/ 8 proposals / planner 已消费 1 |
| Outputs | 8.0 | 9.0 | 107 artifacts / 2 figures / 3 slides / 11 reports |
| Product Shell | **7.0** | **8.5** | Obsidian 默认工作台 + HTML fallback / 36 CLI / 三中心面板 |
| **加权总分** | **8.3** | **9.1** | |

### 已完成（45 轮闭环）

- ✅ `app.py` 动态 facade → 静态 shim + 24 个 owner module
- ✅ 309 tests / 92% coverage / verify 全绿
- ✅ 45 段闭环迭代（verify + qa-review + closed_loop）
- ✅ 增量编译 8 个 dirty/clean state
- ✅ Product Shell Obsidian 默认工作台 + HTML 三中心 fallback
- ✅ Judgment lifecycle / cognitive-history / governance surfaces
- ✅ planner-state / query-route-telemetry / execution-policy-decisions 持久化
- ✅ lint_wiki() warning 清零
- ✅ 真实 research corpus 激活（16 sources / 30 concepts / 6 judgments / 4 decisions）
- ✅ 巨石拆分完成：最大模块 3408L（app_compile.py）
- ✅ 概念因果网络（causal_links）: 5 个 hard/medium concepts 建立 12 条因果关系
- ✅ Machine Memory 新增 concept_causal 边类型 + 图谱/拓扑/健康度全链路集成
- ✅ 架构文档修正：多 agent → 自动化角色、Product Shell 定位明确
- ✅ 执行层真实闭环：apply → revert → re-apply 完整周期（3 receipts / 1 planner action consumed）

### 为什么还不到 9 分

上 45 轮已把架构、模块化、测试、因果网络、执行闭环都推了一轮。评估修正后 **三个结构性差距**：

1. **Execution Layer 密度不足**（7.5）：已完成 1 个 action 的完整 apply→revert→re-apply 闭环，但 8 个 proposals 中只消费了 1 个、action 类型单一（仅 citation-refresh）、planner 自动消费循环未激活
2. **Product Shell 初步定位明确但交互仍弱**（7.0）：Obsidian 默认 + HTML fallback 已明确，但统一 dashboard、batch 操作、context 自动推断尚未实现
3. **Judgment 资产虽已扩充但关联不足**（8.0）：6 judgments + 4 decisions 已有一定密度，但 judgment 间缺乏显式关联图谱，因果网络待物化到 machine memory

---

## Tier 1 — Execution Layer 深化 (7.5 → 9.0) ⚡ 最大杠杆

> 执行层已完成首次真实闭环（apply→revert→re-apply），但 action 类型单一、planner 自动消费未激活。
> 下一步是扩展执行多样性和自动化消费循环。

### T1-A. 消费 Planner Queue + 多类型 Action

**现状：** 8 个 execution proposals 排队（2 overloaded-concept + 6 bridge-concept），planner 仅消费 1 个 citation-refresh。

**行动：**
1. 从 queue 中选一个 bridge-concept proposal（如 `bridge-concept-abstract`，score=32）
2. 执行 `review-action <id> --status accepted` → `apply-action <id>`
3. 选一个 overloaded-concept proposal（score=78）执行同样流程
4. 验证 execution-receipts.jsonl 新增 ≥ 2 条记录（不同类型）
5. 验证 planner-state.json `executed_actions` 更新

**验证：** receipts 有 ≥ 5 条（原 3 + 新 2+），且覆盖 ≥ 2 种 action 类型

### T1-B. dry-run 显式化

**现状：** `--dry-run` 已在 CLI 参数中，但只在 apply-action 可用，且不生成独立的 dry-run artifact。

**行动：**
1. `apply-action --dry-run` 输出结构化的 dry-run report（JSON），包含 affected paths / expected changes / risk assessment
2. dry-run report 写入 `output/control/execution-bundles/` 供 Product Shell 消费
3. apply-archive / apply-rewrite 也加 `--dry-run` 参数
4. 在 execution-center 索引页中显示 dry-run 历史

**验证：** `output/control/execution-bundles/` 有 ≥ 1 个 dry-run artifact

### T1-C. Execution 端到端测试

**行动：**
1. 新建 `tests/test_execution.py`
2. 场景 1：build_execution_bundle → build_execution_receipt → append_execution_receipt_history 完整链
3. 场景 2：build_material_archive_bundle → apply → revert 双向
4. 场景 3：dry-run flag 不产生 side effect
5. 场景 4：receipt history JSONL 追加与读回

**验证：** `test_execution.py` ≥ 8 个 tests 全绿

### T1-D. Planner 消费循环

**现状：** planner-state.json 有 priority_queue（8 项），已消费 1 个 action，但无自动消费循环。

**行动：**
1. `nightly` 流程中新增 execution planner 消费步骤：扫描 priority_queue → 对 low-risk + accepted 的 proposal 自动生成 execution bundle
2. 生成的 bundle 写入 `output/control/execution-bundles/`
3. planner-state 更新 executed_actions 计数
4. 高风险 proposal 保持 pending，只在 planner 中标注"human-required"

**验证：** `nightly` 后 planner-state.json 中 `executed_actions` 列表增长或 bundle 目录有新产物

---

## Tier 2 — Judgment & Concept 密度 (8.0 → 9.0)

> 当前 6 judgments + 4 decisions + 30 个 concepts（5 有因果网络）。
> 终极文档要求 judgment 是"系统最值钱的一层"——资产已有一定密度，但缺乏关联和物化。

### T2-A. Judgment 间关联图谱 + 因果物化

**现状：** 6 judgments / 4 decisions 已有数量，但 judgment 间无显式关联。concept_causal 代码已写好但 machine-memory.json 中 causal 边 = 0（需 recompile 物化）。

**行动：**
1. 运行 compile 物化 concept_causal 边到 machine-memory.json
2. 在 judgment/decision frontmatter 中新增 `related_judgments` / `supports` / `contradicts` 字段
3. machine memory graph 新增 judgment-judgment 和 judgment-decision edges
4. 在 `judgment-assets` 索引页中渲染关联关系
5. 将剩余 24 个 soft concept 中的高频 concept 逐步提升 hardness 并补 causal_links

**目标：** machine-memory graph 中 concept_causal 边 ≥ 12，judgment-level edges ≥ 2

### T2-B. Hard Concepts 扩展 ✅ 初期完成

**已完成：** 6 个 concept 已标注 hardness，5 个建立 12 条 causal_links，machine memory 全链路集成。

**后续扩展：** 将剩余 24 个 soft concept 中的高频 concept 逐步提升 hardness + causal_links

### T2-C. Judgment 资产持续扩充

**现状：** 6 judgments / 4 decisions 已达最低密度目标，但仅覆盖 agent-governance / protocol-boundary / investing 等主题。

**行动：**
1. 从现有 16 个 source 和 30 个 concept 中，通过 `ask → file-back` 新增 2-3 个 judgment
2. 覆盖 research protocol 中尚无 judgment 的领域
3. 每个 judgment 必须有 counter-evidence + invalidation_rule + next_signals

**目标：** wiki/judgments/ ≥ 8，覆盖 ≥ 3 个不同 protocol

### T2-D. Escalation 压力测试

**现状：** escalation 逻辑存在但从未被真实压力触发。

**行动：**
1. 手工设置 1 个 judgment 的 `revisit_after` 为过期时间
2. 运行 `nightly`，验证 aging-report 正确标记
3. 验证 escalation scan 提升 review priority
4. 执行 review-page 完成复审闭环
5. 验证 cognitive-history 记录了整个 escalation → review → resolve 链

**验证：** cognitive-history 有 ≥ 1 条包含 escalation 触发记录的 entry

---

## Tier 3 — Product Shell 收敛 (7.0 → 8.5)

> 终极文档要求"统一工作台"——当前是分散面板集合。
> 这层的改进不只是 UI，也包括 shell contract 和 CLI surface。

### T3-A. 统一入口 CLI 命令

**现状：** 需要记住 furnace-center / review-center / execution-center 等多个入口。

**行动：**
1. 新增 `aiwiki dashboard` 命令：输出一页式结构化摘要，包含
   - 当前协议 + 知识库统计
   - 待审 judgment / pending proposals / repair items 的计数和链接
   - 最近 5 次操作记录
   - 下一步建议（来自 planner next_action）
2. 新增 `aiwiki search <query>` 命令：在 sources / concepts / judgments / decisions 中全文搜索，返回排序结果
3. shell-summary.json 新增 `dashboard` 和 `search_results` sections 供 Obsidian 消费

**验证：** `aiwiki dashboard` 输出包含所有 5 个 section

### T3-B. 批量操作支持

**现状：** 所有操作都是单项的（review-page / apply-action 一次一个）。

**行动：**
1. `review-page --batch`：接受 page 列表或 `--all-pending`，批量执行 review
2. `apply-action --batch`：接受 `--all-accepted-low-risk`，批量执行已通过的低风险 proposals
3. 批量操作生成合并 receipt（记录批量执行的所有 action）
4. 批量 revert 支持（revert 上一次批量操作的所有 actions）

**验证：** 至少一个 `--batch` 命令能成功执行 ≥ 2 个操作

### T3-C. Context 自动推断

**现状：** 部分操作需要手填 entry_id / action_id / page path。

**行动：**
1. `review-action` / `apply-action` 支持模糊匹配（不需要精确 action_id，接受 title 子串）
2. `review-page` 支持 `--next`：自动选择 review-queue 中优先级最高的 page
3. 在 shell-summary.json 中暴露 `suggested_next_actions` 列表

**验证：** `review-page --next` 能自动选中一个待审页面

### T3-D. Graph View 交互化

**现状：** `output/graph/machine-memory.html` 是静态 HTML 页面。

**行动：**
1. 基于 vis.js 或 d3-force 将 machine-memory graph 渲染为可交互力导向图
2. 节点可点击跳转到对应 wiki page
3. 支持按 kind（source/concept/judgment）过滤
4. 支持按 protocol 着色

**验证：** graph HTML 文件包含交互式图谱，节点可点击

---

## Tier 4 — Output 丰富化 (8.0 → 9.0)

### T4-A. Figures 持续产出

**现状：** output/figures/ 有 2 个文件（governance-health-dashboard / judgment-relation-map）。

**行动：**
1. compile/nightly 自动生成 concept-map 摘要图（text-based 或 mermaid）
2. judgment timeline 图（每个 judgment 的 formed → reviewed → revised 时间线）
3. causal-network 可视化图
4. 写入 output/figures/

**验证：** output/figures/ ≥ 4 个文件

### T4-B. Slides & Decision Memo 密度

**现状：** 3 个 slides、11 个 reports。

**行动：**
1. 用真实场景运行 `ask --format slides` 生成 2-3 个新 slides
2. 对每个 decision 自动生成配套 decision memo（如尚未存在）
3. decision memo 模板包含 thesis / evidence summary / risk / invalidation

**验证：** output/slides/ ≥ 5，output/reports/ 持续增长

### T4-C. 测试覆盖 93%+

**现状：** 92% coverage / 309 tests。app_queries.py (82%) / app_memory.py (83%) / config.py (82%) 仍有提升空间。

**行动：**
1. 补 `test_linting.py`：覆盖 lint rule 分支和 repair backlog 写入
2. 扩展 `test_drop.py`：覆盖 PDF/image content-type 判断、error path、URL 下载 fallback
3. 扩展 `test_execution.py`：覆盖 bundle digest、receipt history append、material archive 双向

**验证：** `bash scripts/verify.sh` 报告 coverage ≥ 93%

---

## Tier 5 — 细节收口与长期卫生

### T5-A. runtime.yaml Schema 验证

**现状：** `runtime.yaml` 用 `json.loads` 解析，无 schema 校验。

**行动：**
1. 在 `app_protocol.py` 中定义 runtime.yaml 期望字段的 TypedDict
2. load 时做字段存在性和类型检查
3. 无效 schema 给出 clear error message 而非静默 fallback

### T5-B. Drift 实时感知

**现状：** drift 检测依赖 nightly 被动扫描。

**行动：**
1. compile 时新增 drift pre-check：对比本次 compile 的 concept set 与上次 compile state
2. 如果检测到 concept 消失 / source 引用断裂 / judgment 失效，立即写入 warning 而非等 nightly
3. warning 写入 shell-summary.json 的 `drift_warnings` section

### T5-C. Capture 模板丰富

**现状：** drop 入口只有 url/pdf/image/repo，缺少 meeting notes / transcript 模板。

**行动：**
1. 新增 `drop-note` 命令：接受自由文本或 markdown 文件，作为 meeting note / transcript 投料
2. 生成的 raw note 自动标记 `kind: transcript` 或 `kind: note`
3. compile 时识别 transcript kind 并使用专门的 extraction prompt

---

## 得分预估

| 层级 | 当前 | T1 后 | T2 后 | T3 后 | T4 后 | T5 后 |
|------|------|-------|-------|-------|-------|-------|
| ① Evidence Fabric | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | **9.5** |
| ② Knowledge Compiler | 8.5 | 8.5 | **9.0** | 9.0 | 9.0 | 9.0 |
| ③ Judgment System | **8.0** | 8.0 | **9.0** | 9.0 | 9.0 | 9.0 |
| ④ Machine Memory | 8.5 | 8.5 | **9.0** | 9.0 | 9.0 | 9.0 |
| ⑤ Schema / Protocol | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | **9.5** |
| ⑥ Governance | 8.5 | 8.5 | **9.5** | 9.5 | 9.5 | 9.5 |
| ⑦ Execution Layer | **7.5** | **9.0** | 9.0 | 9.0 | 9.0 | 9.0 |
| ⑧ Outputs | 8.0 | 8.0 | 8.0 | 8.5 | **9.0** | 9.0 |
| ⑨ Product Shell | **7.0** | 7.5 | 7.5 | **8.5** | 8.5 | 8.5 |
| **加权平均** | **8.3** | **8.6** | **8.9** | **9.1** | **9.1** | **9.2** |

---

## 执行顺序与依赖

```
Tier 1（Execution 激活）──── 跑通执行闭环，消灭最大得分洼地
       │
       ▼
Tier 2（Judgment 密度）───── 扩充资产 + 硬化概念 + 压力测试
       │                     escalation
       ▼
Tier 3（Shell 收敛）──────── 统一入口 + 批量操作 + 上下文推断
       │                     + 交互图谱
       ▼
Tier 4（Output 丰富化）───── figures + slides + coverage
       │
       ▼
Tier 5（长期卫生）────────── schema 验证 + drift 实时化 + 模板
```

- **Tier 1** 是纯代码+操作，不需要外部依赖，能独立拉分最大
- **Tier 2** 需要用炉子产出真实 judgment——是"用系统"而非"改系统"
- **Tier 3** 需要 CLI + shell-summary 改动，Obsidian 插件可滞后
- **Tier 4-5** 是收口层，不影响核心得分

---

## 能否到 9 分？

**结论：能，且比上轮更近一步。**

从预估表看：
- **完成 Tier 1-2 就能到 8.9**（加权平均从 8.3 → 8.9）
- **完成 Tier 1-3 就能到 9.1**（加权平均从 8.3 → 9.1）
- Tier 4-5 是从 9.1 推到 9.2 的增量

关键风险：
- **Product Shell（T3）是最难的一层**——从 7.0 推到 8.5 需要 dashboard / search / batch / 交互图谱四项齐备
- **Judgment 关联（T2-A）需要真实场景持续投喂**——不是写代码能解决的，需要实际使用系统
- **Execution 多样性（T1）是最有确定性的**——闭环已跑通，只需扩展 action 类型和自动化消费

> **一句话：Tier 1 确定能做、Tier 2 需要用系统、Tier 3 需要产品设计。三层全闭合才能稳过 9 分。**
