# 炼丹炉 To Do List

> 基于 2026-04-14 重构后全面评估生成。
> 综合评分 **7.4/10**（重构前 4.9）。终局架构覆盖度 **~72%**。

## 当前全局画像

| 维度 | 数据 |
|------|------|
| 核心 runtime | ~24K 行 Python（15 模块） |
| 测试 | 197 个测试函数，5,492 行 |
| 外部依赖 | **零**（纯 stdlib） |
| 模块结构 | 静态 shim + 10 owner 模块 + 3 boundary 模块，零循环依赖 |
| 最大模块 | app_content 7686L/209func — 仍是最大巨石 |
| TypedDict 覆盖 | 仅 3 个（ManifestEntry / CompileState / ShellSummary） |
| 累计 sprint | 40 轮闭环 |

### 已完成的重构

- ✅ 动态 facade 消除 → 静态 shim（app.py）
- ✅ compile_wiki() / lint_wiki() 显式 phase orchestration
- ✅ app_shell.py / app_surfaces.py / app_types.py 落地
- ✅ 零循环依赖 DAG
- ✅ manual-link ranking invalidation 修复

---

## Phase 1 — 工程收尾（残余债务清理）

### 1A. app_content.py 分解

**现状：** 7686 行 / 209 函数，是全 runtime 最大巨石。混装了 source builders、concept builders、lifecycle logic、dashboard render、HTML 模板、执行 bundle/receipt、aging/review 收集器。

**行动：**
1. 把 `render_*` 实现（render_compile_status 409L、curated_page_template 378L、render_furnace_center_html 280L、render_furnace_center 263L、render_review_center_html 221L、render_cognitive_history 153L 等）物理迁移到 `app_surfaces.py`，当前 app_surfaces 只有 re-export
2. 把 execution bundle/receipt 构建函数（build_execution_bundle、build_execution_receipt、append_execution_receipt_history、build_material_archive_receipt 等）迁移到 `app_execution.py`（新模块）
3. app_content.py 收口为：source page builders + concept builders + lifecycle logic + aging/review collectors
4. 预计 app_content.py 从 7686L 降到 ~4500L

**验证：** `bash scripts/verify.sh` 通过 + dashboard 输出不变

### 1B. app_memory.py shell 兼容 delegate 清理

**现状：** app_memory.py 仍保留 11 个 `return _app_shell.shell_X(...)` 兼容 delegate。这些只为旧的 `from aiwiki.app_memory import shell_*` 路径存在。

**行动：**
1. 确认所有 internal caller 已走 `app_shell` 直接 import
2. 把 delegate 标记为 deprecated 或直接删除
3. 更新 app.py shim 中对应的指向

**验证：** `bash scripts/verify.sh` 通过

### 1C. TypedDict 扩展

**现状：** 仅 3 个 TypedDict（ManifestEntry / CompileState / ShellSummary），全 runtime 大量 `dict[str, Any]`。

**行动：**
1. 补充 `ProtocolState`、`ExecutionBundle`、`ExecutionReceipt`、`MachineMemoryRecord`、`AgingSignal` 等高频结构
2. 在 owner 模块中逐步替换 `-> dict[str, Any]` 返回类型
3. 不追求全量覆盖，只做高频路径

**验证：** `bash scripts/verify.sh` 通过

### 1D. ruff + coverage 加入 verify.sh

**现状：** verify.sh 只做 compileall + unittest + CLI smoke，无 lint 和覆盖率。

**行动：**
1. 加 `ruff` 作为 dev 依赖，只启用 E/F/W 基础规则
2. 加 `coverage` 作为 dev 依赖
3. 更新 verify.sh：ruff check → unittest with coverage → coverage report

**验证：** verify.sh 通过 + ruff 零 error + coverage 报告可读

---

## Phase 2 — Judgment System 硬化（终局第③层，当前 60%）

这是与终局差距最大的一层。当前 judgment/decision 只是带 frontmatter 的 markdown 页面，没有真正的"资产化"治理。

### 2A. Judgment Asset 结构化元数据

**目标：** 每个 judgment/decision 必须携带机读结构化字段，不只是 prose。

**行动：**
1. 定义 `JudgmentAsset` TypedDict：citations、confidence、counter_evidence、invalidation_rule、revisit_after、escalate_after、formed_at、last_reviewed
2. judgment/decision frontmatter 强制包含这些字段
3. lint 规则：缺少必填字段的 judgment page 报 warning
4. compile 时提取这些字段进 machine memory graph

### 2B. Counter-evidence 自动收集

**目标：** 当新 source 与已有 judgment 存在潜在冲突时，系统应自动标记。

**行动：**
1. compile 阶段新增 `_counter_evidence_scan_phase()`
2. 对比新 source 的 concept terms 与已有 judgment 的 citation/thesis
3. 潜在冲突写入 `review-queue` 并标记 `counter-evidence-candidate`
4. 不自动推翻，只报给 Human Owner

### 2C. Escalation 主动工作流

**现状：** `escalate_after` 字段和 `collect_aging_signals` 中的超期检测已存在，但检测结果只写入 aging-report，不触发主动工作流。

**目标：** 超期 judgment 不只是出现在报告里，而是自动进入升级处理流程。

**行动：**
1. nightly escalation scan 结果联动 review priority 自动提升
2. 超期 judgment 进入 repair-backlog 生成 review action
3. escalation 状态在 judgment-assets 面板独立显示
4. 触发阈值可通过 protocol 配置差异化

### 2D. Judgment Lifecycle 主动治理

**目标：** judgment 不只是"写完就放着"，而是有 formed → active → under-review → revised → retired 生命周期。

**行动：**
1. 扩展 knowledge lifecycle 支持 judgment-specific states
2. 过期 judgment 自动进入 under-review
3. cognitive-history 记录每次 judgment 状态变更
4. review-center 显示 judgment 生命周期分布

---

## Phase 3 — Concept Layer 硬化（终局第②层，当前 80%）

### 3A. 概念冲突检测

**目标：** 当多个 source 对同一 concept 给出矛盾描述时，系统应标记。

**行动：**
1. concept build 阶段新增冲突检测 pass
2. 对比同一 concept 下不同 source 的 summary/terms
3. 冲突标记写入 concept-quality 和 repair-backlog
4. 不自动合并，提交给 review 工作流

### 3B. 跨源共识质量分

**目标：** concept 不只是"有几个 source 提到"，还要有质量评估。

**行动：**
1. 定义 concept quality 指标：source 覆盖度、一致性、证据深度、最近更新度
2. compile 时计算每个 concept 的 quality score
3. quality score 影响 ranking 和 review 优先级
4. concept-quality index 显示全局分布

### 3C. Concept Rewrite 完整闭环

**目标：** 当前 concept rewrite 只有 proposal 和 state 跟踪，缺少 apply → verify → feedback 闭环。

**行动：**
1. rewrite proposal 支持 dry-run preview
2. apply 后自动校验 concept graph 一致性
3. 记录 rewrite 历史到 cognitive-history
4. 支持 revert 回滚

---

## Phase 4 — Output Layer 丰富化（终局第⑧层，当前 55%）

这是终局九层中覆盖度最低的一层。

### 4A. Decision Memo 自动生成

**目标：** 从 judgment assets + 相关 source/concept 自动生成结构化 decision memo。

**行动：**
1. 定义 decision memo 模板（thesis + evidence + counter-evidence + confidence + recommendation）
2. `ask --format decision-memo` 命令支持
3. 生成结果自动关联对应的 judgment assets
4. 支持回流到 wiki/decisions/

### 4B. SOP 草案生成

**目标：** 从 execution receipts + playbooks 生成可复用的 SOP 草案。

**行动：**
1. 分析同类 execution receipt 模式
2. 抽取重复操作步骤
3. 生成 SOP 草案并标记来源
4. `ask --format sop` 命令支持

### 4C. Slides / Figures 输出框架

**目标：** 为 report 级别的输出提供更丰富的产物形态。

**行动：**
1. 定义 slide deck 输出格式（markdown-based slides）
2. 定义 figure/chart 描述格式（mermaid / ASCII）
3. `ask --format slides` 命令支持
4. 输出到 `output/slides/` 和 `output/figures/`

---

## Phase 5 — Machine Memory + Execution 成熟化（终局第④⑦层）

### 5A. Planner State（Machine Memory，当前 75%）

**目标：** machine memory 不只是被动查询层，还应有规划能力。

**行动：**
1. 定义 `PlannerState`：pending proposals、priority queue、dependency graph
2. compile/nightly 阶段维护 planner state
3. 支持 agent 查询"下一步最高价值动作"
4. 写入 agent-workbench 和 machine-memory-actions

### 5B. Execution Proposals

**目标：** machine memory 可以生成结构化的执行提案。

**行动：**
1. 从 repair-backlog + aging-report + concept-quality 自动生成 execution proposals
2. proposal 带 impact 预估、依赖、风险等级
3. 低风险 proposal 可直接进入 execution layer
4. 高风险 proposal 停在 review 边界

### 5C. Execution Policy Engine

**目标：** 当前高风险拦截逻辑是硬编码，应升级为可配置的 policy engine。

**行动：**
1. 定义 execution policy schema（allow/deny/review rules per action kind）
2. policy 可按 protocol 差异化配置
3. execution layer 统一走 policy check
4. audit log 记录每次 policy 决策

### 5D. Retrieval Route 优化

**目标：** machine memory 查询应有 route 优化，而非暴力全扫。

**行动：**
1. 维护 concept → source 的倒排索引
2. 按 query intent 选择 retrieval route（concept-first / source-first / graph-walk）
3. route 选择策略可按 protocol 配置
4. 记录 route 效果用于后续调优

---

## Phase 6 — Schema 声明化 + Product Shell 统一（终局第⑤⑨层）

### 6A. Schema 声明式 Runtime

**目标：** 当前 protocol 是代码里的 dict literal，应升级为声明式 schema 文件。

**行动：**
1. `schema/protocols/*.yaml` 定义每个 protocol 的 compile/review/nightly/execution 偏置
2. runtime 从 schema 文件加载，不再硬编码
3. 支持 protocol 热加载（无需改代码即可调整行为）
4. schema 文件可 lint / validate

### 6B. Product Shell 统一控制面板

**目标：** 当前是分散的 markdown + HTML 页面，缺乏统一入口。

**行动：**
1. 统一 shell-summary.json 为所有面板的数据源
2. 单一 HTML 页面聚合 furnace-center / review-center / execution-center / graph-view
3. 支持面板间导航和 deep-link
4. Obsidian plugin 可直接消费 shell-summary.json

### 6C. Governance Drift 自动修复

**目标：** 当前 drift 只能被检测，不能自动修复。

**行动：**
1. drift 检测结果直接生成 repair action
2. 低风险 drift（如过期 timestamp、断链引用）自动修复
3. 高风险 drift（如 concept 冲突、judgment 失效）停在 review
4. drift → repair → receipt 完整闭环

---

## 对照终局文档（Furnace Ultimate Architecture）差距总览

| 终局层 | 当前 | 目标 | 关键 Phase |
|---|---|---|---|
| ① Evidence Fabric | 85% | 90%+ | Phase 1（provenance 完善随工程收尾自然提升） |
| ② Knowledge Compiler | 80% | 92% | **Phase 3**（冲突检测 + 质量分 + rewrite 闭环） |
| ③ Judgment System | 60% | 85% | **Phase 2**（最大差距，最高优先级） |
| ④ Machine Memory | 75% | 88% | Phase 5（planner + proposals + retrieval） |
| ⑤ Schema / Protocol | 70% | 85% | Phase 6（声明式 runtime） |
| ⑥ Governance | 75% | 88% | Phase 6（drift 自动修复） |
| ⑦ Execution | 80% | 90% | Phase 5（policy engine） |
| ⑧ Outputs | 55% | 78% | **Phase 4**（memo + SOP + slides） |
| ⑨ Product Shell | 65% | 80% | Phase 6（统一面板） |

**Phase 完成后预期：72% → ~87%**

---

## 执行优先级

```
Phase 1（工程收尾）→ Phase 2（Judgment 硬化）→ Phase 3（Concept 硬化）
                                                    ↓
                                Phase 4（Output 丰富化）→ Phase 5（Memory + Execution）→ Phase 6（Schema + Shell）
```

- **Phase 1** 是后续所有 Phase 的前提——巨石模块不拆，后面的功能加不进去
- **Phase 2** ROI 最高——Judgment 是终局定义的"系统最值钱的一层"，当前只有 60%
- **Phase 3-4** 可并行推进
- **Phase 5-6** 是高阶形态，依赖前面的基础

---

## 最终四类资产对照

| 终局资产 | 当前实现 | 缺失 |
|---|---|---|
| **Hard Concepts** | concept 层存在但缺硬度 | 冲突检测 + 质量分（Phase 3） |
| **Judgment Assets** | judgment page 存在但缺结构化治理 | lifecycle + counter-evidence + escalation（Phase 2） |
| **Execution Playbooks** | bundle/receipt 存在但缺 policy | policy engine + SOP 生成（Phase 4-5） |
| **Cognitive History** | 页面存在但缺叙事连贯性 | judgment 状态变更追踪 + rewrite 历史（Phase 2-3） |

---

## 一句话

> 工程地基已稳（7.4/10），下一步重心从"代码重构"转向"功能层硬化"——优先 Judgment System，这是炼丹炉区别于普通知识库的核心差异层。
