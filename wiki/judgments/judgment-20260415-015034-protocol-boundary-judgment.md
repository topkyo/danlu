---
id: "judgment-20260415-015034-protocol-boundary-judgment"
kind: "judgment"
status: "confirmed"
title: "Protocol Boundary Judgment"
protocol: "research"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-015034-when-should-an-agent-runtime-adopt-mcp-or-a2a-as.md"
citations:
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md"
  - "wiki/sources/discovered-20260408053358-item.md"
citation_snapshots:
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md#15a70e40147aed0ee77ce053915876b92f24391a6a49eea4b580f7f5a3c5f3a5"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T01:50:34+00:00"
confidence: "medium"
counter_evidence:
  - "Single-runtime agents with one tool registry can stay simpler by keeping function calls and state transitions in-process."
  - "Explicit protocols can add latency and schema overhead before multi-system interoperability is needed."
invalidation_rule: "If the corpus shows mature multi-agent systems outperforming protocolized stacks while staying monolithic and auditable, demote this judgment."
next_signals:
  - "Watch whether MCP becomes the default tool boundary for local-first runtimes."
  - "Watch whether A2A adoption concentrates only in cross-service agent swarms instead of local orchestrators."
formed_at: "2026-04-15T01:50:34+00:00"
last_reviewed: "2026-04-15T01:51:03+00:00"
reviewed_at: "2026-04-15T01:51:03+00:00"
revisit_after: ""
escalate_after: ""
---

# Protocol Boundary Judgment

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-015034-when-should-an-agent-runtime-adopt-mcp-or-a2a-as.md`
- Filed at: `2026-04-15T01:50:34+00:00`
- Protocol: `research`

## Judgment
- MCP or A2A boundaries become worth the cost when an agent runtime must coordinate heterogeneous tools, multiple executors, or external agents with explicit contracts.

## Supporting Evidence
- `model-context-protocol-introduction` frames MCP as a stable interface between models and tools.
- `a2a-key-concepts` focuses on agent-to-agent contract surfaces, which matters once execution crosses service or ownership boundaries.
- `building-effective-agents` and the local runtime notes both imply that protocol seams matter most when reuse, audit, and interoperability outrun prompt-only composition.

## Counter Evidence
- Adding protocol layers too early can slow down a local-first stack that still has one writer and one execution surface.
- In-process tools with strong type contracts may not need a network-oriented agent boundary.

## Open Questions
- Where is the actual break point between a typed local adapter and a full protocol boundary?
- Which protocol surface should stay inside the runtime contract, and which should remain external integration glue?

## Confidence And Next Experiment
- Confidence is medium because the corpus supports protocolization, but the local runtime still runs effectively as a single-writer file system.
- Next experiment: compare the overhead of direct adapters versus MCP/A2A shims for the same tool and agent workflows.

## Counter Evidence
- Small local deployments may lose simplicity faster than they gain interoperability.
- Some frameworks may expose protocol adapters mainly for ecosystem growth rather than runtime necessity.

## Invalidation
- Invalidate if direct local adapters consistently deliver the same auditability and portability as protocolized boundaries across new sources.

## Signals
- `wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md` frames MCP as a stable model-tool boundary, which is a direct signal that protocol seams become useful when tools and executors diversify.
- `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` and `wiki/sources/discovered-20260415013128-building-effective-agents.md` both point to explicit contracts once agents cross service or ownership boundaries, while the local runtime still shows a simpler in-process path.

## Next Signals
- Track whether future sources describe protocol boundaries as required for safety-critical workflows.
- Track whether the local runtime starts crossing process or ownership boundaries often enough to justify a stricter contract seam.

## Review Status
- Current status: `confirmed`
- Reviewed at: `2026-04-15T01:51:03+00:00`
- Confidence: `medium`

## Review Notes
- Outcome: `confirmed`
- Reviewed at: `2026-04-15T01:51:03+00:00`
- Note: Protocol boundaries are warranted when interoperability is explicit.

## Review History
- `2026-04-15T01:51:03+00:00` | status `confirmed` | confidence `medium` | note Protocol boundaries are warranted when interoperability is explicit.

## Supporting Artifact
# When should an agent runtime adopt MCP or A2A as explicit protocol boundaries?

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
- 命中词：`when, should, agent, runtime, a2a, protocol`
- 路由策略：`source-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013128-building-effective-agents, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260415013529-a2a-key-concepts, discovered-20260408053946-item, discovered-20260415013329-react-paper-abstract, discovered-20260408053358-item, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013427-toolformer-paper-abstract`
- 提升权重的概念：`and, agent, a2a, decision, protocol, the, url, a2a-key-concepts`
- 协议 shard 来源：`discovered-20260415013329-react-paper-abstract, discovered-20260415013427-toolformer-paper-abstract, discovered-20260415013427-voyager-paper-abstract`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, agent, decision, protocol, the, url`
- 查询子图边数：`26`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-url` / `拆分过载概念 Url` / score `56`

## 推荐概念
- [Url](../../wiki/concepts/url.md)
- [And](../../wiki/concepts/and.md)
- [The](../../wiki/concepts/the.md)
- [Agents](../../wiki/concepts/agents.md)
- [A2a](../../wiki/concepts/a2a.md)

## 推荐来源
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [AutoGen Multi Agent Debate Pattern](../../wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)
- [A2A Key Concepts](../../wiki/sources/discovered-20260415013529-a2a-key-concepts.md)
- [炼丹炉场景路线图](../../wiki/sources/discovered-20260408053358-item.md)

## 草稿提纲
1. 重新表述研究问题。
2. 按当前协议优先组织最相关来源和概念。
3. 写出分歧、证据缺口和下一步问题。

## 引用要求
- 在最终答案里加入 source-page 内联引用。

## Aging
- Revisit after: `none`
- Escalate after: `none`
