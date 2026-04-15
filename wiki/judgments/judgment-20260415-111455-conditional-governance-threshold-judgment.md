---
id: "judgment-20260415-111455-conditional-governance-threshold-judgment"
kind: "judgment"
status: "confirmed"
title: "Conditional Governance Threshold Judgment"
protocol: "research"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-111455-when-should-keep-protocol-and-governance-layers-.md"
citations:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md"
  - "wiki/sources/discovered-20260408053946-item.md"
citation_snapshots:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md#6f37eed9d8925f266f552b166f7fbb0694744b86ec602627531bb08000f36390"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md#15a70e40147aed0ee77ce053915876b92f24391a6a49eea4b580f7f5a3c5f3a5"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md#754b5d075b848d947436f47246cf5c7f7428b7695d4a8dec616bab1c16fa72c6"
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T11:14:55+00:00"
confidence: "medium"
counter_evidence:
  - "If integrations are about to cross process or ownership boundaries, delaying protocol seams can create migration debt."
  - "Receipt and review surfaces can add operator value before formal MCP or A2A adoption is visible in the corpus."
invalidation_rule: "If new corpus evidence shows protocol and governance layers consistently improving local-first runtimes before shared-state, multi-executor, or ownership boundaries appear, invalidate this threshold judgment."
next_signals:
  - "Track whether new aiwiki integrations stay in-process or start crossing process and ownership boundaries."
  - "Track whether review receipts and rollback paths improve operator recovery before multi-executor coordination appears."
related_judgments:
  - "wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md"
  - "wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md"
formed_at: "2026-04-15T11:14:55+00:00"
last_reviewed: "2026-04-15T11:22:01+00:00"
reviewed_at: "2026-04-15T11:22:01+00:00"
revisit_after: ""
escalate_after: ""
---

# Conditional Governance Threshold Judgment

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-111455-when-should-keep-protocol-and-governance-layers-.md`
- Filed at: `2026-04-15T11:14:55+00:00`
- Protocol: `research`

## Research Judgment
- Protocol and governance layers should stay conditional until the runtime crosses a concrete threshold: shared mutable state, multi-executor coordination, or external ownership boundaries. Before that threshold, typed in-process adapters and explicit provenance can keep the system simpler without losing the ability to evolve later.

## Supporting Evidence
- `wiki/sources/discovered-20260415013128-building-effective-agents.md` repeatedly argues for starting from the simplest workflow that can still be evaluated, which supports keeping governance proportional to actual execution power.
- `wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md` and `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` justify explicit contracts once tools, agents, or service boundaries diversify; they do not prove those layers should be mandatory inside a still-local single-writer runtime.
- `wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md` is direct counter-evidence that early protocol and governance seams can become ceremony when one runtime still owns the tool registry, state store, and execution policy.
- `wiki/sources/discovered-20260408053946-item.md` reinforces the same boundary from the local design side: keep one shared core, and move variability into protocol-specific workflows instead of prematurely multiplying base runtime layers.

## Counter Evidence
- Once the runtime starts coordinating heterogeneous tools, background executors, or external agents, retrofitting protocol seams later could be more expensive than introducing them earlier.
- Review queues, receipts, and rollback controls can become useful before network protocols appear if state mutation frequency rises inside a single runtime.

## Open Questions
- What is the smallest measurable threshold that should flip aiwiki from typed local adapters to explicit protocol boundaries?
- Which governance surfaces should trigger on shared-state mutation alone, and which should wait for multi-actor execution?

## Confidence And Next Experiment
- Confidence is medium because the corpus now contains both a strong case for explicit boundaries and an explicit local counterpoint that narrows when those boundaries pay off.
- Next experiment: compare one new integration implemented as a typed in-process adapter versus a protocolized seam, then measure operator complexity, receipt usefulness, and replay quality.
- Default revisit window: `2026-04-19T11:14:55+00:00`
- Default escalation window: `2026-04-25T11:14:55+00:00`

## Counter Evidence
- Early protocolization may still be cheaper if upcoming integrations are known to cross process or ownership boundaries.
- Governance controls can create real leverage before protocolization if mutation risk rises faster than interface complexity.

## Invalidation
- Invalidate if new corpus evidence shows protocol and governance layers consistently improving local-first runtimes before shared-state, multi-executor, or ownership boundaries appear.

## Next Signals
- Track whether new aiwiki integrations stay in-process or start crossing process and ownership boundaries.
- Track whether review receipts and rollback paths improve operator recovery before multi-executor coordination appears.
- Default revisit window: `2026-04-19T11:14:55+00:00`
- Default escalation window: `2026-04-25T11:14:55+00:00`

## Related Judgments
- This judgment narrows [Protocol Boundary Judgment](./judgment-20260415-015034-protocol-boundary-judgment.md): protocol seams are valuable, but only after the runtime crosses a concrete interoperability threshold.
- It also scopes [Agent Governance Judgment](./judgment-20260415-015034-agent-governance-judgment.md): governance should rise with mutation and coordination risk rather than run at maximum strength from day one.

## Review Status
- Current status: `confirmed`
- Reviewed at: `2026-04-15T11:22:01+00:00`
- Confidence: `medium`

## Review Notes
- Outcome: `confirmed`
- Reviewed at: `2026-04-15T11:22:01+00:00`
- Note: Threshold applies once the runtime crosses shared-state or interoperability boundaries.

## Review History
- `2026-04-15T11:22:01+00:00` | status `confirmed` | confidence `medium` | note Threshold applies once the runtime crosses shared-state or interoperability boundaries.
- `2026-04-15T11:21:22+00:00` | status `confirmed` | confidence `medium` | note Threshold applies once the runtime crosses shared-state or interoperability boundaries.

## Supporting Artifact
# When should 炼丹炉 keep protocol and governance layers conditional instead of always-on?

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
- 命中词：`when, should, keep, protocol, and, governance, layers, instead, always`
- 路由策略：`source-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415015403-protocol-overhead-counterpoint, discovered-20260415013529-a2a-key-concepts, discovered-20260415013128-building-effective-agents, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013612-crewai-agents-concept, discovered-20260415013329-react-paper-abstract, discovered-20260415013427-voyager-paper-abstract, discovered-20260415013427-toolformer-paper-abstract`
- 提升权重的概念：`the, and, protocol, model-context-protocol, abstract, agents, concepts, judgment`
- 协议 shard 来源：`discovered-20260415013329-react-paper-abstract, discovered-20260415013427-voyager-paper-abstract, discovered-20260415013427-toolformer-paper-abstract`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`the, and, protocol, abstract, agents, concepts, judgment`
- 查询子图边数：`38`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-and` / `拆分过载概念 And` / score `78`

## 推荐概念
- [Protocol](../../wiki/concepts/protocol.md)
- [The](../../wiki/concepts/the.md)
- [Model Context Protocol](../../wiki/concepts/model-context-protocol.md)
- [And](../../wiki/concepts/and.md)
- [Judgment](../../wiki/concepts/judgment.md)

## 推荐来源
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [Protocol Overhead Counterpoint](../../wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md)
- [Model Context Protocol Introduction](../../wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md)
- [A2A Key Concepts](../../wiki/sources/discovered-20260415013529-a2a-key-concepts.md)
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)

## 草稿提纲
1. 重新表述研究问题。
2. 按当前协议优先组织最相关来源和概念。
3. 写出分歧、证据缺口和下一步问题。

## 引用要求
- 在最终答案里加入 source-page 内联引用。

## Aging
- Revisit after: `none`
- Escalate after: `none`
