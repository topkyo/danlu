---
id: "decision-20260415-015034-agent-governance-decision"
kind: "decision"
status: "approved"
title: "Agent Governance Decision"
protocol: "research"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-015034-what-governance-and-failure-mode-controls-are-re.md"
citations:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md"
  - "wiki/sources/discovered-20260408053358-item.md"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md"
citation_snapshots:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md#bbb5de6cff747a0a40dd1112ecbdd76a9e57c06d85802e72a14f88e8a35d44f8"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md#1dff29c2fbe8e43e72cfb1e136f75f40e8a682ad0df9c2f25b69eff028adbded"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T01:50:34+00:00"
confidence: "high"
counter_evidence:
  - "Lightweight read-only research workflows may only need provenance and not a full review/repair loop."
  - "Too much governance can slow iteration if every action is treated as high risk."
invalidation_rule: "Revisit this decision if the runtime shows sustained low-risk operation without needing repair backlog, review queue, or execution receipts."
next_signals:
  - "Track how often nightly produces actionable governance items."
  - "Track whether safe-apply/revert flows reduce rollback time for operator-facing repairs."
formed_at: "2026-04-15T01:50:34+00:00"
last_reviewed: "2026-04-15T01:53:07+00:00"
reviewed_at: "2026-04-15T01:53:07+00:00"
revisit_after: ""
escalate_after: ""
---

# Agent Governance Decision

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-015034-what-governance-and-failure-mode-controls-are-re.md`
- Filed at: `2026-04-15T01:50:34+00:00`
- Protocol: `research`

## Decision
- Adopt governance-by-default for any workflow that writes judgments, decisions, machine-memory actions, or reversible execution artifacts.

## Affected Surface
- Review queue, aging report, repair backlog, execution-center, execution-audit, and filed-back judgment/decision workflows.
- Operator handoff paths that depend on explicit status, revisit windows, and rollbackability.

## Evidence
- The current corpus ties multi-agent coordination to replay, audit, and recovery concerns.
- The local runtime already contains governance surfaces; using them on real pages demonstrates they are not dead scaffolding.

## Validation Plan
- Validate by confirming that nightly surfaces real pending work, aging catches stale judgments, and revert paths remain usable after safe apply.
- Monitor whether governance metadata stays explicit on every new judgment and decision.

## Rollback And Risks
- Main risk: governance overhead outruns the actual autonomy or mutation risk of the runtime.
- Roll back by narrowing governance requirements to stateful or high-risk execution paths only.

## Counter Evidence
- Low-risk informational outputs may not need the same governance burden as stateful repairs.
- Small teams may prefer lighter-weight review loops until automation expands.

## Invalidation
- Invalidate if the corpus and runtime history show that governance surfaces stay mostly empty even under real agent activity.

## Next Signals
- Watch whether repair backlog and review queue continue to fill with actionable items from real corpus changes.
- Watch whether execution receipts and revert flows remain necessary once the runtime stabilizes.

## Review Status
- Current status: `approved`
- Reviewed at: `2026-04-15T01:53:07+00:00`

## Review Notes
- Outcome: `approved`
- Reviewed at: `2026-04-15T01:53:07+00:00`
- Note: Governance-by-default is justified for stateful agent workflows.

## Review History
- `2026-04-15T01:53:07+00:00` | status `approved` | note Governance-by-default is justified for stateful agent workflows.

## Supporting Artifact
# What governance and failure-mode controls are required for multi-agent systems?

## 回答约束
- 所有重要结论都要落回 `wiki/sources/*.md`。
- 有不确定性就直接写出来，不要补洞。
- 优先使用文件路径引用，而不是模糊转述。
- 当前协议：`research` (研发协议)。

## 协议输出偏置
- 优先组织成 benchmark / experiment / tradeoff / regression risk / next experiment。
- 把 open questions 和验证条件写清楚。

## 推荐索引页
- [知识库总索引](../../wiki/indexes/index.md)
- [来源索引](../../wiki/indexes/sources.md)
- [概念索引](../../wiki/indexes/concepts.md)
- [决策索引](../../wiki/indexes/decisions.md)
- [判断索引](../../wiki/indexes/judgments.md)
- [判断资产](../../wiki/indexes/judgment-assets.md)
- [Agent Workbench](../../wiki/indexes/agent-workbench.md)
- [认知历史](../../wiki/indexes/cognitive-history.md)
- [输出 Pack 总览](../../wiki/indexes/output-packs.md)
- [领域 Pilot 总览](../../wiki/indexes/domain-pilots.md)
- [协议总览](../../wiki/indexes/protocols.md)
- [审阅队列](../../wiki/indexes/review-queue.md)
- [审阅中心](../../wiki/indexes/review-center.md)
- [Aging 报告](../../wiki/indexes/aging-report.md)
- [概念质量](../../wiki/indexes/concept-quality.md)
- [机器记忆](../../wiki/indexes/machine-memory.md)
- [图谱视图](../../wiki/indexes/graph-view.md)
- [拓扑视图](../../wiki/indexes/machine-memory-topology.md)
- [动作队列](../../wiki/indexes/machine-memory-actions.md)
- [修复计划](../../wiki/indexes/machine-memory-repair-plan.md)
- [图谱健康](../../wiki/indexes/graph-health.md)
- [漂移报告](../../wiki/indexes/drift-report.md)
- [修复待办](../../wiki/indexes/repair-backlog.md)
- [运行时规则](../../schema/index.md)
- [当前协议规则](../../schema/protocols/research/index.md)

## 机器记忆查询计划
- 命中词：`and, mode, are, for, multi, agent, systems`
- 路由策略：`source-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260415013128-building-effective-agents, discovered-20260415013329-react-paper-abstract, discovered-20260408053358-item, discovered-20260415013427-toolformer-paper-abstract, discovered-20260415013427-voyager-paper-abstract, discovered-20260415013334-anthropic-tool-use-overview, discovered-20260415013612-crewai-agents-concept`
- 提升权重的概念：`and, autogen-multi-agent, agent, url, agents, the, abstract, overview`
- 协议 shard 来源：`discovered-20260415013329-react-paper-abstract, discovered-20260415013427-toolformer-paper-abstract, discovered-20260415013427-voyager-paper-abstract`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, agent, url, agents, the, abstract, overview`
- 查询子图边数：`30`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-url` / `拆分过载概念 Url` / score `56`

## 推荐概念
- [And](../../wiki/concepts/and.md)
- [The](../../wiki/concepts/the.md)
- [Agents](../../wiki/concepts/agents.md)
- [Agent](../../wiki/concepts/agent.md)
- [Autogen Multi Agent](../../wiki/concepts/autogen-multi-agent.md)

## 推荐来源
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [AutoGen Multi Agent Debate Pattern](../../wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)
- [ReAct Paper Abstract](../../wiki/sources/discovered-20260415013329-react-paper-abstract.md)
- [炼丹炉场景路线图](../../wiki/sources/discovered-20260408053358-item.md)
- [CrewAI Agents Concept](../../wiki/sources/discovered-20260415013612-crewai-agents-concept.md)

## 草稿提纲
1. 重新表述研究问题。
2. 按当前协议优先组织最相关来源和概念。
3. 写出分歧、证据缺口和下一步问题。

## 引用要求
- 在最终答案里加入 source-page 内联引用。

## Aging
- Revisit after: `none`
- Escalate after: `none`
