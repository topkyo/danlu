---
id: "decision-20260415-111456-investing-protocol-decision"
kind: "decision"
status: "approved"
title: "Investing Protocol Decision"
protocol: "investing"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-111456-should-ship-investing-as-a-first-class-protocol--decision-memo.md"
citations:
  - "wiki/sources/discovered-20260408053358-item.md"
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
citation_snapshots:
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md#6f37eed9d8925f266f552b166f7fbb0694744b86ec602627531bb08000f36390"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md#754b5d075b848d947436f47246cf5c7f7428b7695d4a8dec616bab1c16fa72c6"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md#15a70e40147aed0ee77ce053915876b92f24391a6a49eea4b580f7f5a3c5f3a5"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T11:14:56+00:00"
confidence: "medium"
counter_evidence:
  - "The investing corpus may stay too small to justify dedicated protocol templates and review windows."
  - "Operators may prefer lightweight notes until the first real thesis-revision loop proves the workflow is worth the overhead."
invalidation_rule: "Reconsider this decision if investing workflows fail to reuse judgment, review, and revisit surfaces in real operator practice."
next_signals:
  - "Track whether new investing materials naturally map into thesis, catalyst, risk, invalidation, and position-decision fields."
  - "Track whether earnings-style reviews reopen prior investing judgments instead of creating disconnected notes."
supports:
  - "wiki/judgments/judgment-20260415-111456-investing-layer-separation-judgment.md"
formed_at: "2026-04-15T11:14:56+00:00"
last_reviewed: "2026-04-15T11:22:02+00:00"
reviewed_at: "2026-04-15T11:22:02+00:00"
revisit_after: ""
escalate_after: ""
---

# Investing Protocol Decision

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-111456-should-ship-investing-as-a-first-class-protocol--decision-memo.md`
- Filed at: `2026-04-15T11:14:56+00:00`
- Protocol: `investing`

## Position Decision
- Approve investing as a first-class protocol inside 炼丹炉, but keep it inside the shared furnace core rather than forking a separate product or runtime.

## Scope And Sizing
- Scope v1 to explicit `company / thesis / catalyst / risk / invalidation / position decision` structures, plus review and aging windows keyed to earnings, catalyst, or thesis-change events.
- Do not expand this decision into brokerage execution, portfolio sync, or multi-user portfolio state.

## Thesis
- `wiki/sources/discovered-20260408053358-item.md` directly argues that investing is one of the two highest-value scenarios for 炼丹炉 once facts, judgments, and actions are separated.
- `wiki/sources/discovered-20260408053946-item.md` argues that domain variation belongs in protocol/schema/workflow layers, which makes investing a protocol decision rather than a second system.
- `wiki/sources/discovered-20260415013128-building-effective-agents.md` and `wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md` support the operational side: explicit templates and contracts become more valuable as reasoning steps, review surfaces, and future integrations grow.

## Evidence
- `wiki/sources/discovered-20260408053358-item.md` provides the direct product-scope justification for investing.
- `wiki/sources/discovered-20260408053946-item.md` keeps the implementation boundary clean by insisting on one furnace core with protocol-specific workflows.
- `wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md` is the key caution and keeps the decision scoped to protocol primitives instead of premature heavy integration work.

## Bear Case And Invalidation
- Bear case: investing demand may remain too thin or too irregular to justify dedicated protocol scaffolding yet.
- Bear case: the workflow might stay mostly note-driven, in which case protocol fields and review windows add ceremony before they add leverage.
- Stop and reconsider if investing materials do not start reusing judgment, review, and revisit surfaces in practice.

## Catalysts And Revisit
- Next catalysts: new company-thesis notes, earnings-style revisits, and any decision page that changes after evidence drift.
- Revisit once the corpus contains enough investing artifacts to show whether thesis revision and position decision history are actually reused.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Counter Evidence
- The investing corpus may stay too small to justify dedicated protocol templates and review windows.
- Operators may prefer lightweight notes until the first real thesis-revision loop proves the workflow is worth the overhead.

## Invalidation
- Invalidate if investing workflows fail to reuse judgment, review, and revisit surfaces in real operator practice.

## Next Signals
- Track whether new investing materials naturally map into thesis, catalyst, risk, invalidation, and position-decision fields.
- Track whether earnings-style reviews reopen prior investing judgments instead of creating disconnected notes.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Review Status
- Current status: `approved`
- Reviewed at: `2026-04-15T11:22:02+00:00`

## Review Notes
- Outcome: `approved`
- Reviewed at: `2026-04-15T11:22:02+00:00`
- Note: Approve investing as a first-class protocol inside the shared furnace core.

## Review History
- `2026-04-15T11:22:02+00:00` | status `approved` | note Approve investing as a first-class protocol inside the shared furnace core.

## Supporting Artifact
# Decision Memo Request · Should 炼丹炉 ship investing as a first-class protocol with explicit thesis and review primitives?

## Usage
- 把 seed memo 改写成这次问题要用的 decision memo。
- 保留 `wiki/sources/*.md` 级别的引用，不要删掉反证、失效条件和下一次信号。
- 当前协议：`investing` (投资协议)。

## 协议输出偏置
- 优先突出 thesis、bull-bear evidence、position sizing guardrail、risk 和 invalidation。

## 机器记忆查询计划
- 命中词：`should, investing, first, protocol, explicit, thesis, and, review`
- 路由策略：`concept-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013344-model-context-protocol-introduction, discovered-20260415015403-protocol-overhead-counterpoint, discovered-20260415013529-a2a-key-concepts, discovered-20260408053946-item, discovered-20260415013128-building-effective-agents, discovered-20260415013612-crewai-agents-concept, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260415013428-google-adk-agents-overview`
- 提升权重的概念：`and, the, protocol, model-context-protocol, abstract, agents, judgment, concepts`
- 协议 shard 来源：`discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013529-a2a-key-concepts, discovered-20260408053946-item, discovered-20260415013128-building-effective-agents, discovered-20260415013612-crewai-agents-concept`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, the, protocol, abstract, agents, judgment, concepts`
- 查询子图边数：`37`
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
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)
- [Model Context Protocol Introduction](../../wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md)
- [A2A Key Concepts](../../wiki/sources/discovered-20260415013529-a2a-key-concepts.md)
- [Protocol Overhead Counterpoint](../../wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md)

## Seed Pack
- Source pack: `../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-protocol-boundary-judgment.md`
- Judgment asset: `../../wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md`
- Target page: `../../wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md`

## Seed Memo
## Overview
- Target page: `wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md`
- Status: `已确认`
- Protocol: `research` (研发协议)
- Reviewed at: `2026-04-15T01:51:03+00:00`
- Confidence: `medium`

## Executive Summary
- MCP or A2A boundaries become worth the cost when an agent runtime must coordinate heterogeneous tools, multiple executors, or external agents with explicit contracts.

## Signals
- `wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md` frames MCP as a stable model-tool boundary, which is a direct signal that protocol seams become useful when tools and executors diversify.
- `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` and `wiki/sources/discovered-20260415013128-building-effective-agents.md` both point to explicit contracts once agents cross service or ownership boundaries, while the local runtime still shows a simpler in-process path.

## Recommendation
- 当前应保持谨慎，把它视为待复核立场，而不是最终结论。
- 下一次优先验证：`Watch whether MCP becomes the default tool boundary for local-first runtimes.`。

## Counter Evidence
- Adding protocol layers too early can slow down a local-first stack that still has one writer and one execution surface.
- In-process tools with strong type contracts may not need a network-oriented agent boundary.

## Invalidation
- Invalidate if direct local adapters consistently deliver the same auditability and portability as protocolized boundaries across new sources.

## Next Signals
- Track whether future sources describe protocol boundaries as required for safety-critical workflows.
- Track whether the local runtime starts crossing process or ownership boundaries often enough to justify a stricter contract seam.

## Review History
- `2026-04-15T11:22:02+00:00` | status `approved` | note Approve investing as a first-class protocol inside the shared furnace core.

## Version History
- `2026-04-15T11:14:56+00:00` | status `confirmed` | confidence `medium`
- `2026-04-15T11:14:55+00:00` | status `confirmed` | confidence `medium`
- `2026-04-15T09:37:31+00:00` | status `confirmed` | confidence `medium`
- `2026-04-15T08:01:21+00:00` | status `confirmed` | confidence `medium`
- `2026-04-15T03:19:50+00:00` | status `confirmed` | confidence `medium`

## Citations
- `wiki/sources/discovered-20260408053946-item.md`
- `wiki/sources/discovered-20260415013128-building-effective-agents.md`
- `wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md`
- `wiki/sources/discovered-20260415013529-a2a-key-concepts.md`
- `wiki/sources/discovered-20260408053358-item.md`

## Nearby Recent Outputs
- [Why should 炼丹炉 separate facts, judgments, and position decisions for investing workflows?](../../../output/reports/query-20260415-111456-why-should-separate-facts-judgments-and-position.md) | format `report` | protocol `investing`
- [Should 炼丹炉 stay one product shell with protocol-specific workflows instead of separate domain apps?](../../../output/reports/query-20260415-111456-should-stay-one-product-shell-with-protocol-spec.md) | format `report` | protocol `product`
- [When should 炼丹炉 keep protocol and governance layers conditional instead of always-on?](../../../output/reports/query-20260415-111455-when-should-keep-protocol-and-governance-layers-.md) | format `report` | protocol `research`
- [What counter-evidence currently argues for keeping small agent runtimes in-process before adding heavy protocol or governance layers?](../../../output/reports/query-20260415-021957-what-counter-evidence-currently-argues-for-keepi.md) | format `report` | protocol `research`
- [Summarize the dominant architecture patterns in the current agent corpus.](../../../output/slides/query-20260415-015034-summarize-the-dominant-architecture-patterns-in-.md) | format `slides` | protocol `research`

## Related Links
- [Protocol Boundary Judgment](../../../wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md)
- [判断资产](../../../wiki/indexes/judgment-assets.md)
- [认知历史](../../../wiki/indexes/cognitive-history.md)
- [审阅中心](../../../wiki/indexes/review-center.md)

## Aging
- Revisit after: `none`
- Escalate after: `none`
