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

> **实现状态说明（2026-04-26）**：本文定义终局架构边界，不等同于所有机制均已完整落地。当前 runtime 已落地五层文件平面、显式 LLM backend、Product Shell shell-facing contract、L2 protocol-learning 生命周期与显式 activation revert baseline、active corpus / output candidate state、repair planner state，最小金丹 `alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 链路、legacy migration read-only preview + explicit apply baseline 与 superseded cleanup dry-run + deletion apply baseline，planner-log observe-only / execute-mode decision log 与 rollback marker baseline，heavy/light lane 的 read-only dry-run preview、显式 receipted action apply bridge、deterministic primitive receipt wrapper、显式 heavy lane `review` / `distill` / `propose` primitive apply、execute-mode `alchemy auto` deterministic 调度入口与显式 heavy `review` / `distill` / `propose` opt-in、lane primitive trace/audit metadata、高风险 primitive deferred metadata、`judge/distill/review/propose` scoped dry-run preview、`judge` 直接 scoped refresh-marker apply baseline、`judge` semantic proposal-preview artifact baseline、`judge` accepted proposal apply baseline、`review` 直接 scoped apply baseline、`distill` 直接 scoped candidate-refresh apply baseline 与 `propose` scoped proposal-plane apply baseline，以及 L3 prompt/policy proposal 的手工/fixture 创建、execute-mode 自动生成 baseline、Shell review surface、人工 reject、hash-gated apply 和 receipt-gated revert baseline；通用 audit stream 当前已有 read-only preview、显式 append-only backfill baseline，并已接入 execution receipt、runtime history、LLM receipt 与 protocol-learning aging writer direct append，backfill 对 direct append 已写入的同一 source event 幂等跳过。

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

在当前本机 full furnace 模型下，agent 可通过 nightly 静默执行 L0-L3 维护与进化（详见 §8）；操作者通过 receipt / audit / revert 行使事后审计权，是审计者而非每步确认者。agent 可自主改变炉子自身的 prompt/policy/schema，但所有行动均可追溯、可回滚；watcher 仍只负责 deterministic 投料入口，不承担 LLM 深度炼化。

## 1.1 User-Facing Surface（第一性原理）

炼丹炉对用户暴露的表面遵循一条强约束的第一性原理：

> **一个输入端 + 一个输出端，其余全部隐藏。**

这不是 UI 风格偏好，而是产品边界契约。它直接决定哪些机制可以出现在默认用户路径上、哪些必须降级为 internal mechanics。

### 用户面只暴露两件事

- **唯一输入端**：`drop`。用户把任意 raw 资产（URL / PDF / image / repo / text / question）丢进炼丹炉，runtime 自动识别类型并路由到对应协议。用户不需要选 protocol、不需要选 phase、不需要选 backend、不需要选 lane（heavy / light）。
- **唯一输出端**：`today`。用户每天打开炼丹炉，只看到今天该看什么——新报告、待 review 的判断、已完成的金丹、需要拍板的 L3 proposal。其余所有运维状态（System Status / LLM Health / Graph Health / Execution Center / Repair Backlog / Recent Runs）都不在首屏，必须主动展开 Advanced 抽屉才能看到。

### 一切其他细节都是 internal mechanics

下列概念**对用户全部隐藏**，只对 operator / debugger / agent loop 可见：

- 5 个 protocol（general / investing / research / product / ops）的内部路由
- 4 个 API backend（deepseek-api / opencode-api / openai-api / anthropic-api）的选择与切换
- 8+ phase（compile / lint / nightly / review / distill / propose / judge / aging / repair / escalation）的调度
- candidate plane / settled plane / receipt / audit stream / planner-log / signal stream / rollback marker
- L1 / L2 / L3 自主权边界（用户只感知"是否需要我拍板"，不感知层级编号）
- heavy lane / light lane / auto scheduler / primitive opt-in
- elixir 状态机（draft / distilling / settled / superseded）

它们都是**让上述两个用户面工作得更好**的 runtime 实现细节，不应该出现在用户的心智模型里。

### 设计判断标准

任何新增机制、CLI 命令、Product Shell UI 组件、文档章节，都必须先回答：

1. **它会不会增加用户必须知道的概念？** 如果会，必须先证明这个概念无法被隐藏到 internal mechanics 中。
2. **它属于"输入端"还是"输出端"？** 不属于这两端的，默认归 Advanced。
3. **它能不能用 sensible default 替用户做掉？** 能的话不暴露选项；不能的话先问"能不能让它能"。
4. **删掉它，用户的输入/输出体验会不会变差？** 不会的话，应该删掉而不是隐藏。

### 与 §3 不变量的关系

本节是 §3 不变量的**用户面投影**：deterministic baseline + provenance + receipt + revert + audit 是给 operator 和 agent loop 的契约；"一个输入端 + 一个输出端"是给用户的契约。两者都不能破坏，但服务对象不同。

### 实现层投影

- **Product Shell UI 层**的 Active SoT 是 [docs/Furnace Product Shell.md](./Furnace%20Product%20Shell.md)。它是这一原则在 Obsidian 插件上的具体形态：Today Feed（输出）+ Universal Input（唯一默认输入）+ gated Advanced（operator 诊断/历史/Review/Execution）。
- **CLI 层**的目标形态是 `furnace drop <anything>` + `furnace today` 两个核心命令，其余 ~48 个子命令降级为 `furnace advanced <subcommand>`。CLI 收敛工程是后续 milestone，不在本文档定义。
- **runtime 内部接口**（agent loop / planner / phase primitives / receipt / audit）不受本节约束，它们服务的是 operator 和 agent，不是普通用户。

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

## 2.0 AgentOS 9.0 Scorecard

9.0 达标口径与 release gate 见 [AGOS-9-Scorecard.md](./AGOS-9-Scorecard.md)；里程碑执行史料见 [AGOS-9-Execution-Plan.md](./archive/AGOS-9-Execution-Plan.md)。评分必须区分 `historical` / `fixture` / `replay` / `live` 四类证据，不得把历史 dogfood PASS 当作当前 clean vault 的 live PASS。

## 2.1 Current Implementation Map

| 能力 | 当前状态 | 说明 |
|---|---|---|
| 文件平面与 deterministic baseline | implemented | `raw / wiki / .aiwiki/state / schema / output` 已是 runtime 主结构，核心 `compile / lint / nightly` 与 scoped apply/revert 写回语义不依赖 LLM。 |
| 显式 backend 选择 | implemented | `AIWIKI_LLM_BACKEND` 必须显式设置；planner 不做 backend auto-routing。 |
| Product Shell surface | implemented | 插件通过 launcher CLI 与 `output/control/shell-summary.json` 工作，不直接拥有 runtime state。 |
| L2 protocol-learning | implemented | 已有 `active / stale / demoted / archived / superseded` 生命周期与 replacement DAG 校验；`protocol-learn-revert-activate` 可显式回滚带 metadata 的最近一次 `stale -> active` verify activation，并通过 runtime-history 进入 universal audit。 |
| active corpus / output candidates | implemented | `.aiwiki/state/active-corpora.json` 与 `.aiwiki/state/output-candidates.json` 已作为运行态工作集与候选状态。 |
| 金丹最小链路 | implemented | 当前 CLI 为 `alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote`，已落 `output/_candidates/elixirs/` 候选平面、`wiki/elixirs/` 持久平面、provenance、DAG 校验、Stage-3 compounding acceptance、promote/revert/demote receipt 与 maturity gate `elixir_quality_proof`；promotion revert 已按 receipt/hash gate 回到 candidate 并写 universal audit；legacy migration 已有 read-only preview 与显式 apply baseline，superseded cleanup 已有 read-only preview 与显式 deletion apply baseline。剩余 planned 范围仅指显式 LLM/human contract 下的 semantic distillation 与更高自治金丹演化，不影响最小主链路完成状态。 |
| planner | partial | 当前已有 `.aiwiki/state/planner-state.json` 的 repair/execution proposal planner，以及 `.aiwiki/state/planner-log.jsonl` 的 signal observe-only / execute-mode decision log；新 planner-log record 会写入由 decision 派生的 `phase`（`observe / light / heavy / proposal / human`），旧 v1 records 缺 `phase` 仍合法可 replay；`planner-log-replay --execute` 只追加 execute-mode decisions，不直接运行 lane/apply/proposal；`planner-log-rollback --dry-run/--apply` 可预览或显式追加独立 rollback marker stream，但不删除或重写 planner-log；execute-mode deterministic scheduler consumption 已通过 `alchemy auto` 和 `l3-proposal-generate` 落地，高风险 LLM-backed phase orchestration 仍需独立 primitive contract。 |
| heavy/light alchemy lane | partial | 已有 `aiwiki alchemy heavy|light <scope> --dry-run` 只读 preview，`--apply --action-id ...` 到既有 receipted low-risk action batch 的显式桥接，`--apply --primitive compile|lint|nightly` 的 deterministic receipt wrapper，显式 heavy `--apply --primitive review` 到 direct scoped review apply 的桥接，显式 heavy `--apply --primitive distill` 到 direct scoped distill apply 的桥接，显式 heavy `--apply --primitive propose` 到 scoped proposal-plane apply 的桥接，以及 `aiwiki alchemy auto --dry-run|--apply` 对 execute-mode deterministic planner decisions 的显式调度入口；`alchemy auto --lane heavy --primitive review\|distill\|propose` 可显式 opt-in 调度 review/distill/propose，但默认 auto 不选择三者。lane apply 会写 `alchemy-lane-started / alchemy-lane-completed` runtime-history audit events，scheduler apply 会写 `alchemy-auto-scheduler` runtime-history audit event，lane primitive receipt 已显式携带 planner trace 与 execution receipt history audit metadata；`judge` 当前支持 direct `aiwiki alchemy judge <scope> --apply` 对已有 judgment/decision refs 写 deterministic managed refresh marker，也支持 `aiwiki alchemy judge <scope> --propose` 为已有 refs 生成 semantic refresh proposal-preview artifacts，以及 `aiwiki alchemy judge-proposal <proposal> --apply` 对 `state=accepted` 且 target `before_hash` 匹配的 proposal 写入 target managed section；这些路径都不由 runtime 生成判断结论、不改 status/confidence/review lifecycle、不创建 scope-only judgment/decision、不调用 LLM，也不进入 lane/auto；`review` 可显式写 review queue managed section 与 receipt/audit，但不进入 light lane；`distill` 可显式刷新 scoped preview 中已有 elixir candidate refs，并写 receipt/audit/runtime history，不创建新 elixir、不 promote/finalize、不进入 light/default auto；`propose` 可显式写 L3 proposal plane 并写 receipt/audit/runtime history，但不进入 light lane，且不写目标 prompt/policy 文件。 |
| L3 prompt/policy proposal | implemented | 已有 manual baseline：`l3-proposal-create` 写入 `output/_proposals/prompt|policy`，`l3-proposal-generate --dry-run|--apply` 可从 execute-mode `generate-proposal` planner decisions 创建 prompt proposal 候选，`alchemy propose <scope> --apply` 可从 scoped dirty preview 直接生成 prompt proposal 候选并写 proposal-generation receipt/audit，`review proposals`、`review proposal-generation` 和 `shell-status` 的 `review_controls.l3_proposals` 只读列队，`review proposal <id> --status accepted|rejected` 显式人工 accept/reject，`apply <proposal-id>` 仅在 `human_accepted` 或 `metadata_only` 时通过 `before_hash` 写回/登记并生成 receipt，`revert <receipt-id>` 通过 `after_hash` clean revert 并写 runtime-history / universal audit，冲突时生成 `human_merge_required` hint；agentic nightly 默认自动登记 `metadata_only`，不会无人值守改核心 prompt/policy/schema。 |
| universal audit stream | implemented | 当前已有 `aiwiki audit-preview --dry-run` 只读归一化 execution receipts、LLM receipts、runtime history 与 protocol-learning aging audit，并可通过 `aiwiki audit-backfill --apply` 显式 append 缺失 records 到 `.aiwiki/state/audit.jsonl`；execution receipt、runtime history、LLM receipt 与 protocol-learning aging writer 已直接 append universal audit record，且 backfill 对 direct append 已写 records 幂等跳过。 |

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
- **Backend 与 model 显式手动选择**：`deepseek-api / opencode-api / openai-api / anthropic-api` 之间的切换由操作者控制，planner 不做 backend auto-routing。Model 选择同样由操作者显式控制：runtime 不在 backend 内部做隐式 model fallback chain；要换 model 必须通过显式 `--model` / `AIWIKI_LLM_MODEL` 或显式 `--model-fallback model_a,model_b` 指定。任何 backend 内部的"留空时按链尝试"策略都被视为 hidden routing，不允许默认开启。
- **Review / apply / revert / audit 闭环不破坏**：任何写回 `wiki/` 或 `prompts/` 或 `schema/policies/` 的动作都必须产生可回滚的 receipt 和 audit。
- **Runtime 不生成语义判断/学习/提示内容**：`judge / distill / review / propose` 等 phase 的 runtime 实现只负责 deterministic 调度、scoped preview、proposal-preview artifact、managed marker、accepted block 落盘等结构性写入；语义内容（判断结论、distill summary、review verdict、prompt body）必须由 human 或显式被调用的 external model 在 proposal/accepted block 中提供。runtime 不在这些 phase 内部隐式调用 LLM 生成结论。要让 LLM 介入语义生成，必须走显式 `run-*` 或 propose-preview → human/external accept 链路，且每一步都留 receipt 和 audit。

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
- `generate-proposal`（生成 L2/L3 proposal；L3 当前支持 execute-mode deterministic proposal candidate generation，但写回仍必须人工 accept）
- `escalate-human`（需要人工介入）

planner **只能调度已被允许的 phase 集合**，不允许发明新的写回路径。planner 的决策全程可审计。

当前 planner-log v1 的 `phase` 是 additive compatibility field：新记录必须能由 `decision` 复算到闭集 `observe / light / heavy / proposal / human`，旧记录缺 `phase` 仍可作为历史 v1 log replay。`phase` 只表达调度标签，不直接授权 side effect；side effect 仍由 execute-mode、primitive allowlist、receipt/audit/revert 契约共同约束。

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

当前 lane apply 白名单只包含已具备 receipt wrapper 的 `compile / lint / nightly / review / distill / propose`，且 runner 必须看到对应 dry-run step 明确 `apply_supported=true` 才能执行。`judge / distill / review / propose` 属于目标 phase，目前都有独立 scoped dry-run preview，用于盘点 dirty scope 内的 judgment refresh candidates、elixir refresh candidates、review enqueue candidates 与 proposal opportunities；preview 会暴露 `apply_contract` metadata（write surfaces、receipt schema、audit schema、revert policy、idempotency key、backend policy）。其中 `judge` 已支持直接 `aiwiki alchemy judge <scope> --apply`，只对已有 `judgment_refs` 对应的 judgment/decision pages 写 deterministic managed refresh marker，并写 execution receipt / runtime history / universal audit；也支持 `aiwiki alchemy judge <scope> --propose`，只为已有 judgment/decision refs 写 `output/_proposals/judge/` proposal-preview artifact 与 receipt/runtime-history/universal-audit，artifact 记录 target path、before hash、candidate/signal/trace provenance、`llm_invoked=false`、`semantic_content_generated=false` 和 human/model acceptance requirement；`aiwiki alchemy judge-proposal <proposal> --apply` 仅接受 `state=accepted`、target `before_hash` 匹配且包含 explicit accepted refresh block 的 proposal，把该 accepted block 写入 target managed section，并写 receipt/runtime-history/universal-audit。scope-only preview candidates 仍不可 apply/propose，不创建判断页、不改 status/confidence/review lifecycle、不调用 LLM，也不进入 lane/auto。`review` 已支持直接 `aiwiki alchemy review <scope> --apply`、显式 heavy lane `--apply --primitive review`，以及 `alchemy auto --lane heavy --primitive review` opt-in 调度；这些路径只写 `wiki/indexes/review-queue.md` 的 managed section 与 receipt/audit/runtime history，不调用 LLM，也不进入 light lane，且默认 auto 仍只选择 deterministic primitives。`distill` 已支持直接 `aiwiki alchemy distill <scope> --apply`、显式 heavy lane `--apply --primitive distill`，以及 `alchemy auto --lane heavy --primitive distill` opt-in 调度，只刷新 scoped preview 中已有 `elixir_refs` 对应的 candidate plane 文件，使用 deterministic refresh question 做幂等识别并写 execution receipt / runtime history / universal audit；scope-only preview candidates 仍不可 apply，不创建新金丹、不 finalize/promote、不写 `wiki/elixirs/`，不进入 light lane，且默认 auto 仍不选择 distill。`propose` 已支持直接 `aiwiki alchemy propose <scope> --apply`、显式 heavy lane `--apply --primitive propose`，以及 `alchemy auto --lane heavy --primitive propose` opt-in 调度，只生成 L3 prompt proposal 候选并写 execution receipt / runtime history / universal audit，不写 `prompts/*` 或 `schema/policies/*` 目标文件，不消费 `generate-proposal` decisions，不进入 light lane，且默认 auto 仍不选择 propose；目标写回仍必须通过人工 review + 既有 L3 proposal apply/revert。`judge` 如需 runtime 生成语义级判断内容、lane judge 或 auto judge，仍必须另走显式 LLM/人工 contract。

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
- **L3 prompt/policy proposal**（`output/_proposals/prompt/`、`output/_proposals/policy/`，当前为 manual baseline + execute-mode automatic candidate generation baseline）

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
  - 候选平面：`output/_candidates/elixirs/`（未通过人工 promote；当前 draft / distilling / candidate / tombstone 主路径）
  - 当前持久平面：`wiki/elixirs/`（当前最小链路由 `alchemy-promote` 产生 `settled`）
- **Provenance 强制**：目标 schema 要求每个金丹携带 `derived_from`、`judgment_refs`、`counter_evidence`、`confidence_level` 和 `corpus_id`；当前最小实现已强制 `derived_from` 与 corpus provenance，并校验必须包含底层 `wiki/derived/` 源条目。

存储决策（本轮最终结论）：

- **存在 `wiki/elixirs/`，而非作为 judgment 的附加状态，也不在 `active_corpus` 原地升格。**
- 理由：金丹是长期资产，`active_corpus` 是运行态工作集；两者的生命周期和物理位置必须严格分离。

完整 schema / 生命周期 / 三阶段路线图（Chaining → Distillation → Compounding）见 [[docs/Furnace Evolution Mechanics|炼丹炉进化机制]] §7 / §8。

## 8. Autonomy Boundaries: L0 / L1 / L2 / L3 / Judgment

炼丹炉的自主权现在是**agentic 分层可开关模型**：缺省 runtime policy 为 `autonomy_profile=agentic`，系统核心不自改；维护、治理、judgment review、metadata-only L3 和 heavy semantic 非核心自动化默认开启。每层可通过 `.aiwiki/state/autonomy-policy.json` 或独立环境变量缩窄，所有自动采纳均写 receipt 支持 revert/audit。操作者可按层把对应 policy/env flag 改为 `false` / `0`，退回 dry-run preview 或更窄自动化半径。

L0（维护层）由 `AIWIKI_NIGHTLY_AUTO_APPLY_LIGHT=1` 控制；L1-L3/Judgment 分别由 `AIWIKI_NIGHTLY_AUTO_ADOPT_L1/L2/L3/JUDGMENTS=1` 控制。

红线表：

| 层级 | env flag | 自动做的事 | 写 receipt | 可 revert |
|---|---|---|---|---|
| **L0 维护层** | `AUTO_APPLY_LIGHT` | compile / lint / nightly 清洁；陈旧状态清理；派生索引 refresh | 是 | 是 |
| **L1 语义层** | `AUTO_ADOPT_L1` | concept backlog → active；revisit → deferred；source-concept link accepted + apply；所有 accepted low-risk actions apply | 是 | 是 |
| **L2 结构层** | `AUTO_ADOPT_L2` | overloaded-concept split accepted + apply | 是 | 是 |
| **L3 策略层** | `AUTO_ADOPT_L3` | 默认开启非核心/metadata-only 学习；核心 prompt/policy/schema 写回不无人值守发生，必须 human accept + hash-gated apply | 是 | 是 |
| **Judgment 判断层** | `AUTO_ADOPT_JUDGMENTS` | LLM-powered counter-evidence 复核：读取新的反证来源页，调用 LLM 生成 upheld/weakened/refuted 结论，写入 judgment 页 review history | 是 | 是（人工可覆盖） |

永不自动做的底线（所有层级均遵守）：

- 覆盖 `raw/`
- 修改 `src/aiwiki/**`
- 绕过 receipt / audit
- 隐式切换 LLM backend
- 静默吞错

当前本机 full furnace / dogfood nightly profile（2026-06）默认开启每晚自动维护、治理、判断复核、metadata-only L3 学习与 heavy semantic 非核心 apply；watcher 仍保持 deterministic-only，fallback 和 L3 核心写回仍需显式启用，所有学习必须 receipt-gated、可审计、可回滚。

## 9. Protocols, Operator Control, and Backend Selection

**"一个炉子，多个 protocol"** 的原则本轮继续生效：

- Protocol 当前集合：`general / investing / research / product / ops`。
- Protocol 作用在：
  - planner 的 bias（热区偏好、review 频次、light 节奏）
  - review cadence（不同 protocol 的老化速度不同）
  - elixir compounding（同 protocol 内的金丹复利优先）
  - output 模板与 judgment 字段
- Protocol **不是硬隔离**，但当前 runtime 只做 deterministic cross-protocol match：跨协议证据是否被纳入工作集，由 graph / judgment / drift 信号在 deterministic 规则下决定，runtime 不做语义召回（不基于 LLM 相似度判断"另一个协议的 evidence 是否相关"）。任何跨协议召回必须留可追溯的 deterministic 触发依据（signal id、graph edge、ref 关系），并随 receipt/audit 一起记录。基于语义/向量的跨协议证据召回不在默认可用边界内。

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

## 11.1 State Loader 语义边界（best-effort vs strict）

炼丹炉所有持久化状态（`.aiwiki/state/*.json` / `*.jsonl`）有两种合法读取语义，对应两种调用契约。M9-P0.4 起在 `aiwiki.app_state` 同时暴露两套 API，调用方必须根据"静默 fallback 是否等同于事实层数据丢失"显式选择。

**Best-effort：`load_json_document` / `load_jsonl_documents`**

- 文件不存在 → 返回 `{}` / `[]`
- 文件存在但 JSON 解析失败 → `logging.warning` + 返回 `{}` / `[]`（JSONL 单行 skip 后继续）
- 非 dict 顶层 / 非 dict JSONL 记录 → `logging.warning` + 跳过
- 适用：preview、telemetry、drift hint、shell summary 等 caller，对"看不到 = 没有"和"看不到 = 损坏"无需区分
- 反例：authoritative read（receipts、audit、runtime history）不应使用 best-effort，否则一次磁盘损坏可能让 promote / revert / nightly 误判 system state

**Strict：`load_json_document_strict` / `load_jsonl_documents_strict`**

- 文件不存在 → 返回 `{}` / `[]`（"未发生" 不视为 corrupt）
- 文件存在但 JSON 解析失败 → 抛 `CorruptStateError(path, reason, line_number)`
- 非 dict 顶层 / 非 dict JSONL 记录 → 抛 `CorruptStateError`
- 适用：authoritative read 路径，要求"corrupt 必须冒泡"。caller 应捕获 `CorruptStateError` 并选择：升级为 blocker / 触发 repair / fail closed
- `CorruptStateError.line_number` 在 JSONL 上精确到行，便于人工修复定位

**迁移策略**（升级路径）

当前 callers 大部分使用 best-effort 语义。逐点切换到 strict 的触发条件：

1. 该 caller 的"静默 fallback 等同于事实层数据丢失"被识别（典型：执行 receipt 链路、aging 决策、escalation 计算）
2. 同时补一条 acceptance case 覆盖 corrupt-state 行为
3. 在 PROGRESS.md 标注切换原因并保留 best-effort fallback 的退出条件（若有）

已切换到 strict 的 authoritative reader（M9-P0.4）：

- `aiwiki.app_execution.find_latest_elixir_promotion_receipt`：revert hash-gate 依赖此函数选择最近一次 promotion receipt；corrupt JSONL line 必须冒泡为 `CorruptStateError`，不允许静默 `continue`，否则可能选择陈旧 receipt 或误报 missing。

不在本文档列其它具体 caller 清单——以 `git grep load_json_document` / `load_jsonl_documents` 当前代码为准。

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
