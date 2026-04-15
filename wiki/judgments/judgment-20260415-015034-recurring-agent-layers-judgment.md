---
id: "judgment-20260415-015034-recurring-agent-layers-judgment"
kind: "judgment"
status: "confirmed"
title: "Recurring Agent Layers Judgment"
protocol: "research"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-015034-which-architecture-layers-recur-across-modern-ll.md"
citations:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md"
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260408053358-item.md"
citation_snapshots:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md#1dff29c2fbe8e43e72cfb1e136f75f40e8a682ad0df9c2f25b69eff028adbded"
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T01:50:34+00:00"
confidence: "high"
counter_evidence:
  - "Small single-purpose agents can keep planning, tool calls, and state in one local loop without explicit layered boundaries."
  - "Research prototypes often postpone governance and review surfaces until execution risk becomes material."
invalidation_rule: "If new corpus evidence shows better operator leverage from monolithic agent stacks without explicit tool/state/governance separation, downgrade this judgment."
next_signals:
  - "Track whether MCP or A2A become default interoperability seams rather than optional integrations."
  - "Watch whether production agent frameworks keep adding audit, review, and replay surfaces around execution."
formed_at: "2026-04-15T01:50:34+00:00"
last_reviewed: "2026-04-15T12:39:25+00:00"
reviewed_at: "2026-04-15T12:39:25+00:00"
revisit_after: ""
escalate_after: ""
---

# Recurring Agent Layers Judgment

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-015034-which-architecture-layers-recur-across-modern-ll.md`
- Filed at: `2026-04-15T01:50:34+00:00`
- Protocol: `research`

## Judgment
- Modern agent stacks repeatedly separate five responsibilities: planning/policy, tool execution, memory/state, protocol boundaries, and operator governance.

## Supporting Evidence
- `building-effective-agents` describes orchestration, tool use, and evaluation as distinct operational concerns rather than one fused loop.
- `autogen-multi-agent-debate-pattern` shows role-specialized agents coordinating through an explicit interaction pattern instead of a single prompt chain.
- `crewai-agents-concept` and the local architecture notes both emphasize durable state, role separation, and replayable coordination.

## Counter Evidence
- Small local agents can still be effective with one process, one memory store, and no explicit protocol bridge.
- Early-stage research loops may gain speed from collapsing governance into manual operator judgment.

## Open Questions
- Which layer split delivers the highest leverage first: protocol boundaries, memory durability, or governance?
- At what point does a local-first runtime need cross-process standards rather than repo-local conventions?

## Confidence And Next Experiment
- Confidence is high because Anthropic, AutoGen, CrewAI, and the local runtime all converge on similar functional seams.
- Next experiment: compare a monolithic single-agent loop against the current layered runtime on auditability, replay, and repair latency.

## Counter Evidence
- Monolithic assistants may still outperform layered runtimes for narrow one-shot tasks.
- Additional corpus items could show that protocol layers add coordination cost before scale warrants them.

## Invalidation
- Invalidate if the next tranche of sources shows strong multi-tool systems succeeding without durable memory, explicit protocols, or governance controls.

## Signals
- `wiki/sources/discovered-20260415013128-building-effective-agents.md`, `wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md`, and `wiki/sources/discovered-20260415013612-crewai-agents-concept.md` all separate orchestration, tool use, and coordination concerns instead of collapsing them into one prompt loop.
- `wiki/sources/discovered-20260408053946-item.md` and `wiki/sources/discovered-20260408053358-item.md` show protocol and governance seams becoming more valuable as a runtime grows beyond a single local execution path.

## Next Signals
- Track whether newly added frameworks expose audit/review surfaces by default.
- Track whether A2A/MCP style boundaries move from optional adapters to core runtime assumptions.

## Review Status
- Current status: `confirmed`
- Reviewed at: `2026-04-15T12:39:25+00:00`
- Confidence: `high`

## Review Notes
- Outcome: `confirmed`
- Reviewed at: `2026-04-15T12:39:25+00:00`
- Note: Escalation re-review closed after governance pressure test.

## Review History
- `2026-04-15T12:39:25+00:00` | status `confirmed` | confidence `high` | note Escalation re-review closed after governance pressure test.
- `2026-04-15T01:51:03+00:00` | status `confirmed` | confidence `high` | note Cross-framework layer pattern is consistent in the corpus.
- `2026-04-15T01:50:34+00:00` | status `confirmed` | confidence `high` | note Cross-framework layer pattern is consistent in the corpus.

## Supporting Artifact
# Which architecture layers recur across modern LLM agent frameworks?

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
- 命中词：`which, architecture, across, llm, agent, frameworks`
- 路由策略：`source-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013128-building-effective-agents, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260408053358-item, discovered-20260415013329-react-paper-abstract, discovered-20260408053946-item`
- 提升权重的概念：`and, agent, the, autogen-multi-agent, decision, debate, judgment, abstract`
- 协议 shard 来源：`discovered-20260415013329-react-paper-abstract`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, agent, the, decision, abstract`
- 查询子图边数：`25`
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
- [炼丹炉场景路线图](../../wiki/sources/discovered-20260408053358-item.md)
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)
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
