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

> **实现状态说明（2026-04-26）**：本文是“目标契约 + 当前差距”的 SoT。当前已落地 active corpus / output candidates、L2 protocol-learning 生命周期与显式 activation revert baseline、repair planner state、nightly low-risk auto-consume、显式 backend 选择、金丹 `alchemy-start / alchemy-distill / alchemy-finalize / alchemy-promote` 候选主路径，legacy elixir migration read-only preview 与显式 apply baseline、superseded cleanup read-only preview 与显式 deletion apply baseline，planner-log observe-only / execute-mode decision log 与 rollback marker baseline，heavy/light lane read-only dry-run preview、显式 receipted action apply bridge、deterministic primitive receipt wrapper、显式 heavy lane `review` primitive apply、execute-mode `alchemy auto` deterministic 调度入口、lane primitive trace/audit metadata、`judge/distill/review/propose` scoped dry-run preview、`review` 直接 scoped apply baseline 和其余高风险 primitive deferred metadata，以及 L3 prompt/policy proposal 的手工/fixture 创建、execute-mode deterministic automatic candidate generation baseline、Shell review surface、人工 reject、hash-gated apply、receipt-gated revert 与 execution receipt history audit metadata baseline；通用 audit stream 已提供 preview、显式 append-only backfill，并已接入 execution receipt / runtime history / LLM receipt / protocol-learning aging writer direct append，backfill 对 direct append 已写入的同一 source event 幂等跳过。LLM-backed L3 内容生成与 L3 auto-accept 不在默认可用边界内，以下章节用 `implemented / partial / planned` 标记区分。

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
- L3 prompt/policy proposal 的触发、产物、审批、写回、revert 契约（manual baseline + execute-mode automatic candidate generation baseline；auto-accept 永不默认开放）

本文档**不**定义：

- Product Shell UI / surface 细节
- EP 具体实施时间表（见 `PROGRESS.md` 与 `.codex/plans/active.md`）
- 终局架构愿景（见 [[docs/Furnace Agent Architecture|炼丹炉 Agent 架构]]）

## 2. Signal Taxonomy

目标契约：所有进入完整 planner 的 signal 都必须先被标准化为 append-only JSONL record。Signal 只描述“发生了什么”，**从不直接触发 phase**；是否进入 heavy / light / proposal，必须经过 planner 决策。

### 2.1 Field specification

`volatile` 表示该字段**不得参与 dedupe identity**；它可以持久化，但不构成幂等边界。

| name | type | required | volatile | 说明 |
|---|---|---|---|---|
| `schema_version` | integer | yes | no | 当前固定为 `1`。仅按显式 version parser 解释。 |
| `signal_id` | string | yes | yes | signal stream 内唯一；格式 `^sig-[0-9]{8}-[a-z0-9]{6,32}$`。由 collector 在写入 `signals.jsonl` 时生成。 |
| `dedupe_key` | string | yes | no | signal 的唯一幂等边界；格式见 §2.3。planner / replay 只按精确字符串相等去重。 |
| `kind` | enum | yes | no | `raw_added / counter_evidence / drift / review_feedback / runtime_failure / schedule_tick / learning_threshold / elixir_dependency_break`。 |
| `scope` | object | yes | no | 归一化作用域；用于 planner scope 计算，不等同于 trigger source。 |
| `scope.protocol` | enum | yes | no | `general / investing / research / product / ops`。 |
| `scope.corpus_id` | string | no | no | corpus 级信号时填写；未知时省略，不得写 `null`。 |
| `scope.source_ids` | array[string] | yes | no | 规范化后的 source id 列表；无则写 `[]`。 |
| `scope.concept_slugs` | array[string] | yes | no | 规范化后的 concept slug 列表；无则写 `[]`。 |
| `scope.elixir_refs` | array[string] | yes | no | 规范化后的 elixir ref 列表；无则写 `[]`。 |
| `scope.judgment_refs` | array[string] | yes | no | 规范化后的 judgment ref 列表；无则写 `[]`。 |
| `severity` | enum | yes | yes | `low / medium / high / critical`。kind 表中的默认值只用于 emitter defaulting；落盘时必须显式写出。 |
| `evidence_refs` | array[string] | yes | yes | 证据回链；可为空 `[]`，但字段必须存在。 |
| `budget_hint` | object | no | yes | planner 预算提示；仅作 hint，不改变 signal identity。 |
| `budget_hint.max_pages` | integer | no | yes | 正整数。 |
| `budget_hint.max_tokens` | integer | no | yes | 正整数。 |
| `emitted_at` | string | yes | yes | RFC 3339 UTC 时间戳；格式固定 `YYYY-MM-DDTHH:MM:SSZ`。 |
| `emitted_by` | enum | yes | yes | 谁 emit 了这条 normalized signal：`nightly / user / compile / external`。 |
| `source_kind` | enum | yes | no | 原始事件所属 artifact class：`runtime_history / llm_receipt / review_outcome / archive_event / protocol_learning_event / execution_receipt`。 |
| `source_event_ref` | string | yes | yes | 指向原始 artifact 的精确回链；用于审计，不用于 dedupe。 |
| `trace_id` | string | yes | yes | 跨 signal → planner-log → receipt 的链路 id；格式见 §2.4。 |

目标 schema：

```json
{
  "schema_version": 1,
  "signal_id": "sig-20260424-abc123",
  "dedupe_key": "raw_added:research:runtime_history:raw/inbox/example.md",
  "kind": "raw_added",
  "scope": {
    "protocol": "research",
    "corpus_id": "research-transformer-scaling",
    "source_ids": ["src-1"],
    "concept_slugs": ["scaling-law"],
    "elixir_refs": [],
    "judgment_refs": ["judgment-foo"]
  },
  "severity": "medium",
  "evidence_refs": ["raw/inbox/example.md#L12", "wiki/judgments/foo.md"],
  "budget_hint": {
    "max_pages": 20,
    "max_tokens": 4000
  },
  "emitted_at": "2026-04-24T04:00:00Z",
  "emitted_by": "nightly",
  "source_kind": "runtime_history",
  "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L42",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

`emitted_by` 与 `source_kind` 是两个正交维度：前者回答“**谁 emit 了 signal**”，后者回答“**原始事件来自哪个 artifact**”。二者不得混用，也不得互相替代。

Signal kinds（本轮最小集）：

| kind | 触发时机 | 默认 severity |
|---|---|---|
| `raw_added` | drop-url / drop-pdf / drop-image / drop-repo / 手工添加 | medium |
| `counter_evidence` | 新证据与既有 judgment 冲突 | high |
| `drift` | nightly 发现 judgment 证据基础已变 | high |
| `review_feedback` | 用户 accept / reject / rewrite | low-high（按裁决映射） |
| `runtime_failure` | contract validation / lint 持续失败 | medium |
| `schedule_tick` | nightly / weekly / periodic light tick | low |
| `learning_threshold` | protocol-learning 候选累积到阈值 | medium |
| `elixir_dependency_break` | 被引用 elixir 被 demote / superseded | high |

当前实现中，`learning_threshold` 来自 `protocol-learn-age --apply` / nightly protocol-learning aging 的 runtime-history `learning-threshold` 事件；collector 不直接扫描 `wiki/protocol-learnings/` 页面。

Signal **从不直接触发 phase**，必须经过 planner 决策。

### 2.2 Canonical JSON rules

- 持久化格式固定为 **UTF-8 JSONL**；一行一个 JSON object；不做 multiline pretty-print。
- top-level 字段按以下顺序序列化：  
  `schema_version, signal_id, dedupe_key, kind, scope, severity, evidence_refs, budget_hint, emitted_at, emitted_by, source_kind, source_event_ref, trace_id`
- `scope` 内字段按以下顺序序列化：  
  `protocol, corpus_id, source_ids, concept_slugs, elixir_refs, judgment_refs`
- `budget_hint` 内字段按以下顺序序列化：  
  `max_pages, max_tokens`
- `scope.source_ids / scope.concept_slugs / scope.elixir_refs / scope.judgment_refs / evidence_refs` 必须去重并按字典序升序写出。
- 时间戳必须使用 **RFC 3339 UTC**，格式固定为 `YYYY-MM-DDTHH:MM:SSZ`；timezone 必填；v1 不允许 offset form，不允许小数秒。
- v1 **禁止 `null`**。可选字段未知时省略；已知为空的 list 字段必须写 `[]`。
- v1 **禁止浮点数**。所有 numeric 字段都必须是十进制整数。

### 2.3 Dedupe identity

- `dedupe_key` 是 signal 的**唯一持久化幂等边界**；不得再引入平行的 `(source_kind, source_id, event_hash)` 对外 schema。
- `dedupe_key` 由 **collector / normalizer** 在 signal materialization 时生成；planner 不得重写。
- v1 格式固定为：  
  `<kind>:<scope.protocol>:<source_kind>:<source_identity>`
- `source_identity` 必须是 source artifact 内的稳定标识，**不得**包含行号、offset、mtime、重放时间戳等 append-only 噪音。  
  - 例：`raw/inbox/example.md`
  - 若 source artifact 无短且稳定的业务 id，则写为 `sha256-<16 lowercase hex>`，其输入是**去除 source 侧 volatile 字段后的 canonical source payload**。
- 以下字段不得参与 dedupe identity：  
  `signal_id`, `severity`, `evidence_refs`, `budget_hint`, `emitted_at`, `emitted_by`, `source_event_ref`, `trace_id`，以及 source artifact 内的行号 / offset / mtime / replay timestamp。

### 2.4 trace_id lifecycle

- `trace_id` 格式固定为 **lowercase UUIDv4**：  
  `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
- 若原始 source artifact 已带合法 `trace_id`，signal 必须沿用；否则由 collector 在首次 signal materialization 时生成。
- 同一条处理链中的 `signal / planner-log / receipt / audit entry` 必须逐字复用同一个 `trace_id`。
- 对同一 `dedupe_key`，若重放输入携带不同 `trace_id`，视为 `trace_id_conflict`：保留已落盘记录，拒绝新记录，不做静默覆盖。

### 2.5 Fail-fast rules

以下情况必须立即拒绝写入 `signals.jsonl`：

- 任一 required 字段缺失、为 `null`、类型错误。
- `schema_version != 1`。
- `signal_id` 不匹配 `^sig-[0-9]{8}-[a-z0-9]{6,32}$`。
- `trace_id` 不是 lowercase UUIDv4。
- `emitted_at` 不是 `YYYY-MM-DDTHH:MM:SSZ`。
- enum 字段不在闭集内。
- list 字段含非字符串元素、重复值，或未按 canonical 顺序写出。
- `budget_hint` 存在但两个子字段都缺失，或任一值不是正整数。
- 出现未知 top-level 字段或未知 nested 字段。v1 对 unknown fields 采用 **strict**；forward-compat 仅通过新 `schema_version` 实现。
- `source_kind` 与 `source_event_ref` 明显不一致（例如 `source_kind=runtime_history`，但 ref 不指向 runtime-history artifact class）。

### 2.6 Schema evolution

- 以下任一变化都必须递增 `schema_version`：  
  新增 / 删除 / 重命名字段；变更 requiredness；变更 type；变更 enum 闭集；变更 canonical JSON 规则；变更 `dedupe_key` 生成规则；变更 `trace_id` 格式或传播语义。
- 纯文案澄清、注释增强、对**原本就非法**数据的更明确报错，不触发 version bump。
- reader / validator 必须先按 `schema_version` 选择 parser，再做字段校验；不允许 best-effort 混读，不允许 silent downgrade。

当前状态：runtime 已有 `runtime-history.jsonl`、LLM receipts、review / execution receipts、planner-state 等可观测输入；`signals-replay` 已能从 runtime history、LLM receipts 和 execution receipt history 中归一化部分 signal。`raw_added` 当前由 `ingest_source` 与 `drop-*` 投料入口先写 `runtime-history.jsonl` 的 `raw-added` 事件，再由 collector observe-only 映射；不直接扫描 `raw/` 作为事件源。`counter_evidence` 当前由 compile runtime 的 `counter_evidence_scan` 先写 runtime-history `counter-evidence` 事件，再由 collector observe-only 映射；不直接扫描 judgment / decision pages 作为事件源。`learning_threshold` 当前由 protocol-learning aging apply 写入 runtime-history `learning-threshold` 事件，再由 collector observe-only 映射；不直接扫描 `wiki/protocol-learnings/`。`schedule_tick` 当前由 `run_nightly` 成功路径写入 runtime-history `nightly` 事件，再由 collector observe-only 映射；nightly 不自动触发 `signals-replay` / `planner-log-replay` / lane apply。`archive_event` 的 `source_event_ref` 当前只允许指向 execution receipt history（如 `.aiwiki/state/execution-receipts.jsonl#L12`），避免把 `wiki/archives/` 事实页误当事件源。`review_outcome` 作为 future source_kind 只允许明确的 review outcome event log path；当前 review 事件仍通过 runtime history 映射，不新增第二套 writer。`.aiwiki/logs/runs.jsonl` 是 runner health/logging artifact，v1 不定义 `run_log` source_kind，不能伪装成现有 source_kind 接入 `signals-replay`。

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

每条决策包含：`schema_version / signal_id / dedupe_key / trace_id / decision / mode / reason_codes / budget_used / locks_acquired / primitive_refs / side_effects_allowed / decided_at`。

注：`trace_id` 按 §2.4 必须逐字复用上游 signal 的 trace_id；字段原先遗漏，
此处澄清，不触发 schema version bump（属于 §2.6 "纯文案澄清"）。

当前已落地的 planner 状态文件是 `.aiwiki/state/planner-state.json`，它不是 append-only decision log。

首版 planner-log 已以 `mode=observe_only` 落地，且 `side_effects_allowed=false`；当前 `planner-log-replay --execute` 可显式追加 `mode=execute` decision log，execute-mode 与 observe-only 用独立 dedupe identity 共存。execute-mode 只表达后续 scheduler 可消费的授权决策，不直接启动 compile、proposal generation 或 lane apply；`ignore` / `escalate-human` 即使在 execute mode 也保持 `side_effects_allowed=false`。当前所有 v1 signal kind 均已有 planner routing；`raw_added` 只写 light-lane decision；`counter_evidence` / `learning_threshold` 只写 `generate-proposal` / `enqueue-heavy` decision，不直接启动 compile、proposal generation 或 lane apply。带 `<kind>_observed` 的 `reason_codes` 必须先记录原始观测事实，再记录 `proposal_recommended` / `heavy_lane_recommended` 等建议动作，避免把建议动作误当成原始观测事实；`generate-proposal` decision 只进入 proposal / inspection 路径，不被 heavy/light dry-run lanes 消费。`aiwiki planner-log-rollback --dry-run` 只读预览 rollback marker；`--apply` 把 marker append 到 `.aiwiki/state/planner-log-rollback.jsonl`，不删除、不重写 planner-log，也不改变 planner-log schema。

## 4. Heavy Alchemy Contract

### 4.1 定位

heavy 是**事件驱动的深度重炼**，面向“知识意义可能被改变”的场景。

### 4.2 触发源

- `counter_evidence`（severity=high 及以上）
- `drift`（命中 active judgment 或 active corpus）
- `elixir_dependency_break`
- `learning_threshold` 达到结构调整条件
- 用户显式触发（当前已支持 `aiwiki alchemy heavy <scope> --dry-run` preview；执行留到 M5）

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

当前实现状态：dry-run 可以预览上述目标序列，但 lane `--apply --primitive` 只支持已 receipt 化的 `compile / lint / nightly / review` primitives，其中 `review` 只允许 heavy lane 显式执行。Runner 执行前必须确认对应 dry-run step 存在且 `apply_supported=true`；`alchemy auto --dry-run|--apply` 只消费 `mode=execute` planner-log decisions，并只调度已有 apply-supported deterministic primitives，不选择 `review`；L3 proposal 生成通过独立的 `l3-proposal-generate --dry-run|--apply` 消费 execute-mode `generate-proposal` decisions，不由 heavy/light lane 消费；`aiwiki alchemy judge <scope> --dry-run` 当前只读盘点 heavy dirty scope 内的 judgment refresh candidates，`aiwiki alchemy distill <scope> --dry-run` 当前只读盘点 elixir refresh candidates，`aiwiki alchemy review <scope> --dry-run` 当前只读盘点 review enqueue candidates，`aiwiki alchemy review <scope> --apply` 与 `aiwiki alchemy heavy <scope> --apply --primitive review` 可显式写入 review queue managed section 并生成 receipt/runtime-history/universal-audit，`aiwiki alchemy propose <scope> --dry-run` 当前只读盘点 proposal opportunities。`judge / distill / propose` 仍返回 `apply_supported=false` / `missing_receipted_scoped_contract` 并携带 deferred `apply_contract` metadata。

### 4.4 作用范围约束

- heavy 默认**不**做全库重刷；只在 dirty scope 上执行。
- 只有 **graph / contract 级损坏**（比如 schema 核心不一致、全局 DAG 破裂）才允许升级为全量 heavy，且需要 `escalate-human` 显式授权。

### 4.5 与现有 CLI 的关系

heavy 是目标**调度层**，底层仍复用现有 primitives：

- `compile` / `lint` / `nightly` / `review` 与现有 scoped apply/revert primitives 保持可单独运行。
- heavy 落地后只是按 planner 决策**组合**这些 primitives，并共享锁与 audit。
- 既有命令的语义**不变**。
- 当前 lane apply 只允许 `compile / lint / nightly / review` 中已在对应 dry-run plan 出现且 `apply_supported=true` 的 primitives；`review` 仅限 heavy lane 显式 apply，不进入 `alchemy auto`；`judge / distill / propose` 仍为 heavy/light lane 的 deferred apply primitives。L3 prompt proposal candidate generation 已由独立 `l3-proposal-generate` baseline 承接，保持 proposal-only 与人工 accept 边界。

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
| 候选（当前与目标，未 promote） | `output/_candidates/elixirs/<elixir-id>.md` |
| 持久（当前与目标） | `wiki/elixirs/<elixir-id>.md` |

目标契约要求候选平面与持久平面**物理隔离**，避免一个字段同时表达两种语义。`M2.1` 起，`alchemy-start / alchemy-distill` 已写入 `output/_candidates/elixirs/`（`draft / distilling`）；`alchemy-finalize / alchemy-promote` 为主路径。

迁移策略：

- 旧 `wiki/elixirs/` 文件继续按当前 schema 读取，不做强制搬迁。
- 当前可用 `aiwiki alchemy legacy-migration --dry-run` 只读盘点缺少 candidate tombstone 的 legacy settled elixir；`aiwiki alchemy legacy-migration --apply` 会为 `migration_required=true` 的 legacy settled elixir 创建缺失 candidate tombstone，并写 execution receipt / universal audit；apply 不修改 `wiki/elixirs/`，不迁移 conflict candidate，不执行 superseded cleanup。
- 当前可用 `aiwiki alchemy superseded-cleanup --dry-run` 只读盘点 candidate plane 中 superseded tombstone 的清理状态；`--apply` 只删除仍指向现存 settled elixir 的 superseded candidate tombstone，并写 execution receipt / universal audit；apply 不修改 `wiki/elixirs/`，不删除 conflict、missing-target 或 non-settled target tombstone。
- 新候选入口落地后，默认只对新金丹写入 `output/_candidates/elixirs/`。
- 任一候选 promote 失败必须保持 source candidate 不变，并写明失败原因；不得半写入 `wiki/elixirs/`。
- 任一候选 promote 成功后也保留 candidate（墓碑 / tombstone）：不删除候选文件，原地改写 frontmatter 为 `elixir_state: superseded`，并写入 `superseded_by: wiki/elixirs/<elixir-id>.md` 与 `promoted_at: <iso8601>`。
- 对应 revert 时，将 candidate 从 `superseded` 恢复为 `candidate`，清除 `superseded_by / promoted_at`，并删除 `wiki/elixirs/<elixir-id>.md` 的 promoted 文件。

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

当前最小实现已落地字段：`kind / elixir_id / elixir_state / protocol / iteration / provenance_corpus / derived_from / topic / counter_evidence / confidence_level / created_at / updated_at / distill_history_json`，`settled` 时补 `sealed_at`。

仍属于目标 schema（`M2.3+`）：`promoted_at / supersedes / superseded_by / judgment_refs / decision_refs / elixir_refs / corpus_id / review_after`。

确认分阶段约束：`M2.1` 起，新建 candidate frontmatter 默认写入 `counter_evidence: [NONE_FOUND]` 与 `confidence_level: low`，并覆盖 `alchemy-start` 与 `alchemy-distill` 的 candidate rewrite path；`counter_evidence` 的“必须存在且非空”强制仍在 `M2.3` promote gate 执行。旧 `wiki/elixirs/` 直写文件不做强制迁移补字段。

### 7.3 生命周期

| 状态 | 位置 | 入口 |
|---|---|---|
| `draft` | `output/_candidates/elixirs/` | `alchemy-start <corpus_id> --topic ...` |
| `distilling` | `output/_candidates/elixirs/` | `alchemy-distill <elixir_id> --question ...` |
| `candidate` | `output/_candidates/elixirs/` | `alchemy-finalize <elixir-id>`（作者显式 finalize，ready-for-promote） |
| `settled` | `wiki/elixirs/` | `alchemy-promote --elixir-id <elixir_id>` |
| `superseded` | `output/_candidates/elixirs/`（tombstone 保留） | 当前：候选 promote 成功后原地墓碑化 |

状态转移（`M2.2`）：

- `draft -> candidate`：`alchemy-finalize <elixir-id>`。
- `distilling -> candidate`：`alchemy-finalize <elixir-id>`。
- `candidate -> distilling`：再次 `alchemy-distill <elixir-id> --question ...`（回退，允许人工改稿）。
- `candidate -> settled`：`alchemy-promote --elixir-id <elixir-id>`。
- M2.5 起，旧 seal alias/API 保持删除状态；candidate 进入 settled 只走 `alchemy-promote`。

### 7.4 DAG 约束

- 金丹引用链（`elixir_refs`）**必须**构成有向无环图。
- 新金丹**不得**只依赖旧金丹的结论自举——必须同时锚定至少一条 `raw/` 或 `wiki/sources/` / `wiki/judgments/` 的底层证据。
- 当前 `alchemy-distill / alchemy-finalize / alchemy-promote` 已校验金丹 DAG、自引用、路径穿越和底层 `wiki/derived/` 锚定。

### 7.5 Counter-evidence 强制

- `M2.2` `alchemy-finalize` 只执行结构性校验（provenance / DAG / `wiki/derived/` anchor / 路径穿越），不强制 `counter_evidence` 非空；校验失败必须保持 candidate 文件不变，不得半写成 `candidate` 状态。
- 目标 promote gate 中 `counter_evidence` 字段**不得为空**。
- 若真的没有反证，显式写 `counter_evidence: [NONE_FOUND]` 并记录 `confidence_level: low`。
- `M2.3` promote gate 强制规则：`counter_evidence` 必须存在且非空；`[NONE_FOUND]` 视为“显式声明无反证”，允许 promote。
- 当 `counter_evidence == [NONE_FOUND]` 时，`confidence_level` 必须为 `low`；否则 `confidence_level` 可为 `low / medium / high`。
- M2.3 起，promotion receipt 的 `bundle` 同步记录当次 gate 通过的 `counter_evidence` 与 `confidence_level`，使 execution receipt history 可直接审计 promote evidence。

分阶段落地：`M2.1` 负责 candidate 默认写入，`M2.3` 负责 promote gate 强制校验。

### 7.6 Elixir 生命周期 Receipt（复用 ExecutionReceipt）

- Elixir `promote / demote / revert` 复用现有 `build_execution_receipt` 基底（`src/aiwiki/app_execution.py:168`），不引入 elixir 专用第二套 receipt 物理层。
- `subject_kind` 明确新增：`elixir_promotion` / `elixir_demotion` / `elixir_revert`。
- 写入路径保持不变：History 写 `.aiwiki/state/execution-receipts.jsonl`；Single 写 `output/control/execution-receipts/<action_id>.json`。
- payload 至少包含：`elixir_id`、`protocol`、`from_state`、`to_state`、`candidate_path`、`wiki_path`；`demote/revert` 需补失败原因或来源 receipt id。
- M2.4 起，`elixir_revert` / `elixir_demotion` receipt 的 `bundle` 显式记录状态迁移与双平面路径；已有 `dependency_breaks` 与 source promotion receipt anchor 保持在同一 bundle 内。
- M3.1 起，`dependency_breaks[].break_reason` 是闭集：`source_demoted / source_reverted`；非法 reason 不得进入 `elixir_dependency_break` signal。
- M2.6 起，elixir lifecycle receipt 的 `action_id` 使用 `elixir-<op>-<slug>-<epoch_ms>` 事件级 id；同毫秒文件冲突时追加数字后缀，避免覆盖已有 receipt。
- M3.4 起，`alchemy-revert` 的 clean/stale 判定只依赖 promotion receipt 中的 settled/tombstone sha256 hash anchors；`applied_at` 与 tombstone `promoted_at` 不再作为 fallback 判据。

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
# → 当前：从该 corpus 下已 promoted 的 wiki/derived/ 输出生成 output/_candidates/elixirs/<elixir-id>.md，state=draft

aiwiki alchemy-distill <elixir-id> --question "延迟约束如何改变架构权衡？"
# → 当前：在 output/_candidates/elixirs/ 上推进 iteration，保留 provenance，state=distilling

aiwiki alchemy-promote --elixir-id <elixir-id>
# → 当前：校验 gate（含 counter_evidence）与 DAG / wiki/derived/ 锚定后写入 settled
```

**当前验收准则**：能从已 promoted output 生成 elixir，能多轮 distill，能 finalize+promote，并拒绝空 provenance、自引用、路径穿越和 DAG 环路。

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

**架构授权的 partial 能力**。agent 可生成对 `prompts/*.md` 和 `schema/policies/*` 的修改提案，但**必须人工 accept** 才写回。当前 runtime 已提供 manual baseline：`l3-proposal-create` 创建 `prompt_proposal / policy_proposal` fixture，`review proposals` 与 Product Shell `review_controls.l3_proposals` 只读查看队列，`review proposal-generation` 预览 planner-log 中的 `generate-proposal` candidates，`l3-proposal-generate --dry-run|--apply` 从 execute-mode 且带 `proposal_recommended` 的 planner decisions deterministic 创建 prompt proposal 候选，`review proposal <proposal-id> --status rejected` 显式否决，`apply <proposal-id>` 执行人工 accept + hash-gated 写回，`revert <receipt-id>` 按 receipt clean revert 或生成 `human_merge_required` hint；apply/revert receipt 顶层暴露 execution receipt history audit metadata。自动 generation 只写 proposal plane/state，不写目标文件、不调用 LLM、不自动 accept；现有成熟 proposal 类型仍包括 execution proposal 与 concept rewrite proposal。

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
- `schema/policies/*`（`ensure_layout` 与新 vault bootstrap 会创建该目录，但不生成默认 policy 文件）

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
| `aiwiki alchemy-start <corpus-id> --topic <topic>` | 当前：从该 corpus 的已 promoted output 创建 draft elixir | `output/_candidates/elixirs/` |
| `aiwiki alchemy-distill <elixir-id> --question <q>` | 当前：推进 draft/distilling elixir iteration | `output/_candidates/elixirs/` |
| `aiwiki alchemy-promote --elixir-id <elixir-id>` | 当前：candidate promote 为 settled | `wiki/elixirs/` + `output/_candidates/elixirs/` tombstone + receipts |
| `aiwiki alchemy legacy-migration --dry-run` | 当前：只读盘点 legacy settled elixir 的 candidate tombstone 状态 | 读 `wiki/elixirs/` + `output/_candidates/elixirs/` |
| `aiwiki alchemy legacy-migration --apply` | 当前：显式为缺失 tombstone 的 legacy settled elixir 创建 candidate tombstone，并写 receipt / audit；不改 settled source，不做 cleanup | `output/_candidates/elixirs/` + execution receipt |
| `aiwiki alchemy superseded-cleanup --dry-run` | 当前：只读盘点 superseded tombstone 的清理候选和阻塞原因；不删除 | 读 `output/_candidates/elixirs/` + `wiki/elixirs/` |
| `aiwiki alchemy superseded-cleanup --apply` | 当前：显式删除支持清理的 superseded candidate tombstone，并写 receipt / audit；不改 settled source，不删除阻塞项 | `output/_candidates/elixirs/` + execution receipt |
| `aiwiki protocol-learn-add/list/show/age/verify/revert-activate/demote/archive/supersede` | 当前：L2 learning 生命周期治理；`revert-activate` 只回滚带 metadata 的最近一次 `stale -> active` verify activation | `wiki/protocol-learnings/` + runtime history |
| `aiwiki signals-list/show` / `aiwiki planner-log-list` | 当前：只读 inspection；`--since` 必须为 ISO datetime，`--limit` 必须大于 0 | 读 `.aiwiki/state/signals.jsonl` / `.aiwiki/state/planner-log.jsonl` |
| `aiwiki planner-log-rollback --dry-run\|--apply` | 当前：预览或显式追加 rollback marker；planner-log 本体保持 append-only，不删除不重写 | 读 `.aiwiki/state/planner-log.jsonl`；写 `.aiwiki/state/planner-log-rollback.jsonl` |
| `aiwiki audit-preview --dry-run` | 当前：只读预览分散审计来源归一化后的目标 audit stream 记录；不写 `audit.jsonl` | 读 execution receipts / LLM receipts / runtime history / protocol-learning aging audit |
| `aiwiki audit-backfill --apply` | 当前：显式 append-only backfill 缺失的 universal audit records；按 `audit_event_id` 幂等跳过已有记录 | `.aiwiki/state/audit.jsonl` |
| `aiwiki alchemy heavy <scope> --dry-run` / `aiwiki alchemy light <scope> --dry-run` | 当前：只读 preview lane scope、primitive plan、预算、锁结果和 deferred primitive metadata；不 execute | 读 `.aiwiki/state/planner-log.jsonl` + `.aiwiki/state/signals.jsonl` |
| `aiwiki alchemy judge <scope> --dry-run` | 当前：只读 preview heavy dirty scope 内的 judgment refresh candidates；不调用 LLM、不写 judgment/decision、不写 receipt/audit | 读 `.aiwiki/state/planner-log.jsonl` + `.aiwiki/state/signals.jsonl` |
| `aiwiki alchemy distill <scope> --dry-run` | 当前：只读 preview heavy dirty scope 内的 elixir refresh candidates；不调用 LLM、不写 elixir candidate、不写 receipt/audit | 读 `.aiwiki/state/planner-log.jsonl` + `.aiwiki/state/signals.jsonl` |
| `aiwiki alchemy review <scope> --dry-run\|--apply` | 当前：dry-run 只读 preview heavy dirty scope 内的 review enqueue candidates；apply 显式写 review queue managed section 并写 receipt/runtime-history/universal-audit；不调用 LLM | 读 `.aiwiki/state/planner-log.jsonl` + `.aiwiki/state/signals.jsonl`；apply 写 `wiki/indexes/review-queue.md` 与 receipt/audit |
| `aiwiki alchemy propose <scope> --dry-run` | 当前：只读 preview heavy dirty scope 内的 proposal opportunities；不调用 LLM、不写 proposal plane、不写 receipt/audit；不消费 `generate-proposal` decisions | 读 `.aiwiki/state/planner-log.jsonl` + `.aiwiki/state/signals.jsonl` |
| `aiwiki alchemy heavy|light <scope> --apply --action-id <id>` | 当前：仅在 dry-run plan 非空时，显式桥接到既有 receipted low-risk action batch apply；不执行 receipt-less lane 序列 | `apply_machine_memory_actions_batch` receipts |
| `aiwiki alchemy heavy|light <scope> --apply --primitive compile|lint|nightly` / `aiwiki alchemy heavy <scope> --apply --primitive review` | 当前：执行已支持 primitives 并写 lane primitive execution receipt；`review` 复用 direct scoped review apply 写 review queue managed section；receipt 顶层携带 planner `trace_id/trace_ids` 与 execution receipt history audit metadata；不调用 LLM-backed `run-*` | `output/control/execution-receipts/` + `.aiwiki/state/execution-receipts.jsonl`；`review` 另写 `wiki/indexes/review-queue.md` |
| `aiwiki alchemy auto --dry-run\|--apply` | 当前：显式消费 `mode=execute` planner decisions，并只调度已有 apply-supported deterministic lane primitives；不消费 observe-only decisions | lane primitive receipts + runtime history |
| `aiwiki l3-proposal-create --kind prompt_proposal\|policy_proposal ...` | 当前：手工/fixture 创建 L3 proposal；只写 proposal 平面和 state，不写目标文件 | `output/_proposals/prompt\|policy/` + `.aiwiki/state/l3-proposals.json` |
| `aiwiki l3-proposal-generate --dry-run\|--apply` | 当前：从 execute-mode `generate-proposal` planner decisions deterministic 创建 prompt proposal 候选；observe-only candidates 只会被标为 blocked；不写目标文件、不调用 LLM、不自动 accept | `output/_proposals/prompt/` + `.aiwiki/state/l3-proposals.json` |
| `aiwiki review proposals` | 当前：查看 L3 proposal 队列 | 读 only |
| `aiwiki review proposal-generation` | 当前：只读预览 planner-log 中的 `generate-proposal` candidates，标明 execute-mode eligible 与 observe-only blocked 状态；不写 `_proposals` 或 state | 读 `.aiwiki/state/planner-log.jsonl` |
| `aiwiki shell-status` | 当前：在 `review_controls.l3_proposals` 暴露 L3 proposal review controls 与 command hints | 读 `.aiwiki/state/l3-proposals.json` |
| `aiwiki review proposal <proposal-id> --status rejected` | 当前：人工 reject L3 proposal；只更新 proposal state/page，不写目标文件，不生成 apply receipt | `output/_proposals/prompt\|policy/` + `.aiwiki/state/l3-proposals.json` |
| `aiwiki apply <proposal-id>` | 当前：人工 accept L3 proposal；`before_hash` mismatch 时转 `stale` 并拒绝半写 | `prompts/*.md` 或 `schema/policies/*` + execution receipt |
| `aiwiki revert <receipt-id>` | 当前：按 L3 apply receipt 回滚；`after_hash` mismatch 时生成 `human_merge_required` hint，不覆盖目标文件 | 恢复 target 文件或写 `output/_proposals/*/*-revert-hint.md` |

## 12. Audit, Revert, and Backward Compatibility

### 12.1 统一 audit 语义

以下目标动作**全部**需要产生 audit entry：

- heavy alchemy 显式 apply 启动 / 完成（当前通过 `alchemy-lane-started / alchemy-lane-completed` runtime history 进入 universal audit）
- light alchemy 显式 apply 启动 / 完成（当前通过 `alchemy-lane-started / alchemy-lane-completed` runtime history 进入 universal audit；budget_exceeded 仍由 dry-run status 表达，不写执行事件）
- elixir promotion / demotion / supersede（candidate promote chain）
- L2 learning 状态变更（当前已有 protocol-learning aging audit / 状态文件；threshold signal 与 activation revert 通过 runtime history 观察映射）
- L3 proposal manual create / generate candidate / reject / accept / revert（当前已有 manual baseline 与 execute-mode automatic candidate generation baseline）

当前审计仍以分散日志为源：execution receipts、LLM receipts、runtime history、protocol-learning aging audit 等分别承担各自领域的审计语义。`aiwiki audit-preview --dry-run` 可只读预览这些来源归一化后的目标 audit record（含 source stream/ref、event type、trace、subject、revert_supported）。`aiwiki audit-backfill --apply` 可显式把缺失记录 append 到 `.aiwiki/state/audit.jsonl`，并按稳定 `audit_event_id` 幂等跳过已存在记录。M5.9 起，`append_execution_receipt_history` 在写 execution receipt history 后会直接 append 对应 universal audit record；M5.10 起，`append_runtime_history` 在写 runtime history 后也会直接 append 对应 universal audit record；M5.11 起，LLM receipt log 写入后也会直接 append 对应 universal audit record；M5.12 起，protocol-learning aging audit 写入后也会直接 append 对应 universal audit record。因为 protocol-learning aging audit 是覆盖写 JSON snapshot，其 universal audit `source_ref` 带 `run_at` fragment 以区分多次 aging run。

### 12.2 Revert 适用范围

revert **可以**：

- 回滚 L3 accept（当前已支持 receipt-gated clean revert：按 apply receipt `after_hash` 校验当前目标，再恢复 `before_content`；冲突时写 `human_merge_required` hint）
- 回滚 elixir promotion（当前已支持 receipt/hash-gated revert：删除 settled elixir、恢复 candidate tombstone 为 candidate，并写 `elixir_revert` execution receipt / universal audit）
- 回滚 L2 learning activate（当前已支持显式 `protocol-learn-revert-activate`，仅回滚带 metadata 的最近一次 `stale -> active` verify activation，并写 runtime-history / universal audit）

revert **不可以**：

- 回滚 `raw/` 的历史事实
- 回滚 audit entry 本身
- 回滚 planner 决策日志本体（当前 `planner-log-rollback --apply` 只追加独立 marker stream；不删除、不重写 append-only log）

### 12.3 向后兼容

- 既有 `compile / lint / nightly` 与 scoped apply/revert CLI（如 `apply-rewrite / revert-rewrite`、`apply-action / revert-action`、`apply-archive / revert-archive`）**不变**，仍作为 operator-visible primitives。
- 本文档引入的新机制都是**叠加**在现有 primitives 之上的调度与 proposal 层。

### 12.4 9+ Rollout Gate Matrix

| Milestone | 新增能力 | 禁止事项 | 验收 gate |
|---|---|---|---|
| **M0 Baseline Freeze** | 固化当前 active corpus、output candidates、L2 learning、最小金丹、scoped apply/revert。 | 不新增自动调度；不迁移旧金丹。 | `verify` 全绿；docs 与 CLI 语义一致；Product Shell 只读事实不回退。 |
| **M1 Signal Observability** | 新增 `.aiwiki/state/signals.jsonl` 与 `.aiwiki/state/planner-log.jsonl`，从 runtime-history / receipts 归一化 signal。 | `mode` 只能是 `observe_only`；不得触发 phase。 | signal schema fixture、dedupe replay、trace 回链、坏 schema fail-fast。 |
| **M2 Elixir Candidate Plane** | 新增 `output/_candidates/elixirs/`、candidate frontmatter、promote/demote/revert receipt。 | 不强制迁移旧 `wiki/elixirs/`；不绕过 DAG / provenance gate。 | promote hash gate、revert clean/stale 分支、DAG 环路拒绝、路径穿越拒绝。 |
| **M3 L3 Proposal** | 新增 prompt/policy proposal kind，支持手工/fixture 创建、execute-mode deterministic candidate generation、review、apply、revert。 | 不自动 accept proposal；不写 `src/aiwiki/**`、schema core 或 protocol core；不以 LLM 结果作为默认生成内容。 | before_hash mismatch 退为 stale；receipt 可 clean revert；冲突生成 human_merge_required；generation idempotent 且不触碰目标文件。 |
| **M4 Heavy/Light Dry-run Wrapper** | `alchemy heavy/light --dry-run` 只计算 signal scope、primitive plan、预算与锁结果。 | 默认不 execute；light 不升级 heavy；全量 heavy 不自动授权。 | scope preview 稳定；预算超限可解释；锁冲突 skip；primitive plan 可复现。 |
| **M5 Controlled Execution** | heavy/light 允许显式 `--apply` 组合 scoped primitives。 | 不允许 hidden backend choice；不允许无 receipt 写回。 | 每个 phase 有 trace_id、receipt、audit entry；失败可从上一稳定点恢复。 |

M5 当前收敛状态：`--apply --action-id` 只桥接既有 receipted low-risk action batch；`--apply --primitive` 只支持 dry-run step 明确 `apply_supported=true` 的 `compile/lint/nightly/review` receipts，其中 `review` 仅限 heavy lane 显式 apply。任一 lane `--apply` 必须先得到 `status=ok` 且 `selected_count>0` 的 dry-run preview；非 `ok` preview 会在 action bridge 或 primitive implementation 调用前 abort，且不会写 lane start/complete runtime history。显式 lane apply 成功路径会写 `alchemy-lane-started / alchemy-lane-completed` runtime-history events，并通过 runtime-history direct append 进入 universal audit stream。lane primitive receipt 顶层已暴露 planner trace 与 execution receipt history audit metadata。`alchemy auto` 已提供 execute-mode deterministic scheduler consumption，但不选择或执行 `review`；L3 proposal generation 已通过独立 `l3-proposal-generate` baseline 承接。`judge/distill/propose` 仍只有 scoped dry-run preview 与 deferred apply contract metadata，直到各自拥有 executable scoped primitive apply contract。

M3 当前收敛状态：manual baseline 已支持 `l3-proposal-create`、`review proposals`、`review proposal-generation` candidate preview、`l3-proposal-generate --dry-run|--apply` execute-mode deterministic candidate generation、`shell-status` 的 `review_controls.l3_proposals`、`review proposal <proposal-id> --status rejected`、`apply <proposal-id>` 与 `revert <receipt-id>`；写回范围限定为 `prompts/*.md` 与 `schema/policies/*`。`l3-proposal-generate --apply` 只消费 `mode=execute` 且含 `proposal_recommended` 的 planner-log `generate-proposal` records，写 `output/_proposals/prompt/` 与 `.aiwiki/state/l3-proposals.json`，并通过 runtime history / universal audit 暴露创建事件；observe-only records 只在 preview 中标为 blocked。`reject` 只更新 proposal state/page 与 runtime history，不写目标文件、不生成 apply receipt；runtime history 写入会同步 append universal audit record。`apply` 必须通过 proposal `before_hash`，失败时 proposal 转 `stale` 且不写目标；`revert` 必须通过 receipt `after_hash`，失败时转 `revert_conflict` 并生成 `human_merge_required` hint。L3 apply/revert receipt 顶层暴露 `audit_stream=execution_receipts`、`audit_event=execution_receipt_history_append`、`audit_path=.aiwiki/state/execution-receipts.jsonl`。自动 generation 不调用 LLM、不写 target、不自动 accept；通用 audit stream 已有 preview/backfill 与 execution receipt/runtime history/LLM receipt/protocol-learning aging direct append baseline。

达到 9+ 可行性的条件不是“自动化更多”，而是每个 milestone 都满足：可重放、可 dry-run、可回滚、可停用、可用现有 gate 验证。

### 12.5 Stop Lines and Kill Switches

- Signal replay 不能稳定去重时，planner 停留在 `observe_only`。
- 任一 proposal / candidate 无法产生 clean receipt 时，不允许进入默认 apply。
- M2 `elixir promote` 属于 in-process 不可逆操作；未生成 `elixir_promotion` clean receipt 前，不允许进入默认 apply（`elixir_demotion / elixir_revert` 同理需 receipt）。
- `M2.2` `alchemy-finalize` 属于 candidate plane 内可逆操作，不要求 receipt；但若执行失败，必须保证 candidate 文件不出现半写状态。
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
