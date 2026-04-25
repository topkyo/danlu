---
title: "炼丹炉 Agent 架构"
kind: "architecture"
status: "active"
owner: "tim"
supersedes:
  - docs/Alchemy Furnace.md
  - docs/Furnace Ultimate Architecture.md
  - docs/Furnace Protocols.md
related_docs:
  - docs/Furnace Evolution Mechanics.md
  - docs/Furnace Elixir.md
  - docs/archive/Furnace Product Shell Plugin.md
  - docs/archive/Furnace Product Shell Runtime Plan.md
---

# 炼丹炉 Agent 架构

这份文档是炼丹炉（aiwiki runtime）当前终局架构的唯一 SoT。

> **实现状态说明（2026-04-24）**：本文定义终局架构边界，不等同于所有机制均已完整落地。当前 runtime 已落地五层文件平面、显式 LLM backend、Product Shell shell-facing contract、L2 protocol-learning 生命周期、active corpus / output candidate state、repair planner state，最小金丹 `alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 链路，以及 heavy/light lane 的 read-only dry-run preview、显式 receipted action apply bridge 和 deterministic primitive receipt wrapper。完整 signal planner、heavy/light 自动执行调度器、L3 prompt/policy proposal 仍属于架构授权的待落地机制。

它同时取代：

- `Alchemy Furnace.md`（基线架构叙事）
- `Furnace Ultimate Architecture.md`（九层终局叙事）
- `Furnace Protocols.md`（一个炉子多协议）

实现契约（heavy / light 炼丹、active corpus、金丹、protocol-learning、L3 proposal）单独放在配套文档 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]] 中，本文档只负责回答“炼丹炉是什么 agent 系统，它的边界在哪”。

## 1. Positioning：炼丹炉是什么 agent 系统

**炼丹炉是一个 local-first、single-writer 的 agent 系统/引擎：它持续把 signal 驱动的证据、判断、反馈和失败模式，炼成可审计的知识资产、金丹资产与进化提案，从而实现知识复利与受控自主进化。**

它不是：

- 笔记库或静态 wiki
- 一次性 RAG 问答前端
- “会跑命令的外壳”
- hosted service / multi-user sync / 团队协作平台
- fine-tuning / 在线训练系统

它是：

- 一个跑在本地文件系统上的长期 agent runtime
- 一套以 signal → planner → phase → feedback → learning 为主轴的调度模型
- 一个会定期炼丹（light）、也会被事件触发深度重炼（heavy）的持续进化引擎
- 一个明确把自身自主权分层切分、且守住 L3 红线的系统

操作者（human owner）永远是最终裁决者。agent 是受控执行者与受控学习者，不是共同决策者，更不是炉子本身的重写者。

## 2. From Nine Layers to a Loop-First Agent Model

此前的终局架构文档用“九层模型”叙事（Evidence Fabric / Knowledge Compiler / Judgment Layer / ... / Product Shell）。本轮架构不是推翻，而是把叙事重心从“静态分层”迁移到“loop-first 控制模型”。

| 维度 | 旧九层模型 | 新 agent 模型 |
|---|---|---|
| 主叙事 | 按层级纵向堆叠 | 围绕 agent loop 展开 |
| 核心对象 | layers / stages | signals / planner / phases / feedback / learning |
| compile / review / nightly | 平行顶层命令 | 统一归为 heavy / light 炼丹两类周期 |
| Product Shell | 作为顶层第 9 层 | 降级为 surface（不是架构本体） |
| decision / judgment | 主要高价值资产 | 与 elixir 并列为一等资产 |
| 自主进化边界 | 口头化 L1/L2/L3 | 显式红线表（见 §8） |
| 对实现的冲击 | 看起来像重写 | 目录与 CLI 保留，先加 planner + proposal |

**结论**：

- **叙事上**：从“九层静态模型”替换为“持久化平面 + agent loop + autonomy boundary”。
- **实现上**：当前目录结构（`raw / wiki / .aiwiki/state / schema / output`）、治理链、执行层全部保留，并允许在其上方逐步新增完整 planner 和 proposal 机制。
- **本文档不要求推翻任何现有 CLI 命令**。

## 2.1 Current Implementation Map

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 文件平面与 deterministic baseline | implemented | `raw / wiki / .aiwiki/state / schema / output` 已是 runtime 主结构，核心 `compile / lint / nightly` 与 scoped apply/revert 写回语义不依赖 LLM。 |
| 显式 backend 选择 | implemented | `AIWIKI_LLM_BACKEND` 必须显式设置；planner 不做 backend auto-routing。 |
| Product Shell surface | implemented | 插件通过 launcher CLI 与 `output/control/shell-summary.json` 工作，不直接拥有 runtime state。 |
| L2 protocol-learning | implemented | 已有 `active / stale / demoted / archived / superseded` 生命周期与 replacement DAG 校验。 |
| active corpus / output candidates | implemented | `.aiwiki/state/active-corpora.json` 与 `.aiwiki/state/output-candidates.json` 已作为运行态工作集与候选状态。 |
| 金丹最小链路 | partial | 当前 CLI 为 `alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote`，已落 `wiki/elixirs/`、provenance 与 DAG 校验；候选目录、promote/demote/revert 语义仍待收口。 |
| planner | partial | 当前已有 `.aiwiki/state/planner-state.json` 的 repair/execution proposal planner；完整 signal planner 与 append-only planner log 未落地。 |
| heavy/light alchemy lane | partial | 已有 `aiwiki alchemy heavy|light <scope> --dry-run` 只读 preview，`--apply --action-id ...` 到既有 receipted low-risk action batch 的显式桥接，以及 `--apply --primitive compile|lint|nightly` 的 deterministic receipt wrapper；当前尚未执行 LLM-backed 或 proposal/distill lane 序列。 |
| L3 prompt/policy proposal | planned | 架构允许生成 `output/_proposals/prompt|policy`，但 runtime 入口、review queue 接线和 apply/revert 尚待实现。 |

## 2.2 9+ Feasibility Contract

为了把本轮重构从“合理愿景”推进到可落地性 9 分以上，终局架构必须遵守以下实施约束：

| 约束 | 决策 | 提升可行性的原因 |
|---|---|---|
| **Observe before schedule** | 先落 normalized signal stream 与 planner-log，只记录不自动调度。 | 先验证 signal schema、去重、scope 与 severity，不改变 runtime 行为。 |
| **Manual-first before automation** | L3 proposal、elixir candidate promote、heavy/light lane 都先支持手动触发与 dry-run。 | 人工 gate 先跑通 receipt / revert / stale hash，避免把自动化风险混入 schema 风险。 |
| **Scoped primitives only** | 新调度层只能组合现有 scoped primitives；不得引入绕过 `apply-rewrite / apply-action / apply-archive` 等链路的通用写回。 | 保留当前可审计、可回滚的执行边界，降低迁移复杂度。 |
| **Compatibility adapters over migration** | 旧 `wiki/elixirs/` 最小链路继续可读；新增 candidate plane 不强制迁移旧文件。 | 避免一次性数据迁移，把风险限制在新入口。 |
| **No hidden backend choice** | planner、heavy、light、proposal generator 都不得自动切换 LLM backend。 | 保持成本、隐私和失败模式可解释。 |
| **Kill switch by design** | 每个 planned 机制必须有 `--dry-run`、禁用开关或只读 fallback。 | 任何阶段出现坏 proposal / 坏 signal / 锁异常时可局部停用，不影响 deterministic baseline。 |

判断标准：只要某个新增能力还不能证明以上六条，就不能宣称进入“默认可用”状态，只能保持 planned 或 experimental。

## 3. Stable Invariants and Non-Goals

下列不变量在本轮重构后继续生效，任何新机制都必须证明与其兼容：

- **Single writer, many readers**：同一时刻只允许一个 writer 触碰 `wiki/` / `.aiwiki/state/` / `output/control/` / `output/packs/`。
- **`raw/` 是唯一事实输入层**：任何派生层都不得覆盖或改写 `raw/`。
- **Provenance 必须保留**：所有派生资产都应回溯到 `raw/` 或上游 wiki 证据。
- **Deterministic baseline**：核心 runtime 行为不依赖 LLM；LLM 只在显式 `run-*`、可选 vision 分析或未来 LLM-backed alchemy 路径下被调用。
- **Backend 显式手动选择**：`codex-cli / nvidia-nim-api / copilot-cli / claude-cli` 之间的切换由操作者控制，planner 不做 backend auto-routing。
- **Review / apply / revert / audit 闭环不破坏**：任何写回 `wiki/` 或 `prompts/` 或 `schema/policies/` 的动作都必须产生可回滚的 receipt 和 audit。

非目标（明确不在架构边界内）：

- Hosted service
- Multi-user sync / 实时协作
- Heavy RAG infrastructure（向量数据库集群、图数据库中间件）
- Model fine-tuning / 在线训练
- agent 自动改写 `src/aiwiki/**` 或 schema 核心结构

## 4. Formal Agent Loop

炼丹炉的运行形式化为一条受控 loop：

```
signal → planner → phase → feedback → learning
   ^                                       |
   |                                       v
   +--- re-enter as new signal ------------+
```

### 4.1 Signal（感知）

signal 是完整 planner 的唯一输入来源。目标 signal 包括（非穷举）：

- `raw/` 变化（drop-url / drop-pdf / drop-image / drop-repo / 手工添加）
- `counter-evidence` 出现（判断被证据反驳）
- `drift` 检测命中（nightly 发现 judgment 基础证据已变）
- 用户 `review` 反馈（accept / reject / rewrite）
- `runtime failure` 模式（contract validation 持续失败、lint 反复回归）
- `schedule tick`（nightly / weekly / periodic light tick）
- `protocol-learning` 累积阈值命中
- 金丹 `dependency` 断裂（被引用的 elixir 被 demote / superseded）

每条 signal 都被标准化为：

```
{ kind, scope, severity, protocol, evidence_refs, budget_hint }
```

signal **不直接触发命令**，必须先进入 planner。

### 4.2 Planner（决策）

planner 在 signal 和当前系统状态（active_corpus、aging、review backlog、budget）之间做路由决策，输出以下之一：

- `ignore`（信号不值得处理）
- `enqueue-light`（收入 light 炼丹队列）
- `enqueue-heavy`（触发 heavy 炼丹）
- `generate-proposal`（生成 L2/L3 proposal；L3 当前为 planned）
- `escalate-human`（需要人工介入）

planner **只能调度已被允许的 phase 集合**，不允许发明新的写回路径。planner 的决策全程可审计。

### 4.3 Phase（执行）

phase 是一组受控的执行原子，当前集合：

- `route`（scope 识别、dependency graph 解析）
- `compile`（metadata / source / concept / index / cold maintenance，见增量 compile 契约）
- `judge`（judgment / decision 刷新）
- `distill`（候选金丹生成）
- `lint`（drift / contract 校验）
- `review`（进入 review queue）
- `propose`（生成 prompt / policy proposal）
- `apply`（accept 后写回目标文件）
- `revert`（按 receipt 回滚）

所有 phase 都必须映射到已有或待补的受控 CLI primitive；本轮架构不新增绕过 CLI / receipt / audit 的物理执行路径，只在既有 primitives 上方加调度。

### 4.4 Feedback（反哺）

每次 phase 执行完都产生 machine-readable feedback：

- `receipt`（谁做了什么、输入、输出、可否 revert）
- `audit entry`（appended-only 审计记录）
- `drift result`（新的漂移/冲突证据）
- `review outcome`（用户最终裁决）
- `failure cluster`（反复失败的模式，供 L3 propose 使用）

feedback 会重新进入 signal 流，构成 loop 的闭合。

### 4.5 Learning（进化）

learning 是 loop 的唯一合法“进化出口”。它只允许落到三个受控位置：

- **L1 runtime state**（`.aiwiki/state/*`、temperature、active corpus 降温）
- **L2 protocol-learning**（`wiki/protocol-learnings/` 的候选/老化/supersede）
- **L3 prompt/policy proposal**（`output/_proposals/prompt/`、`output/_proposals/policy/`，当前为 planned）

learning 不允许自动改 `src/aiwiki/**`，不允许自动改 schema 核心结构，不允许越过 review 链直接写入 `prompts/*.md` 或 `schema/policies/*`。

## 5. Persistent Planes and Asset Topology

把系统表述为“平面”而不是“层”，更贴近 runtime 的真实物理结构：

| 平面 | 物理位置 | 角色 |
|---|---|---|
| **事实平面** | `raw/` | 唯一事实输入，不可被派生层覆盖 |
| **知识/判断平面** | `wiki/sources/`、`wiki/concepts/`、`wiki/decisions/`、`wiki/judgments/`、`wiki/elixirs/`、`wiki/protocol-learnings/` | 人读资产；派生输出 + 凝丹 + 经验沉淀 |
| **运行态平面** | `.aiwiki/state/*` | machine-readable runtime state（manifest、active corpus、compile state、aging、routing） |
| **规则平面** | `schema/`、`prompts/` | 系统行为的显式契约；L3 proposal 的目标目录 |
| **产物/Proposal 平面** | `output/_candidates/`、`output/_proposals/`、`output/reports/`、`output/packs/` | 候选区、提案区、最终导出 |

关键约束：

- 派生平面**永远**不能向事实平面写回。
- 运行态平面可由事实平面 + 近期运行历史增量重建。
- 规则平面的变更必须经过 L3 proposal 链，不允许 agent 直接写。

## 6. Heavy Alchemy and Light Alchemy

两种炼丹周期在 agent loop 上是 planner 的两条执行 lane，而不是两套独立系统：

```
                   ┌──────────────┐
 signals ────────▶ │   Planner    │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┐
              ▼                       ▼
       ┌────────────┐          ┌────────────┐
       │  Heavy     │          │   Light    │
       │ Alchemy    │          │  Alchemy   │
       └─────┬──────┘          └─────┬──────┘
             │                       │
             └──────────┬────────────┘
                        ▼
                 ┌────────────┐
                 │ Phase exec │
                 └─────┬──────┘
                       ▼
               feedback → learning
```

- **Heavy Alchemy**：事件驱动、深链路、作用域有限定。处理“知识意义被改变”的信号（新事实、反证、drift 大范围命中、金丹断裂、protocol-learning 结构调整）。
- **Light Alchemy**：定时驱动、窄链路、预算严格。处理“知识卫生”事务（nightly aging、候选区清理、index 刷新、cold/archive 建议）。
- **锁与优先级**：两者共享 single writer 锁；heavy 优先；light 拿不到锁即 skip，不做长等待。
- **不允许 light 静默升级为 heavy**。

具体契约见 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]] §4 / §5。

## 7. Elixir as a First-Class Asset

金丹（Elixir）在本轮架构里升格为与 `judgment` / `decision` 并列的一等知识资产。

核心定位：

- **复合资产**：金丹不是更高级的 judgment，它是对多个 judgment / decision / source 的综合凝结。
- **知识复利节点**：新金丹可以引用旧金丹，形成真正的长期杠杆；但引用链必须是 DAG，且不能只靠旧金丹的结论自举，必须继续锚定底层证据。
- **独立生命周期**：与 judgment 的状态机完全分离。
  - 目标候选平面：`output/_candidates/elixirs/`（未通过人工 promote；planned）
  - 当前持久平面：`wiki/elixirs/`（当前最小链路由 `alchemy-promote` 产生 `settled`）
- **Provenance 强制**：目标 schema 要求每个金丹携带 `derived_from`、`judgment_refs`、`counter_evidence`、`confidence_level` 和 `corpus_id`；当前最小实现已强制 `derived_from` 与 corpus provenance，并校验必须包含底层 `wiki/derived/` 源条目。

存储决策（本轮最终结论）：

- **存在 `wiki/elixirs/`，而非作为 judgment 的附加状态，也不在 `active_corpus` 原地升格。**
- 理由：金丹是长期资产，`active_corpus` 是运行态工作集；两者的生命周期和物理位置必须严格分离。

完整 schema / 生命周期 / 三阶段路线图（Chaining → Distillation → Compounding）见 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]] §7 / §8。

## 8. Autonomy Boundaries: L1 / L2 / L3

本轮架构最关键的边界决策：**L3 红线只开 proposal-only 一条缝——agent 可生成对 `prompts/*.md` 和 `schema/policies/*` 的 proposal，但必须人工 accept 才能写回。** 当前 runtime 尚未落地 L3 prompt/policy proposal 执行链；本文只定义授权范围与红线。

红线表：

| 层级 | 可以自动做 | 需要人工 accept | 永不允许自动做 |
|---|---|---|---|
| **L1 知识 / 运行态自维护** | `.aiwiki/state/*` 更新、active corpus 收敛、targeted compile / lint、索引刷新、候选产物生成 | 正式写入高价值长期资产（promote elixir）、高风险 apply | 覆盖 `raw/`；绕过 receipt / audit；隐式切换 backend |
| **L2 Protocol-learning** | 聚类 review 反馈、生成 learning 候选、老化、supersede；replacement graph 校验 | 将新 learning 置为 `active`；默认装载到 ask 路径 | 隐式改 prompt / policy；跨 protocol 污染；破坏 replacement DAG |
| **L3 Prompt/Policy Proposal**（planned） | 生成 proposal 到 `output/_proposals/prompt/`、`output/_proposals/policy/`，附证据、patch 说明和 revert 信息 | 写回 `prompts/*.md`、`schema/policies/*` | 自动修改 `src/aiwiki/**`；自动修改 schema 核心结构；自动改 protocol core contract |

补充规则：

- L3 proposal **物理目录独立**，但**逻辑接入现有 review queue**，复用 review / apply / revert / audit 语义。
- L3 proposal 目标文件范围 **只限** `prompts/*.md` 与 `schema/policies/*`；其他规则文件（protocol 定义、schema 核心）不在本轮开口。
- 任何 L3 accept 必须产生可回滚 receipt；若 target 文件已被人手修改且无法 clean revert，则退化为人工 merge 提示而不是强制 revert。

## 9. Protocols, Operator Control, and Backend Selection

**"一个炉子，多个 protocol"** 的原则本轮继续生效：

- Protocol 当前集合：`general / investing / research / product / ops`。
- Protocol 作用在：
  - planner 的 bias（热区偏好、review 频次、light 节奏）
  - review cadence（不同 protocol 的老化速度不同）
  - elixir compounding（同 protocol 内的金丹复利优先）
  - output 模板与 judgment 字段
- Protocol **不是硬隔离**：跨协议证据（bridge evidence）在 graph / judgment / drift 信号触发时允许被召回。

操作者控制：

- Backend 选择始终通过环境变量或 Product Shell / launcher settings 显式手动配置，不在 planner 决策范围内。
- 人工 accept / reject 是跨边界写回（L1 promote / L2 activate / L3 apply）的唯一最终门槛。

## 10. Compatibility Proof with the Current Runtime

对 §3 的每条不变量逐条证明兼容：

| 不变量 | 兼容性 |
|---|---|
| **Single writer** | 完整 planner 落地后不直接写业务文件；所有写操作仍走现有 phase primitives，共享同一锁。 |
| **`raw/` 不可覆盖** | agent loop 所有学习出口（L1/L2/L3）都在派生平面或规则平面，`raw/` 永远不是写目标。 |
| **Provenance** | 已落地资产继续保留 evidence / corpus provenance；目标金丹与 L3 proposal schema 进一步强制证据锚点。 |
| **Deterministic baseline** | core runtime（compile / lint / nightly 与 scoped apply/revert 写回语义）保持决定论，LLM 只在显式 `run-*`、可选 vision 分析或未来 LLM-backed alchemy 路径被调用。 |
| **Backend 显式选择** | planner 不做 backend routing；backend 切换仍由 operator 通过 env / launcher settings 显式指定。 |
| **Review / apply / revert / audit** | 既有 execution / rewrite / candidate 写回继续走 review / receipt / audit；L3 proposal 落地时必须接入同一语义。 |

**结论**：新架构不要求改变任何现有 CLI 命令的语义，也不要求新增任何破坏性迁移。完整 planner 和 L3 proposal 是在既有 primitives 之上的增量调度层。

可行性判定：

- 当前文档版可作为 9+ 落地蓝图，但不是宣称 runtime 已达到 9+ 自动化成熟度。
- 9+ 的工程条件是：signal / planner-log 可重放，candidate / proposal 可 dry-run，所有写回均有 receipt + hash gate + revert，heavy/light 默认只组合 scoped primitives。
- 若后续实现需要突破任一条件，必须回到本文档修订，而不是在代码里隐式扩权。

## 11. What This Document Does Not Define

为了避免架构文档膨胀，以下内容**不**在本文档定义：

- 具体 signal schema、planner routing rule、phase 契约细节 → 见 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]]
- active corpus / elixir / learning / proposal 的 frontmatter 详细字段 → 见进化机制文档
- Product Shell surface / UI contract → 当前参考归档史料 [[docs/archive/Furnace Product Shell Plugin|产品壳插件]] / [[docs/archive/Furnace Product Shell Runtime Plan|产品壳 runtime 计划]]
- 具体 EP 实施路线 / 时间表 → 见 `PROGRESS.md` 与 `.codex/plans/active.md`

## 12. Document Status and Supersede Map

本文档取代：

- `docs/Alchemy Furnace.md`（基线叙事被 §1 / §5 / §10 吸收）
- `docs/Furnace Ultimate Architecture.md`（九层叙事被 §2 / §5 / §6 / §7 / §8 吸收）
- `docs/Furnace Protocols.md`（一个炉子多协议被 §9 吸收）

旧文档应物理归档到 `docs/archive/`，并在 frontmatter 标注 `superseded_by: docs/Furnace Agent Architecture.md`。

配套文档（未被取代，继续生效）：

- [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]]：实现契约 SoT
- [[docs/Furnace Elixir|金丹机制 thesis]]：金丹产品思路（仍 accepted）
- [[docs/archive/Furnace Product Shell Plugin|产品壳插件]]：surface 契约史料
- [[docs/archive/Furnace Product Shell Runtime Plan|产品壳 runtime 计划]]：shell-runtime 契约史料
