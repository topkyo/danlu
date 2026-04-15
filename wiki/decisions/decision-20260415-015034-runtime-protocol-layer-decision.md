---
id: "decision-20260415-015034-runtime-protocol-layer-decision"
kind: "decision"
status: "approved"
title: "Runtime Protocol Layer Decision"
protocol: "research"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-015034-should-keep-explicit-protocol-and-governance-lay-decision-memo.md"
citations:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md"
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260408053358-item.md"
citation_snapshots:
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md#bbb5de6cff747a0a40dd1112ecbdd76a9e57c06d85802e72a14f88e8a35d44f8"
  - "wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md#58dc9dc777e6a918cde731c940b0b836ff4b8d2de29099a771f61bd7acdf01a5"
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T01:50:34+00:00"
confidence: "high"
counter_evidence:
  - "A single-process local runtime could keep adapters inline longer before splitting a formal protocol layer."
  - "Protocol and governance layers add maintenance cost when the tool surface is still narrow."
invalidation_rule: "Reconsider this decision if direct adapters keep matching the portability, auditability, and repair ergonomics of explicit protocol layers."
next_signals:
  - "Track whether new integrations are blocked by missing protocol seams."
  - "Track whether operator review load decreases once protocol boundaries are explicit."
formed_at: "2026-04-15T01:50:34+00:00"
last_reviewed: "2026-04-15T01:51:03+00:00"
reviewed_at: "2026-04-15T01:51:03+00:00"
revisit_after: ""
escalate_after: ""
---

# Runtime Protocol Layer Decision

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-015034-should-keep-explicit-protocol-and-governance-lay-decision-memo.md`
- Filed at: `2026-04-15T01:50:34+00:00`
- Protocol: `research`

## Decision
- Adopt explicit protocol and governance layers as first-class runtime surfaces inside 炼丹炉, rather than treating them as optional add-ons.

## Affected Surface
- `schema/protocols/*`, ask/file-back/nightly flows, execution policy, review queue, and future external agent or tool adapters.
- Product Shell surfaces that need audit-friendly status, receipts, and protocol-aware summaries.

## Evidence
- `building-effective-agents`, `react-paper-abstract`, and `autogen-multi-agent-debate-pattern` all imply that multi-step reasoning becomes easier to operate when orchestration and evaluation surfaces are explicit.
- The local corpus already activates protocol dashboards, review queues, and execution audit pages; keeping those in-runtime preserves provenance and reversibility.

## Validation Plan
- Validate by showing that protocol-aware ask/review/nightly flows keep producing auditable outputs without adding import-time or operator complexity regressions.
- Confirm that new tools or agent integrations can land against protocol contracts instead of bespoke one-off wiring.

## Rollback And Risks
- Main risk: over-abstracting a still-local runtime and paying coordination cost too early.
- Roll back by collapsing protocol wiring back into direct adapters if operator throughput or maintainability clearly regresses.

## Counter Evidence
- A simpler adapter-only stack may stay easier to maintain while integrations remain few.
- Some protocol layers may standardize ecosystem growth more than runtime quality.

## Invalidation
- Invalidate if future integrations repeatedly bypass the protocol layer because it creates more friction than safety or audit value.

## Next Signals
- Watch whether new agent or tool integrations naturally target the protocol contracts.
- Watch whether governance surfaces keep surfacing actionable work instead of idle scaffolding.

## Review Status
- Current status: `approved`
- Reviewed at: `2026-04-15T01:51:03+00:00`

## Review Notes
- Outcome: `approved`
- Reviewed at: `2026-04-15T01:51:03+00:00`
- Note: Explicit protocol/governance layers remain justified.

## Review History
- `2026-04-15T01:51:03+00:00` | status `approved` | note Explicit protocol/governance layers remain justified.

## Supporting Artifact
# Decision Memo Request · Should 炼丹炉 keep explicit protocol and governance layers inside the runtime?

## Usage
- 把 seed memo 改写成这次问题要用的 decision memo。
- 保留 `wiki/sources/*.md` 级别的引用，不要删掉反证、失效条件和下一次信号。
- 当前协议：`research` (研发协议)。

## 协议输出偏置
- 优先突出假设、实验信号、反例、回归风险和下一轮验证。

## 机器记忆查询计划
- 命中词：`should, keep, protocol, and, the, runtime`
- 路由策略：`source-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013128-building-effective-agents, discovered-20260415013329-react-paper-abstract, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260408053946-item, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013427-toolformer-paper-abstract, discovered-20260415013427-voyager-paper-abstract, discovered-20260415013529-a2a-key-concepts`
- 提升权重的概念：`and, the, protocol, agent, decision, abstract, agents, autogen-multi-agent`
- 协议 shard 来源：`discovered-20260415013329-react-paper-abstract, discovered-20260415013427-toolformer-paper-abstract, discovered-20260415013427-voyager-paper-abstract`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, the, protocol, agent, decision, abstract, agents`
- 查询子图边数：`27`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-url` / `拆分过载概念 Url` / score `56`

## 推荐概念
- [Abstract](../../wiki/concepts/abstract.md)
- [And](../../wiki/concepts/and.md)
- [Protocol](../../wiki/concepts/protocol.md)
- [The](../../wiki/concepts/the.md)
- [Agent](../../wiki/concepts/agent.md)

## 推荐来源
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [ReAct Paper Abstract](../../wiki/sources/discovered-20260415013329-react-paper-abstract.md)
- [AutoGen Multi Agent Debate Pattern](../../wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)
- [炼丹炉场景路线图](../../wiki/sources/discovered-20260408053358-item.md)

## Seed Pack
- 当前没有可复用的 compiled decision memo；请基于推荐来源直接起草。

## Seed Memo
## Executive Summary
- Pending synthesis.

## Evidence
- Cite the strongest supporting signals with `wiki/sources/*.md` links.

## Counter Evidence
- Record the strongest counter case explicitly.

## Invalidation
- State what would break the memo.

## Next Signals
- Note what should be checked next.

## Aging
- Revisit after: `none`
- Escalate after: `none`
