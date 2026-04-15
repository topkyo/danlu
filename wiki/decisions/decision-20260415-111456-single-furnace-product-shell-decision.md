---
id: "decision-20260415-111456-single-furnace-product-shell-decision"
kind: "decision"
status: "approved"
title: "Single Furnace Product Shell Decision"
protocol: "product"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-111456-should-keep-one-core-product-shell-and-route-by--decision-memo.md"
citations:
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260408053358-item.md"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
citation_snapshots:
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md#6f37eed9d8925f266f552b166f7fbb0694744b86ec602627531bb08000f36390"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md#15a70e40147aed0ee77ce053915876b92f24391a6a49eea4b580f7f5a3c5f3a5"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md#754b5d075b848d947436f47246cf5c7f7428b7695d4a8dec616bab1c16fa72c6"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md#bbb5de6cff747a0a40dd1112ecbdd76a9e57c06d85802e72a14f88e8a35d44f8"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T11:14:56+00:00"
confidence: "medium"
counter_evidence:
  - "Operators may still need dedicated domain shells if protocol-aware navigation remains confusing."
  - "A single shell can become too generic and force product compromises across different operator jobs."
invalidation_rule: "Reconsider this decision if protocol-aware routing fails to keep the shell understandable or if domain workflows repeatedly demand separate top-level products."
next_signals:
  - "Track whether protocol-specific cards, review queues, and packs stay comprehensible inside the shared shell."
  - "Track whether operators request separate entry points or separate products after more protocol surfaces ship."
supports:
  - "wiki/judgments/judgment-20260415-111456-single-furnace-product-shell-judgment.md"
formed_at: "2026-04-15T11:14:56+00:00"
last_reviewed: "2026-04-15T11:22:02+00:00"
reviewed_at: "2026-04-15T11:22:02+00:00"
revisit_after: ""
escalate_after: ""
---

# Single Furnace Product Shell Decision

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-111456-should-keep-one-core-product-shell-and-route-by--decision-memo.md`
- Filed at: `2026-04-15T11:14:56+00:00`
- Protocol: `product`

## Product Decision
- Prioritize one shared product shell with protocol-aware routing and overlays, rather than launching separate investing, research, and product SKUs.

## User Problem And Bet
- Operators need one place to inspect sources, judgments, decisions, review state, and execution controls without losing cross-domain context.
- The bet is that protocol-aware cards, prompts, and packs can specialize the experience while preserving the same core runtime, graph, and governance surfaces underneath.

## Metric And Validation
- `wiki/sources/discovered-20260408053946-item.md` supplies the core rationale: shared graph/review/repair/memory/output capabilities are the reusable asset, so products should vary by protocol rather than by runtime fork.
- `wiki/sources/discovered-20260408053358-item.md` adds the operator proof point: investing and research both need the same classes of artifacts even though their templates differ.
- Primary validation signals: protocol-specific shell usage, review completion by protocol, and whether new packs/outputs remain attributable without spawning separate app shells.

## Launch Risks And Rollback
- Main risk: one shell accumulates enough mode-specific UI that operators stop understanding where to look.
- Secondary risk: protocol-specific language or output packs may demand separate entry points earlier than expected.
- Roll back by extracting protocol-focused landing pages or nav presets while keeping the core runtime and shared shell objects intact.
- Default revisit window: `2026-04-19T11:14:56+00:00`
- Default escalation window: `2026-04-25T11:14:56+00:00`

## Counter Evidence
- Operators may still need dedicated domain shells if protocol-aware navigation remains confusing.
- A single shell can become too generic and force product compromises across different operator jobs.

## Invalidation
- Invalidate if protocol-aware routing fails to keep the shell understandable or if domain workflows repeatedly demand separate top-level products.

## Next Signals
- Track whether protocol-specific cards, review queues, and packs stay comprehensible inside the shared shell.
- Track whether operators request separate entry points or separate products after more protocol surfaces ship.
- Default revisit window: `2026-04-19T11:14:56+00:00`
- Default escalation window: `2026-04-25T11:14:56+00:00`

## Review Status
- Current status: `approved`
- Reviewed at: `2026-04-15T11:22:02+00:00`

## Review Notes
- Outcome: `approved`
- Reviewed at: `2026-04-15T11:22:02+00:00`
- Note: Prioritize one shared shell with protocol-aware routing.

## Review History
- `2026-04-15T11:22:02+00:00` | status `approved` | note Prioritize one shared shell with protocol-aware routing.

## Supporting Artifact
# Decision Memo Request · Should 炼丹炉 keep one core product shell and route by protocol instead of separate domain SKUs?

## Usage
- 把 seed memo 改写成这次问题要用的 decision memo。
- 保留 `wiki/sources/*.md` 级别的引用，不要删掉反证、失效条件和下一次信号。
- 当前协议：`product` (产品协议)。

## 协议输出偏置
- 优先突出用户问题、核心 bet、指标、发布风险和验证窗口。

## 机器记忆查询计划
- 命中词：`should, keep, one, core, product, shell, and, protocol, instead, separate`
- 路由策略：`concept-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415015403-protocol-overhead-counterpoint, discovered-20260415013529-a2a-key-concepts, discovered-20260415013329-react-paper-abstract, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013128-building-effective-agents, discovered-20260415013612-crewai-agents-concept, discovered-20260408053946-item, discovered-20260415013331-autogen-multi-agent-debate-pattern`
- 提升权重的概念：`and, the, protocol, model-context-protocol, abstract, agents, concepts, judgment`
- 协议 shard 来源：`none`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, the, protocol, abstract, agents, concepts, judgment`
- 查询子图边数：`37`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-and` / `拆分过载概念 And` / score `78`

## 推荐概念
- [Protocol](../../wiki/concepts/protocol.md)
- [Model Context Protocol](../../wiki/concepts/model-context-protocol.md)
- [The](../../wiki/concepts/the.md)
- [And](../../wiki/concepts/and.md)
- [Judgment](../../wiki/concepts/judgment.md)

## 推荐来源
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [Model Context Protocol Introduction](../../wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md)
- [A2A Key Concepts](../../wiki/sources/discovered-20260415013529-a2a-key-concepts.md)
- [Protocol Overhead Counterpoint](../../wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md)
- [ReAct Paper Abstract](../../wiki/sources/discovered-20260415013329-react-paper-abstract.md)

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
- `2026-04-15T11:22:02+00:00` | status `approved` | note Prioritize one shared shell with protocol-aware routing.

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
- [Decision Memo Request · Should 炼丹炉 ship investing as a first-class protocol with explicit thesis and review primitives?](../../../output/reports/query-20260415-111456-should-ship-investing-as-a-first-class-protocol--decision-memo.md) | format `decision-memo` | protocol `investing`
- [When should 炼丹炉 keep protocol and governance layers conditional instead of always-on?](../../../output/reports/query-20260415-111455-when-should-keep-protocol-and-governance-layers-.md) | format `report` | protocol `research`
- [What counter-evidence currently argues for keeping small agent runtimes in-process before adding heavy protocol or governance layers?](../../../output/reports/query-20260415-021957-what-counter-evidence-currently-argues-for-keepi.md) | format `report` | protocol `research`

## Related Links
- [Protocol Boundary Judgment](../../../wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md)
- [判断资产](../../../wiki/indexes/judgment-assets.md)
- [认知历史](../../../wiki/indexes/cognitive-history.md)
- [审阅中心](../../../wiki/indexes/review-center.md)

## Aging
- Revisit after: `none`
- Escalate after: `none`
