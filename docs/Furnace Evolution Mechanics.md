---
title: "炼丹炉进化机制"
kind: "contract"
status: "active"
owner: "tim"
supersedes:
  - docs/Furnace Material Scaling.md
  - docs/Furnace Material State Model.md
  - docs/Furnace Incremental Compile Plan.md
related_docs:
  - docs/Furnace Agent Architecture.md
  - docs/Furnace Elixir.md
---

# 炼丹炉进化机制

这份文档定义炼丹炉“如何进化”的实现契约：signal 如何路由到 heavy / light 炼丹、active corpus 如何持久化、金丹如何炼成与复利、L2 protocol-learning 如何衔接既有实装、L3 prompt/policy proposal 如何受控写回。

> **实现状态说明（2026-04-24）**：本文是“目标契约 + 当前差距”的 SoT。当前已落地 active corpus / output candidates、L2 protocol-learning 生命周期、repair planner state、nightly low-risk auto-consume、显式 backend 选择、最小金丹 `alchemy-start / alchemy-distill / alchemy-seal`。完整 signal stream、append-only `planner-log.jsonl`、heavy/light 调度入口、`output/_candidates/elixirs/` 候选平面、L3 prompt/policy proposal 的 review/apply/revert 链路尚未完整实现，以下章节用 `implemented / partial / planned` 标记区分。

它同时取代：

- `Furnace Material Scaling.md`（规模化设计）
- `Furnace Material State Model.md`（状态模型）
- `Furnace Incremental Compile Plan.md`（增量编译计划）

与终局架构 [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]] 配对使用：架构文档定义**世界观**，本文档定义**契约**。

## 1. Scope and Contract Boundary

本文档**只**定义：

- signal 的标准化结构与 taxonomy（target contract）
- planner 的路由规则与锁策略（target contract；当前仅有 repair planner state）
- heavy / light alchemy 的执行契约（target contract；当前由 existing primitives 局部承担）
- `active_corpus` 的持久化 schema 与生命周期（implemented）
- `wiki/elixirs/` 的 frontmatter 与 DAG 约束（partial）
- Chaining / Distillation / Compounding 三阶段 CLI 语义（当前 CLI + 目标 CLI delta）
- L2 protocol-learning 与现有 EP-029 Step 4 的衔接
- L3 prompt/policy proposal 的触发、产物、审批、写回、revert 契约（planned）

本文档**不**定义：

- Product Shell UI / surface 细节
- EP 具体实施时间表（见 `PROGRESS.md` 与 `.codex/plans/active.md`）
- 终局架构愿景（见 [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]]）

## 2. Signal Taxonomy

目标契约：所有进入完整 planner 的信号必须标准化为：

```json
{
  "schema_version": 1,
  "signal_id": "sig-20260424-abc123",
  "dedupe_key": "raw_added:research:raw/inbox/example.md",
  "kind": "raw_added | counter_evidence | drift | review_feedback | runtime_failure | schedule_tick | learning_threshold | elixir_dependency_break",
  "scope": {
    "protocol": "research",
    "corpus_id": "research-transformer-scaling",
    "source_ids": ["src-1"],
    "concept_slugs": ["scaling-law"],
    "elixir_refs": [],
    "judgment_refs": ["judgment-foo"]
  },
  "severity": "low | medium | high | critical",
  "evidence_refs": ["raw/inbox/example.md#L12", "wiki/judgments/foo.md"],
  "budget_hint": {
    "max_pages": 20,
    "max_tokens": 4000
  },
  "emitted_at": "2026-04-24T12:00:00+08:00",
  "emitted_by": "nightly | user | compile | external",
  "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L42",
  "trace_id": "trace-20260424-abc123"
}
```

Signal kinds（本轮最小集）：

| kind | 触发时机 | 默认 severity |
|---|---|---|
| `raw_added` | drop-url / drop-pdf / drop-image / drop-repo / 手工添加 | medium |
| `counter_evidence` | 新证据与既有 judgment 冲突 | high |
| `drift` | nightly 发现 judgment 证据基础已变 | high |
| `review_feedback` | 用户 accept / reject / rewrite | low-high（随裁决） |
| `runtime_failure` | contract validation / lint 持续失败 | medium |
| `schedule_tick` | nightly / weekly / periodic light tick | low |
| `learning_threshold` | protocol-learning 候选累积到阈值 | medium |
| `elixir_dependency_break` | 被引用 elixir 被 demote / superseded | high |

Signal **从不直接触发 phase**，必须经过 planner 决策。

当前状态：runtime 已有 `runtime-history.jsonl`、LLM receipts、review / execution receipts、planner-state 等可观测输入，但尚未统一归一化为 append-only signal stream。

落地约束：

- `schema_version` 必须随不兼容变更递增。
- `dedupe_key` 是同一事件重复写入时的幂等边界；planner 必须按它去重。
- `source_event_ref` 保留到原始 receipt / history 的回链，signal 自身不替代原始审计。
- `trace_id` 贯穿 signal、planner-log、receipt，便于重放和调试。

## 3. Planner Routing Rules and Locking

当前状态：已落地 `.aiwiki/state/planner-state.json`，用于 repair / execution proposals 的 priority queue、dependency graph、next action 和 nightly auto-consume 记录。下述 `signal -> planner -> heavy/light` 是下一阶段完整 planner 契约，不等同于当前 `planner-state.json` 的全部能力。

### 3.1 Routing 决策

planner 接收 signal，产出以下之一的决策：

- `ignore`：严重度不足、budget 耗尽、signal 已被覆盖
- `enqueue-light`：收入下一轮 light 队列
- `enqueue-heavy`：立即触发 heavy 炼丹（或加入 heavy 队列）
- `generate-proposal`：触发 L2 learning 或 L3 prompt/policy proposal
- `escalate-human`：系统无法决策，显式交人工

### 3.2 Heavy vs Light 判别依据

按**三维度**判别，不按 cron 或事件名硬编码：

| 维度 | Heavy | Light |
|---|---|---|
| **是否改变知识意义** | 是（judgment 可能反转、新事实进入金丹依赖链） | 否（仅卫生、索引、老化） |
| **作用范围** | 可能跨多个 source / concept / corpus | 局部、分页、有预算 |
| **风险** | 可能触发 review / revert / escalation | 零风险、可重跑 |

只要**任一**维度判定为 heavy，走 heavy lane；否则走 light。

### 3.3 锁与优先级

- 全局 single writer 锁由 planner 协调。
- heavy 持有锁优先级最高，light 遇到 heavy 锁 **立即 skip**（不进入长等待）。
- light 遇到 light 锁时，后来者 skip。
- heavy 进行中接收到新 high severity signal 时，不抢占当前 heavy；将新 signal 入 heavy 队列，按 scope 去重合并。

### 3.4 Planner 状态

目标 planner 的决策日志写入：

- `.aiwiki/state/planner-log.jsonl`（append-only）

每条决策包含：`schema_version / signal_id / dedupe_key / decision / mode / reason_codes / budget_used / locks_acquired / primitive_refs / side_effects_allowed / decided_at`。

当前已落地的 planner 状态文件是 `.aiwiki/state/planner-state.json`，它不是 append-only decision log。

首版 planner-log 必须以 `mode=observe_only` 落地，且 `side_effects_allowed=false`；只有 signal replay、去重和 scope 计算连续通过 gate 后，才能开放 `dry_run`，最后才允许 `execute`。

## 4. Heavy Alchemy Contract

### 4.1 定位

heavy 是**事件驱动的深度重炼**，面向“知识意义可能被改变”的场景。

### 4.2 触发源

- `counter_evidence`（severity=high 及以上）
- `drift`（命中 active judgment 或 active corpus）
- `elixir_dependency_break`
- `learning_threshold` 达到结构调整条件
- 用户显式触发（目标入口：`aiwiki alchemy heavy <scope>`；当前尚未落地）

### 4.3 动作序列

heavy 的默认执行序列：

```
1. route       : 计算 dirty scope（source + concept + judgment + elixir 依赖图）
2. compile     : 按 dirty scope 做 targeted 增量 compile（不做全库热编译）
3. judge       : 刷新 dirty scope 内的 judgment / decision
4. distill     : （可选）触发候选金丹更新
5. lint        : drift / contract 校验
6. review      : 有 high severity 产物时入 review queue
```

### 4.4 作用范围约束

- heavy 默认**不**做全库重刷；只在 dirty scope 上执行。
- 只有 **graph / contract 级损坏**（比如 schema 核心不一致、全局 DAG 破裂）才允许升级为全量 heavy，且需要 `escalate-human` 显式授权。

### 4.5 与现有 CLI 的关系

heavy 是目标**调度层**，底层仍复用现有 primitives：

- `compile` / `lint` / `nightly` / `review` 与现有 scoped apply/revert primitives 保持可单独运行。
- heavy 落地后只是按 planner 决策**组合**这些 primitives，并共享锁与 audit。
- 既有命令的语义**不变**。

## 5. Light Alchemy Contract

### 5.1 定位

light 是**定时、限额、低扰动**的维护周期，只做知识卫生。

### 5.2 Cadence 建议

| 周期 | 内容 |
|---|---|
| `nightly`（每日）| drift 检测、候选区老化、aging、索引刷新、热度再评估 |
| `weekly`（每周）| 加深清理、cold / archive 建议、stale generated page 清理 |
| 可选 `6-12h micro-light` | 仅做 manifest refresh、index lightweight refresh |

### 5.3 预算约束（硬约束）

单轮 light 必须**显式**限制：

- `max_sources_processed`（建议 ≤ 200）
- `max_tokens_consumed`（若触发 LLM，建议 ≤ 10k）
- `max_wall_time`（建议 ≤ 10min）

超出预算即停止并记录 `budget_exceeded` 到目标 planner-log，剩余工作进入下一轮。

### 5.4 与 heavy 的互斥规则

- light 拿不到锁即 **skip**，不排长等待。
- light 发现自身 scope 与进行中 heavy scope 重叠，直接 skip。
- light **绝不允许**静默升级为 heavy；若 light 过程中识别出 heavy 信号，必须回到 planner 决策。

### 5.5 可执行原子

light 允许调度的 phase 子集：

- `compile`（仅 metadata refresh + index refresh + cold maintenance）
- `lint`（read-only drift / aging）
- `route`（active corpus 降温、expire）

light **不允许**触发 `judge`、`distill`、`propose`、`apply`。

## 6. Active Corpus Contract

### 6.1 定位

`active_corpus` 是**可持久化的 runtime working set**，不是新的事实源。它回答“当前这一轮炼化 / 提问 / 复审围绕哪一批材料”。

### 6.2 存储

| 文件 | 角色 |
|---|---|
| `.aiwiki/state/active-corpora.json` | canonical state（当前所有 active / cooling / expired corpus） |
| `.aiwiki/state/runtime-history.jsonl` | 统一运行历史（query / review / nightly），active corpus 收敛依赖 |
| `wiki/indexes/log.md` | 人读镜像，**不**作为 canonical rebuild input |

### 6.3 Schema

```json
{
  "corpus_id": "research-transformer-scaling",
  "protocol": "research",
  "topic": "Compare scaling laws and inference-time compute",
  "focus_kind": "question | review | nightly | judgment | alchemy",
  "focus_ref": "...",
  "question_hash": "sha256:...",
  "source_ids": ["src-1", "src-2"],
  "concept_slugs": ["transformer", "scaling-law"],
  "judgment_refs": ["judgment-foo"],
  "elixir_refs": ["elixir-bar"],
  "bridge_evidence_ids": ["src-bridge-1"],
  "output_refs": ["output/reports/query-123.md"],
  "budget": {
    "max_context_tokens": 8000,
    "max_turns": 20
  },
  "status": "active | cooling | expired",
  "created_at": "2026-04-24T12:00:00+08:00",
  "last_used_at": "2026-04-24T12:15:00+08:00",
  "expires_at": "2026-04-27T12:00:00+08:00"
}
```

### 6.4 状态机

| 状态 | 触发 |
|---|---|
| `active` | 当前 `ask --corpus` 命中 / 显式引用；目标 `alchemy-start` 或 future `alchemy start` wrapper 创建 |
| `cooling` | nightly 把长期未用的 active 降温 |
| `expired` | 超过 `expires_at` 且无命中 |
| `active` ← `expired` | 被重新命中时允许回升 |

### 6.5 物理隔离原则

- `active_corpus` **只存在于** `.aiwiki/state/`，不写入 `wiki/`。
- `active_corpus` **不能** 原地升格为金丹；金丹必须经过显式 `distill → promote` 生命周期。
- `active_corpus` 可以被多个 `ask` turn 共享；每次 turn 追加 `output_refs` 并刷新 `last_used_at`。

## 7. Elixir Storage and Lifecycle

### 7.1 存储路径

| 阶段 | 路径 |
|---|---|
| 候选（目标，未 promote） | `output/_candidates/elixirs/<elixir-id>.md` |
| 持久（当前与目标） | `wiki/elixirs/<elixir-id>.md` |

目标契约要求候选平面与持久平面**物理隔离**，避免一个字段同时表达两种语义。当前最小实现暂时由 `alchemy-start` 直接写入 `wiki/elixirs/` 的 `draft` 金丹，再由 `alchemy-distill` 推进 `distilling`，最后由 `alchemy-seal` 标记 `settled`。

迁移策略：

- 旧 `wiki/elixirs/` 文件继续按当前 schema 读取，不做强制搬迁。
- 新候选入口落地后，默认只对新金丹写入 `output/_candidates/elixirs/`。
- `alchemy-seal` 继续兼容旧 draft / distilling 文件；新 promote gate 稳定后，再把默认入口切到 candidate flow。
- 任一候选 promote 失败必须保持 source candidate 不变，并写明失败原因；不得半写入 `wiki/elixirs/`。

### 7.2 Frontmatter（最小集）

目标 frontmatter 最小集：

```yaml
---
kind: elixir
elixir_id: elixir-research-scaling-2026q2
protocol: research
elixir_state: draft | distilling | candidate | settled | superseded
corpus_id: research-transformer-scaling
derived_from:
  - wiki/judgments/scaling-law-baseline.md
  - wiki/decisions/inference-compute-tradeoff.md
  - output/reports/query-123.md
judgment_refs:
  - judgment-scaling-law-baseline
decision_refs:
  - decision-inference-compute-tradeoff
elixir_refs:  # 引用的其他金丹（形成复利）
  - elixir-foundation-arch-2025q4
counter_evidence:
  - wiki/sources/skeptic-paper-2024.md
confidence_level: medium | high
review_after: 2026-07-24
supersedes: []
superseded_by: null
created_at: 2026-04-24
promoted_at: null
---
```

当前最小实现已落地字段：`elixir_id`、`elixir_state`、`iteration`、`provenance_corpus`、`derived_from`、`topic`、`created_at`、`updated_at`、`distill_history_json`，`settled` 时补 `sealed_at`。`judgment_refs / decision_refs / counter_evidence / confidence_level / promoted_at` 仍属于目标 schema。

### 7.3 生命周期

| 状态 | 位置 | 入口 |
|---|---|---|
| `draft` | 当前 `wiki/elixirs/`；目标 `output/_candidates/elixirs/` | 当前 `alchemy-start <corpus_id> --topic ...` |
| `distilling` | 当前 `wiki/elixirs/`；目标 `output/_candidates/elixirs/` | 当前 `alchemy-distill <elixir_id> --question ...` |
| `candidate` | 目标 `output/_candidates/elixirs/` | planned：准备提交人工评审 |
| `settled` | `wiki/elixirs/` | 当前 `alchemy-seal <elixir_id>`；目标 `promote` 后 |
| `superseded` | `wiki/elixirs/`（保留） | planned：被新金丹显式 supersede |

### 7.4 DAG 约束

- 金丹引用链（`elixir_refs`）**必须**构成有向无环图。
- 新金丹**不得**只依赖旧金丹的结论自举——必须同时锚定至少一条 `raw/` 或 `wiki/sources/` / `wiki/judgments/` 的底层证据。
- 当前 `alchemy-distill / alchemy-seal` 已校验金丹 DAG、自引用、路径穿越和底层 `wiki/derived/` 锚定；目标 promote gate 继续执行同类校验。

### 7.5 Counter-evidence 强制

- 目标 promote gate 中 `counter_evidence` 字段**不得为空**。
- 若真的没有反证，显式写 `counter_evidence: [NONE_FOUND]` 并记录 `confidence_level: low`。

当前最小金丹实现尚未强制 `counter_evidence / confidence_level`。

## 8. Chaining → Distillation → Compounding

金丹机制的三阶段路线图及其 CLI 契约。

### 8.1 阶段 1：Chaining（串主题）

```bash
aiwiki ask "VLA 的核心设计权衡是什么" --protocol research --corpus research-vla-2026q2
# → 当前：创建/命中 corpus，写入 active-corpora.json，status=active

aiwiki ask "和传统 HLA 相比有哪些优劣" --corpus research-vla-2026q2
# → 当前：每轮 output 写入 output/reports、output/slides、output/figures 等可见产物
# → 当前：.aiwiki/state/output-candidates.json 记录候选状态，output_refs 追加到 corpus
# → 绝不自动写入 wiki/

aiwiki drop-url https://example.com/vla-paper
aiwiki ask "结合新 paper 重新评估权衡" --corpus research-vla-2026q2
```

**验收准则**：第二轮 `ask` 能无缝读取前轮 output；`wiki/` 不被自动写入。

### 8.2 阶段 2：Distillation（凝丹）

```bash
aiwiki promote output/reports/query-20260424-example.md
# → 当前：把 output candidate promote 到 wiki/derived/，供金丹引用

aiwiki alchemy-start research-vla-2026q2 --topic "VLA 机器人架构"
# → 当前：从该 corpus 下已 promoted 的 wiki/derived/ 输出生成 wiki/elixirs/<elixir-id>.md，state=draft

aiwiki alchemy-distill <elixir-id> --question "延迟约束如何改变架构权衡？"
# → 当前：推进 iteration，保留 provenance，state=distilling

aiwiki alchemy-seal <elixir-id>
# → 当前：校验 DAG 与底层 wiki/derived/ 锚定后标记 state=settled
```

**当前验收准则**：能从已 promoted output 生成 elixir，能多轮 distill，能 seal，并拒绝空 provenance、自引用、路径穿越和 DAG 环路。

**目标验收准则**：能成功生成 candidate elixir 文件并走完 promote / demote / revert 生命周期；每一步可审计。

### 8.3 阶段 3：Compounding（复利）

```bash
aiwiki alchemy-start research-vla-2026q2 --topic "下一代 VLA 架构" --include-elixir elixir-vla-2026q1
aiwiki alchemy-distill <new-elixir-id> --question "如何吸收旧金丹结论？" --include-elixir elixir-foundation-arch-2025q4
# → 当前：显式引用 settled 金丹，写入 derived_from，并执行 DAG 校验
```

**验收准则**：

- 同 protocol 的 ask 能显式加载 `protocol-learnings`（L2）
- 新金丹能显式引用旧金丹（DAG 校验通过）
- 引用链不形成无限自循环

## 9. L2 Protocol-Learning Contract

L2 layer 已在 EP-029 Step 4 落地。本文档**继承**现有实现，不引入破坏性变更。

### 9.1 现有实装（EP-029 Step 4）

- 存储：`wiki/protocol-learnings/<protocol>/<learning-id>.md`
- 生命周期：`active / stale / demoted / archived / superseded`
- 校验：replacement graph（supersede DAG）
- 加载：`ask --load-learnings` 只加载 `active` 且显式 opt-in

### 9.2 本文档新增约束

- heavy/light alchemy **可以**作为新 learning 候选来源（来自 failure cluster / review 聚类），但必须走现有 `active → stale → superseded` 生命周期与 graph 校验。
- `active` 状态的装载**必须**显式（CLI flag 或 protocol 级 opt-in），**不**做隐式全局注入。
- L2 的职责是**经验沉淀**，**不**是偷偷改 prompt / policy——那是 L3 的范围。

### 9.3 触发 learning 候选生成

目标 signal→proposal 路径：

- `review_feedback` 聚类出 recurring pattern（同一 protocol、同类 reject 理由、≥ 3 次）
- `drift` 反复命中同一类 judgment
- `runtime_failure` 聚类出稳定失败模式

完整 planner 落地后可发出 `generate-proposal`（targeting `wiki/protocol-learnings/<protocol>/_candidates/`）。人工 accept 后转为 `active`。当前可通过 `protocol-learn-add` 显式新增 learning，再用 `protocol-learn-age / verify / demote / archive / supersede` 治理生命周期。

## 10. L3 Prompt/Policy Proposal Contract

**架构授权的 planned 能力**。agent 可生成对 `prompts/*.md` 和 `schema/policies/*` 的修改提案，但**必须人工 accept** 才写回。当前 runtime 尚未提供 `prompt_proposal / policy_proposal` 的生成、review、apply、revert 入口；现有成熟 proposal 类型是 execution proposal 与 concept rewrite proposal。

### 10.1 触发条件

目标 L3 proposal 只在以下条件之一成立时触发：

1. **Failure pattern 聚类**：同一 prompt / policy 下反复出现 ≥ N 次同类失败（建议 N=5），且归因指向 prompt / policy 本身。
2. **Recurring feedback**：同一 prompt 下用户反复 reject / rewrite（≥ 3 次），且 feedback 有共同语义。
3. **Drift 证据累积**：某 policy 条款的基础事实已变，且有 ≥ 2 条 drift 证据。
4. **长期 contract validation failure**：某 contract 连续 ≥ 7 天 / ≥ 10 次失败。

低于阈值的单次事件**不**触发 L3 proposal——避免冷启动噪音。

### 10.2 产物路径

| 类型 | 目录 |
|---|---|
| Prompt proposal | `output/_proposals/prompt/<proposal-id>.md` |
| Policy proposal | `output/_proposals/policy/<proposal-id>.md` |

### 10.3 Proposal Schema

```yaml
---
kind: prompt_proposal | policy_proposal
proposal_id: prop-20260424-001
target_file: prompts/investing-review.md  # 或 schema/policies/aging.json
trigger:
  signal_ids: ["sig-1", "sig-2", "sig-3"]
  pattern: failure_cluster | recurring_feedback | drift | contract_failure
  evidence_count: 5
evidence_refs:
  - output/receipts/receipt-123.md
  - wiki/judgments/foo.md
patch:
  kind: diff  # 或 full_replace
  before_hash: sha256:...  # target 文件当前 hash，revert 依据
  content: |
    <unified diff or full content>
rationale: |
  系统观察到 5 次 review reject，归因显示当前 prompt 在 X 情况下歧义。
  建议补充约束 Y，以减少此类失败。
revert_plan:
  kind: restore_before_hash
  fallback: human_merge_required
review_queue_entry_id: review-456
state: candidate | accepted | rejected | reverted
created_at: 2026-04-24T12:00:00+08:00
---
```

### 10.4 审批流程

目标 L3 proposal **物理目录独立**，但**逻辑接入现有 review queue**：

```
propose (auto) → review queue (human) → accept? 
                                         ├─ yes → apply → receipt + audit
                                         └─ no  → rejected (保留记录)
```

- 复用现有 `review / scoped apply / scoped revert / audit` 语义。
- proposal 作为独立 proposal kind，避免与普通 rewrite proposal 混淆。
- **Accept 前绝不写回**目标文件。

### 10.5 Accept 后的写回

人工 accept 后：

1. 验证 `before_hash` 仍匹配 target 文件（若已被人手修改，判为 stale，触发 `human_merge_required`）。
2. 应用 patch 到 `prompts/*.md` 或 `schema/policies/*`。
3. 生成 receipt（记录 before_hash / after_hash / diff / proposal_id）。
4. 写 audit entry。

### 10.6 Revert 规则

- **默认 revert**：按 receipt 还原到 `before_hash` 指示的内容。
- **不可 clean revert 的情形**：target 文件在 accept 后被人手再次修改，`after_hash` 与当前不一致——此时**不**强制 revert，而是：
  - 生成 `revert-hint.md`，标记冲突
  - 提示人工 merge
  - proposal 状态转为 `revert_conflict`

### 10.7 写回范围硬边界

L3 proposal **只允许**写入以下文件：

- `prompts/*.md`
- `schema/policies/*`

**永不**允许：

- 写入 `src/aiwiki/**`（runtime 代码）
- 写入 `schema/` 的核心结构文件（如 `schema/manifest.json` / `schema/writeback.md`）
- 写入 `schema/protocols/*`（协议核心契约）

## 11. CLI Semantics Summary

| 命令 | 语义 | 写目标 |
|---|---|---|
| `aiwiki ask "<q>" --corpus <id>` | 当前：绑定或创建 corpus turn；追加 output_refs | `output/reports` / `output/slides` / `output/figures` 等产物 + `.aiwiki/state/output-candidates.json` + `.aiwiki/state/active-corpora.json` |
| `aiwiki promote <artifact_ref>` | 当前：output candidate → `wiki/derived/` | `wiki/derived/` + candidate state |
| `aiwiki demote <artifact_ref>` | 当前：demote output candidate | `.aiwiki/state/output-candidates.json` |
| `aiwiki alchemy-start <corpus-id> --topic <topic>` | 当前：从该 corpus 的已 promoted output 创建 draft elixir | `wiki/elixirs/` |
| `aiwiki alchemy-distill <elixir-id> --question <q>` | 当前：推进 draft/distilling elixir iteration | `wiki/elixirs/` |
| `aiwiki alchemy-seal <elixir-id>` | 当前：校验后标记 settled | `wiki/elixirs/` |
| `aiwiki protocol-learn-add/list/show/age/verify/demote/archive/supersede` | 当前：L2 learning 生命周期治理 | `wiki/protocol-learnings/` |
| `aiwiki alchemy heavy <scope>` | planned：手动触发 heavy 炼丹 | 按 scope |
| `aiwiki review proposals` | planned：查看 L3 proposal 队列 | 读 only |
| `aiwiki apply <proposal-id>` | planned：人工 accept L3 proposal | `prompts/*.md` 或 `schema/policies/*` |
| `aiwiki revert <receipt-id>` | planned：按 receipt 回滚 L3 accept | 恢复 target 文件 |

## 12. Audit, Revert, and Backward Compatibility

### 12.1 统一 audit 语义

以下目标动作**全部**需要产生 audit entry：

- heavy alchemy 启动 / 完成（planned）
- light alchemy 启动 / 完成（含 budget_exceeded；planned）
- elixir promotion / demotion / supersede（candidate promote chain planned；当前 seal 直接更新 elixir state）
- L2 learning 状态变更（当前已有 protocol-learning aging audit / 状态文件）
- L3 proposal generation / accept / reject / revert（planned）

当前审计仍是分散日志：execution receipts、LLM receipts、runtime history、protocol-learning aging audit 等分别承担各自领域的审计语义。目标通用审计流为 `.aiwiki/state/audit.jsonl`（append-only，planned）。

### 12.2 Revert 适用范围

revert **可以**：

- 回滚 L3 accept（按 before_hash；planned）
- 回滚 elixir promotion（回到 candidate；planned）
- 回滚 L2 learning activate（回到 stale）

revert **不可以**：

- 回滚 `raw/` 的历史事实
- 回滚 audit entry 本身
- 回滚 planner 决策日志（planned；当前 `planner-state.json` 不是 append-only log）

### 12.3 向后兼容

- 既有 `compile / lint / nightly` 与 scoped apply/revert CLI（如 `apply-rewrite / revert-rewrite`、`apply-action / revert-action`、`apply-archive / revert-archive`）**不变**，仍作为 operator-visible primitives。
- 本文档引入的新机制都是**叠加**在现有 primitives 之上的调度与 proposal 层。

### 12.4 9+ Rollout Gate Matrix

| Milestone | 新增能力 | 禁止事项 | 验收 gate |
|---|---|---|---|
| **M0 Baseline Freeze** | 固化当前 active corpus、output candidates、L2 learning、最小金丹、scoped apply/revert。 | 不新增自动调度；不迁移旧金丹。 | `verify` 全绿；docs 与 CLI 语义一致；Product Shell 只读事实不回退。 |
| **M1 Signal Observability** | 新增 `.aiwiki/state/signals.jsonl` 与 `.aiwiki/state/planner-log.jsonl`，从 runtime-history / receipts 归一化 signal。 | `mode` 只能是 `observe_only`；不得触发 phase。 | signal schema fixture、dedupe replay、trace 回链、坏 schema fail-fast。 |
| **M2 Elixir Candidate Plane** | 新增 `output/_candidates/elixirs/`、candidate frontmatter、promote/demote/revert receipt。 | 不强制迁移旧 `wiki/elixirs/`；不绕过 DAG / provenance gate。 | promote hash gate、revert clean/stale 分支、DAG 环路拒绝、路径穿越拒绝。 |
| **M3 L3 Manual Proposal** | 新增 prompt/policy proposal kind，先支持手工/fixture 创建、review、apply、revert。 | 不自动生成 proposal；不写 `src/aiwiki/**`、schema core 或 protocol core。 | before_hash mismatch 退为 stale；receipt 可 clean revert；冲突生成 human_merge_required。 |
| **M4 Heavy/Light Dry-run Wrapper** | `alchemy heavy/light --dry-run` 只计算 signal scope、primitive plan、预算与锁结果。 | 默认不 execute；light 不升级 heavy；全量 heavy 不自动授权。 | scope preview 稳定；预算超限可解释；锁冲突 skip；primitive plan 可复现。 |
| **M5 Controlled Execution** | heavy/light 允许显式 `--apply` 组合 scoped primitives。 | 不允许 hidden backend choice；不允许无 receipt 写回。 | 每个 phase 有 trace_id、receipt、audit entry；失败可从上一稳定点恢复。 |

达到 9+ 可行性的条件不是“自动化更多”，而是每个 milestone 都满足：可重放、可 dry-run、可回滚、可停用、可用现有 gate 验证。

### 12.5 Stop Lines and Kill Switches

- Signal replay 不能稳定去重时，planner 停留在 `observe_only`。
- 任一 proposal / candidate 无法产生 clean receipt 时，不允许进入默认 apply。
- 任一写回目标 hash 不匹配时，必须转为 `stale` 或 `human_merge_required`。
- Heavy/light wrapper 在没有 dry-run plan 的情况下不得执行。
- LLM backend 未显式配置或 receipt 缺失 usage/accounting 时，不得作为自动 proposal 依据。
- 新机制导致 `compile / lint / nightly` deterministic baseline 回归时，必须局部禁用该机制，而不是修改 baseline 迁就它。

## 13. Risks and Mitigations

| 风险 | 问题 | 缓解 |
|---|---|---|
| **L3 冷启动噪音** | 初期 failure 稀疏，proposal 低质 | 设阈值（recurring + ≥N 证据）；按 protocol 聚类；要求双证据（signal + feedback） |
| **金丹 DAG 伪循环** | A 引 B、B 通过 judgment 间接回指 A | promote gate 强制 DAG 校验；强制底层证据锚定 |
| **Light 抢 heavy 锁** | 定时 light 阻塞事件 heavy | single 锁 + heavy 优先；light 拿不到锁即 skip |
| **L2 过拟合** | active learning 积累导致 ask 行为漂移 | 显式装载；aging / demote；replacement DAG 校验 |
| **候选 / proposal 堆积** | `_candidates/`、`_proposals/` 沦为垃圾场 | light 负责 TTL 与 aging；review center 独立 surfacing |
| **Heavy 范围膨胀** | 本来 targeted，最后退化全库 | planner 先算 scope；全量 heavy 需 `escalate-human` |
| **Elixir 与 judgment 混淆** | 被误用成“更高级 judgment” | 文档写死：金丹是复合资产，引用而非覆盖 judgment |
| **L3 accept 后 revert 不安全** | target 被人手改过，自动 revert 破坏修改 | 基于 before_hash 判 stale；冲突时退化为 human_merge_required |

## 14. Document Status and Supersede Map

本文档取代：

- `docs/Furnace Material Scaling.md`（规模化设计被 §2 / §3 / §5 / §6 吸收）
- `docs/Furnace Material State Model.md`（状态模型被 §6 吸收）
- `docs/Furnace Incremental Compile Plan.md`（增量 compile 被 §4 / §5 吸收）

旧文档应物理归档到 `docs/archive/`，并在 frontmatter 标注 `superseded_by: docs/Furnace Evolution Mechanics.md`。

配套文档：

- [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]]：终局架构 SoT
- [[docs/Furnace Elixir|金丹机制 thesis]]：金丹产品思路（仍 accepted）
