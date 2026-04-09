---
title: "炼丹炉原料状态模型"
kind: "design"
status: "active"
---

# 炼丹炉原料状态模型

这份文档不是新的架构层，而是对 [[wiki/indexes/Furnace Material Scaling|大规模原料处理设计]] 的进一步收敛：

**把 `temperature / active corpus / archive` 压成更接近 runtime 的最小状态模型。**

它仍然不是“当前已经实现”的说明，而是后续实现时应优先遵守的 schema 基线。

对应关系：

- 基线架构：[[wiki/indexes/Alchemy Furnace|炼丹炉架构]]
- 规模化设计：[[wiki/indexes/Furnace Material Scaling|大规模原料处理设计]]
- 终局形态：[[wiki/indexes/Furnace Ultimate Architecture|炼丹炉最终极形态]]

## 目标

这份状态模型希望回答 4 个问题：

1. evidence temperature 应该记录在哪，至少包含哪些字段。
2. active corpus 应该如何持久化，如何被 query / nightly / review 复用。
3. archive / reactivation 应该如何表达，而不是只停留在口头概念。
4. protocol-aware routing 的最小分数结构应该是什么。

## 先分两张状态面

后续实现里，至少要显式区分两张状态面：

### 1. Evidence State Plane

面向：

- `raw/`
- 附件
- capture notes
- source-level evidence

负责：

- `temperature`
- 进入/退出 active corpus
- archive candidate
- reactivation candidate
- protocol routing score

### 2. Knowledge Lifecycle Plane

面向：

- `wiki/concepts`
- `wiki/decisions`
- `wiki/judgments`

负责：

- `active / review / deferred / retired / revisit`
- judgment invalidation
- review window
- escalation

这两张状态面可以互相引用，但不能混成同一套字段。

## 建议的状态文件

如果后续实现，建议优先落在：

- `.aiwiki/state/material-state.json`
- `.aiwiki/state/active-corpora.json`
- `.aiwiki/state/archive-candidates.json`
- `.aiwiki/state/material-routing.json`

原因：

- 都属于 machine-readable runtime state
- 都应可由 `raw/ + wiki/ + machine memory` 增量重建
- 不该污染 `raw/` 或 `wiki/` 本身

## 1. Material State

最小单元：一条 evidence / source 级状态记录。

建议字段：

```json
{
  "material_id": "src-20260409-abc123",
  "path": "raw/inbox/example.md",
  "kind": "raw_note",
  "source_type": "web",
  "protocol_hints": ["research", "investing"],
  "temperature": "hot",
  "last_touched_at": "2026-04-09T12:00:00+08:00",
  "last_query_hit_at": "2026-04-09T12:10:00+08:00",
  "last_review_reference_at": "2026-04-09T12:20:00+08:00",
  "citation_count": 3,
  "supports_judgment_ids": ["judgment-foo"],
  "active_corpus_ids": ["research-transformer-scaling"],
  "archive_candidate": false
}
```

说明：

- `material_id`
  - 稳定 ID，不直接依赖 path
- `protocol_hints`
  - 表示该材料天然更贴近哪些协议，但不是硬隔离
- `temperature`
  - 只表达 evidence 热度，不表达 knowledge lifecycle
- `supports_judgment_ids`
  - 把 evidence 和 judgment 层关联起来，但不混状态机
- `active_corpus_ids`
  - 记录当前被哪些工作集显式点亮

## 2. Active Corpus

最小单元：一次 query / review / nightly 所围绕的活动工作集。

建议字段：

```json
{
  "corpus_id": "research-transformer-scaling",
  "protocol": "research",
  "focus_kind": "question",
  "focus_ref": "Compare scaling laws and inference-time compute",
  "question_hash": "sha256:...",
  "source_ids": ["src-1", "src-2"],
  "concept_slugs": ["transformer", "scaling-law"],
  "bridge_evidence_ids": ["src-bridge-1"],
  "output_refs": ["output/reports/report-123.md"],
  "status": "active",
  "created_at": "2026-04-09T12:00:00+08:00",
  "last_used_at": "2026-04-09T12:15:00+08:00",
  "expires_at": "2026-04-12T12:00:00+08:00"
}
```

说明：

- `focus_kind`
  - 例如 `question / review / nightly / judgment`
- `bridge_evidence_ids`
  - 显式记录跨协议召回的证据
- `status`
  - 只描述工作集当前是否活跃，不描述 evidence/knowledge 生命周期
- `expires_at`
  - 允许工作集自然降温，而不是永久留在 active

## 3. Archive Candidate

最小单元：一条被系统建议降温或归档的 evidence 状态。

建议字段：

```json
{
  "material_id": "src-20260409-abc123",
  "current_temperature": "warm",
  "recommended_temperature": "cold",
  "reason_codes": ["stale-no-query-hit", "no-active-corpus"],
  "first_flagged_at": "2026-04-09T13:00:00+08:00",
  "last_flagged_at": "2026-04-10T13:00:00+08:00",
  "blocked_by_judgment_ids": [],
  "reactivation_signals": []
}
```

说明：

- `reason_codes`
  - 用可枚举 code，不只写自然语言
- `blocked_by_judgment_ids`
  - 如果仍支撑 active judgment，就不能直接降温/归档
- `reactivation_signals`
  - 后续被召回时写回原因

## 4. Material Routing

最小单元：某条材料在某个协议/问题下的路由分数快照。

建议字段：

```json
{
  "material_id": "src-20260409-abc123",
  "protocol": "research",
  "scores": {
    "protocol_score": 0.9,
    "graph_score": 0.7,
    "judgment_score": 0.6,
    "recency_score": 0.8,
    "drift_score": 0.2
  },
  "total_score": 3.2,
  "selected_as": "hot-evidence",
  "is_bridge": false,
  "computed_at": "2026-04-09T12:30:00+08:00"
}
```

说明：

- `protocol_score`
  - 当前 active protocol 的偏置分
- `graph_score`
  - graph neighborhood / machine memory 的相关性分
- `judgment_score`
  - 与 active `decision / judgment` 的绑定强度
- `recency_score`
  - 最近活跃度
- `drift_score`
  - 漂移/复审压力
- `is_bridge`
  - 是否作为跨协议 bridge evidence 进入当前工作集

## 最小状态转换规则

### Evidence Temperature

建议先只允许这些转换：

- `hot -> warm`
- `warm -> cold`
- `cold -> hot`
- `warm -> hot`
- `cold -> archived`
- `archived -> cold`

不建议一开始支持：

- 复杂多跳自动转换
- 批量无审计变更
- 同一轮 compile 里反复震荡

### Active Corpus

建议先只支持：

- `active`
- `cooling`
- `expired`

并遵循：

- query 命中会刷新 `last_used_at`
- nightly 可把 `active -> cooling`
- 超过 `expires_at` 可转 `expired`
- 被重新命中时允许 `expired -> active`

### Archive Candidate

建议先只支持：

- `suggested`
- `deferred`
- `ready`
- `reactivated`

这样可以避免一开始把“降温建议”直接做成自动归档执行。

## 不该放进这个状态模型的内容

以下内容不应塞进 material state：

- concept summary 本文
- judgment/decision 审阅结果
- 执行层 receipt
- protocol 模板本身
- 只给人看的 narrative 说明

这些应继续留在：

- `wiki/`
- `output/`
- `schema/`
- `.aiwiki/state/` 的其它专用文件

## 第一版落地顺序

如果未来把这份状态模型真正接进 runtime，建议按这个顺序：

1. `material-state.json`
2. `active-corpora.json`
3. `material-routing.json`
4. `archive-candidates.json`

原因：

- 先有温度和工作集，query / nightly 才有真正的运行面
- routing 分数其次，因为它依赖前两者
- archive candidate 最后补，避免一开始就把“归档”做得过重

## 结论

规模化设计回答的是“方向”；这份状态模型回答的是“后续实现时，状态该怎么落”。

最关键的约束仍然是：

- evidence temperature 和 knowledge lifecycle 分开
- 当前协议优先，但跨协议证据可召回
- machine memory 负责窄化入口，不让 LLM直接面对大库
- 所有状态都优先进入 `.aiwiki/state/`，而不是污染 `raw/` 或 `wiki/`
