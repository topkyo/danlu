---
id: "judgment-20260415-111456-single-furnace-product-shell-judgment"
kind: "judgment"
status: "confirmed"
title: "Single Furnace Product Shell Judgment"
protocol: "product"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-111456-should-stay-one-product-shell-with-protocol-spec.md"
citations:
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260408053358-item.md"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
citation_snapshots:
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md#6f37eed9d8925f266f552b166f7fbb0694744b86ec602627531bb08000f36390"
  - "wiki/sources/discovered-20260415013529-a2a-key-concepts.md#15a70e40147aed0ee77ce053915876b92f24391a6a49eea4b580f7f5a3c5f3a5"
  - "wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md#754b5d075b848d947436f47246cf5c7f7428b7695d4a8dec616bab1c16fa72c6"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T11:14:56+00:00"
confidence: "medium"
counter_evidence:
  - "Different operator personas may still want dedicated shells if protocol switching adds too much navigation noise."
  - "A single shell can hide domain-specific workflows behind generic surfaces and slow onboarding."
invalidation_rule: "If operators repeatedly need separate navigation, metrics, or review loops that cannot coexist cleanly in one shell, invalidate this single-shell judgment."
next_signals:
  - "Track whether dashboard and shell-status usage cluster by protocol without forcing separate app entry points."
  - "Track whether new investing or product workflows stay understandable after they land in the shared shell."
formed_at: "2026-04-15T11:14:56+00:00"
last_reviewed: "2026-04-15T11:22:02+00:00"
reviewed_at: "2026-04-15T11:22:02+00:00"
revisit_after: ""
escalate_after: ""
---

# Single Furnace Product Shell Judgment

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-111456-should-stay-one-product-shell-with-protocol-spec.md`
- Filed at: `2026-04-15T11:14:56+00:00`
- Protocol: `product`

## Product Judgment
- 炼丹炉 should present one shared product shell with protocol-specific workflows, rather than separate investing, research, and product apps. The shell's job is to expose the same reviewable runtime core while letting schema, prompts, packs, and review signals shift by protocol.

## User Signal And Evidence
- `wiki/sources/discovered-20260408053946-item.md` is the clearest product signal: it argues for one furnace core and multiple protocols because graph, review, repair, machine memory, and outputs are shared leverage rather than domain-specific duplicates.
- `wiki/sources/discovered-20260408053358-item.md` supports the same direction from the operator-workflow side: investing and research both need judgment, decision, review, and aging surfaces, even though their templates differ.
- `wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md` and `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` reinforce that interfaces can standardize interactions without forcing separate products.
- `wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md` is the main product caution: adding one more abstraction layer only helps if it clarifies workflows instead of creating ceremony.

## Counter Signals
- If operators keep asking for separate navigation stacks, terminology, or default outputs that the shared shell cannot express cleanly, the single-shell bet weakens.
- If protocol switching makes the shell harder to understand than separate entry points, the product cost may outweigh the shared-core benefit.

## Confidence And Next Validation
- Confidence is medium because the corpus strongly supports a shared core, but there is still little real operator behavior data about how many protocol modes one shell can expose without confusion.
- Next validation: observe whether new protocol-specific surfaces can land as shell overlays instead of demanding separate top-level products.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Counter Evidence
- Dedicated shells could still win if protocol-specific onboarding, metrics, or IA diverge too far.
- A shared shell can become generic enough that users stop recognizing the domain workflow they came for.

## Invalidation
- Invalidate if operators repeatedly need separate navigation, metrics, or review loops that cannot coexist cleanly in one shell.

## Next Signals
- Track whether dashboard and shell-status usage cluster by protocol without forcing separate app entry points.
- Track whether new investing or product workflows stay understandable after they land in the shared shell.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Review Status
- Current status: `confirmed`
- Reviewed at: `2026-04-15T11:22:02+00:00`
- Confidence: `medium`

## Review Notes
- Outcome: `confirmed`
- Reviewed at: `2026-04-15T11:22:02+00:00`
- Note: Single shell remains the product bet while protocols carry workflow differences.

## Review History
- `2026-04-15T11:22:02+00:00` | status `confirmed` | confidence `medium` | note Single shell remains the product bet while protocols carry workflow differences.

## Supporting Artifact
# Should 炼丹炉 stay one product shell with protocol-specific workflows instead of separate domain apps?

## 回答约束
- 所有重要结论都要落回 `wiki/sources/*.md`。
- 有不确定性就直接写出来，不要补洞。
- 优先使用文件路径引用，而不是模糊转述。
- 当前协议：`product` (产品协议)。

## 协议输出偏置
- 优先组织成 user problem / insight / bet / metric / launch risk / next validation。
- 把关键假设、受影响用户和下一次验证窗口写清楚。

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
- [当前协议规则](../../schema/protocols/product/index.md)

## 机器记忆查询计划
- 命中词：`should, one, product, shell, protocol, specific, workflows, instead, separate, apps`
- 路由策略：`concept-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415015403-protocol-overhead-counterpoint, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013329-react-paper-abstract, discovered-20260408053946-item, discovered-20260415013529-a2a-key-concepts, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260415013128-building-effective-agents, discovered-20260415013612-crewai-agents-concept`
- 提升权重的概念：`the, protocol, and, model-context-protocol, concepts, judgment, agents, mcp`
- 协议 shard 来源：`none`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`the, protocol, and, concepts, judgment, agents`
- 查询子图边数：`33`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-and` / `拆分过载概念 And` / score `78`

## 推荐概念
- [Protocol](../../wiki/concepts/protocol.md)
- [Mcp](../../wiki/concepts/mcp.md)
- [Model Context Protocol](../../wiki/concepts/model-context-protocol.md)
- [The](../../wiki/concepts/the.md)
- [Judgment](../../wiki/concepts/judgment.md)

## 推荐来源
- [统一的炼丹炉](../../wiki/sources/discovered-20260408053946-item.md)
- [Protocol Overhead Counterpoint](../../wiki/sources/discovered-20260415015403-protocol-overhead-counterpoint.md)
- [A2A Key Concepts](../../wiki/sources/discovered-20260415013529-a2a-key-concepts.md)
- [Model Context Protocol Introduction](../../wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md)
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)

## 草稿提纲
1. 重新表述研究问题。
2. 按当前协议优先组织最相关来源和概念。
3. 写出分歧、证据缺口和下一步问题。

## 引用要求
- 在最终答案里加入 source-page 内联引用。

## Aging
- Revisit after: `none`
- Escalate after: `none`
