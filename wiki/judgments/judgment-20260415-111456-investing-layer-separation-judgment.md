---
id: "judgment-20260415-111456-investing-layer-separation-judgment"
kind: "judgment"
status: "confirmed"
title: "Investing Layer Separation Judgment"
protocol: "investing"
source_files:
  - "/home/tim/ai-wiki/output/reports/query-20260415-111456-why-should-separate-facts-judgments-and-position.md"
citations:
  - "wiki/sources/discovered-20260408053358-item.md"
  - "wiki/sources/discovered-20260408053946-item.md"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md"
  - "wiki/sources/discovered-20260415013428-google-adk-agents-overview.md"
citation_snapshots:
  - "wiki/sources/discovered-20260408053358-item.md#c13ff3a1c5fc5523b8d0452f566e257e0fce75d6eb99ff019ddc99805eb8abf1"
  - "wiki/sources/discovered-20260408053946-item.md#0e2c327565c35311e2f2d4ee693ca3ac4ba2917e67d5541fc7de9b34dd173546"
  - "wiki/sources/discovered-20260415013128-building-effective-agents.md#2b9fefd6df1175acb14f2312c3e9c078398338321a27c53f5adafa2ef9a5da02"
  - "wiki/sources/discovered-20260415013329-react-paper-abstract.md#bbb5de6cff747a0a40dd1112ecbdd76a9e57c06d85802e72a14f88e8a35d44f8"
  - "wiki/sources/discovered-20260415013612-crewai-agents-concept.md#1dff29c2fbe8e43e72cfb1e136f75f40e8a682ad0df9c2f25b69eff028adbded"
  - "wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md#6f37eed9d8925f266f552b166f7fbb0694744b86ec602627531bb08000f36390"
  - "wiki/sources/discovered-20260415013428-google-adk-agents-overview.md#0561fcd5faf5086c904d826ec2dd3cb53cb687bed2a4c06c06ffaf7d3d83d6ba"
generated_by: "aiwiki-file-back"
last_compiled_at: "2026-04-15T11:14:56+00:00"
confidence: "medium"
counter_evidence:
  - "A small watchlist can often be managed with plain notes before a full fact / judgment / decision stack pays for itself."
  - "If operators never revisit old theses, explicit separation can become documentation overhead instead of leverage."
invalidation_rule: "If investing operators can repeatedly update theses and position actions without losing provenance or review context in a flatter note structure, weaken this judgment."
next_signals:
  - "Track whether earnings or catalyst reviews reopen prior judgments instead of spawning disconnected notes."
  - "Track whether position actions can be traced back to explicit thesis, risk, and invalidation entries during review."
formed_at: "2026-04-15T11:14:56+00:00"
last_reviewed: "2026-04-15T11:22:01+00:00"
reviewed_at: "2026-04-15T11:22:01+00:00"
revisit_after: ""
escalate_after: ""
---

# Investing Layer Separation Judgment

## Origin
- Filed from: `/home/tim/ai-wiki/output/reports/query-20260415-111456-why-should-separate-facts-judgments-and-position.md`
- Filed at: `2026-04-15T11:14:56+00:00`
- Protocol: `investing`

## Investment Judgment
- Investing workflows need an explicit split between raw facts, interpretive judgments, and position decisions. Without that split, thesis evolution, counter-evidence, and action history collapse into one note stream and become hard to review when earnings, catalysts, or valuation assumptions change.

## Drivers And Catalysts
- `wiki/sources/discovered-20260408053358-item.md` is the strongest direct signal: it defines the investing stack as `raw -> sources -> concepts -> judgments -> decisions -> review/aging`, explicitly tying judgment pages to thesis interpretation and decision pages to actions such as observe, buy, trim, or reject.
- `wiki/sources/discovered-20260408053946-item.md` extends the same logic at the runtime boundary: investing should vary at the protocol/template/workflow layer, not by forking a separate system or collapsing all artifacts into one page type.
- `wiki/sources/discovered-20260415013128-building-effective-agents.md`, `wiki/sources/discovered-20260415013329-react-paper-abstract.md`, and `wiki/sources/discovered-20260415013612-crewai-agents-concept.md` all reinforce the operational side of the split: once reasoning becomes multi-step, operators need a way to inspect evidence, interpretation, and final action separately.

## Risks And Invalidation
- The main risk is over-structuring a small investing corpus before repeated thesis revisions and review loops exist.
- Another risk is false precision: a layered workflow can look rigorous even if the underlying evidence base remains thin.
- Invalidate the judgment if a flatter note workflow keeps preserving provenance, counter-evidence, and position history just as well through multiple earnings-style revisions.

## Confidence And Watchlist
- Confidence is medium because the local corpus argues for the investing stack structurally, but it still lacks repeated live investing review cycles to prove the workflow pays off in practice.
- Watchlist: the next useful proof point is whether one company thesis can move through fact updates, judgment revision, and decision change without losing prior reasoning.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Counter Evidence
- Very small watchlists can be operated with lighter-weight notes and manual checklists for a long time.
- If position actions are rare, explicit decision pages may add ceremony before they add review leverage.

## Invalidation
- Invalidate if investing operators can repeatedly update theses and position actions without losing provenance or review context in a flatter note structure.

## Next Signals
- Track whether earnings or catalyst reviews reopen prior judgments instead of spawning disconnected notes.
- Track whether position actions can be traced back to explicit thesis, risk, and invalidation entries during review.
- Default revisit window: `2026-04-18T11:14:56+00:00`
- Default escalation window: `2026-04-22T11:14:56+00:00`

## Review Status
- Current status: `confirmed`
- Reviewed at: `2026-04-15T11:22:01+00:00`
- Confidence: `medium`

## Review Notes
- Outcome: `confirmed`
- Reviewed at: `2026-04-15T11:22:01+00:00`
- Note: Investing workflow should preserve the fact / judgment / decision split.

## Review History
- `2026-04-15T11:22:01+00:00` | status `confirmed` | confidence `medium` | note Investing workflow should preserve the fact / judgment / decision split.

## Supporting Artifact
# Why should 炼丹炉 separate facts, judgments, and position decisions for investing workflows?

## 回答约束
- 所有重要结论都要落回 `wiki/sources/*.md`。
- 有不确定性就直接写出来，不要补洞。
- 优先使用文件路径引用，而不是模糊转述。
- 当前协议：`investing` (投资协议)。

## 协议输出偏置
- 优先组织成 thesis / bull-bear evidence / catalysts / risks / invalidation。
- 把时间窗口和下一次财报或事件复审写清楚。

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
- [当前协议规则](../../schema/protocols/investing/index.md)

## 机器记忆查询计划
- 命中词：`why, should, separate, facts, judgments, and, position, decisions, for, investing, workflows`
- 路由策略：`concept-first`
- 路由原因：`default-strategy`
- 来源意图词：`none`
- 图谱意图词：`none`
- 提升权重的来源：`discovered-20260415013612-crewai-agents-concept, discovered-20260415013128-building-effective-agents, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013329-react-paper-abstract, discovered-20260415013529-a2a-key-concepts, discovered-20260415013331-autogen-multi-agent-debate-pattern, discovered-20260415013428-google-adk-agents-overview, discovered-20260415013411-langgraph-agentic-concepts`
- 提升权重的概念：`and, the, abstract, agents, protocol, judgment, agent, concepts`
- 协议 shard 来源：`discovered-20260415013612-crewai-agents-concept, discovered-20260415013128-building-effective-agents, discovered-20260415013344-model-context-protocol-introduction, discovered-20260415013529-a2a-key-concepts, discovered-20260415013331-autogen-multi-agent-debate-pattern`
- 时间偏置：`none`
- 时间意图词：`none`
- 时间 shard 来源：`none`
- 桥接概念：`and, the, abstract, agents, protocol, judgment, agent, concepts`
- 查询子图边数：`29`
- 查询路径数：`4`
- 触达分量：`component-1`
- 命中的修复动作：`6`
- 归档召回提示：`none`
- Planner next action：`overloaded-concept-and` / `拆分过载概念 And` / score `78`

## 推荐概念
- [The](../../wiki/concepts/the.md)
- [Abstract](../../wiki/concepts/abstract.md)
- [And](../../wiki/concepts/and.md)
- [Agent](../../wiki/concepts/agent.md)
- [Agents](../../wiki/concepts/agents.md)

## 推荐来源
- [Building Effective Agents](../../wiki/sources/discovered-20260415013128-building-effective-agents.md)
- [Model Context Protocol Introduction](../../wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md)
- [Google ADK Agents Overview](../../wiki/sources/discovered-20260415013428-google-adk-agents-overview.md)
- [ReAct Paper Abstract](../../wiki/sources/discovered-20260415013329-react-paper-abstract.md)
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
