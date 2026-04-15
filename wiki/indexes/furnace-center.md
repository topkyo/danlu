# 炉心面板

- 最近编译时间：`2026-04-15T03:37:27+00:00`
- 当前协议：`research` (研发协议)
- 来源节点：`15`
- 概念节点：`30`
- 待审项目：`0`
- 已到期 / 升级：`1` / `1`
- Judgment formed / active / under-review / revised / retired：`0` / `3` / `1` / `1` / `0`
- 生命周期概念待审 / 已退役：`30` / `0`
- 证据漂移：`0`
- Judgment review actions：`5`
- Ready repair actions：`0`
- 可直接 apply 的动作：`0`
- Rewrite 提案：`12`
- 可直接 apply 的 rewrite：`0`
- 页级 patch step：`18`
- 当前协议 stage：`active`
- 当前协议 outputs / receipts：`7` / `0`
- 当前协议 review packs / memos / SOP：`1` / `5` / `8`
- 最近输出：`7`
- 本地控制面板：`output/control/furnace-center.html`

## 今天先做什么
1. 先处理 `5` 个 lifecycle concept backlog。
2. 先清理 `5` 个 judgment review action。
3. 优先复查 `1` 个升级项。

## 即刻可执行

### Execution Proposals
- `overloaded-concept-and` | risk `high` | targets `wiki/concepts/and.md`
- `overloaded-concept-the` | risk `high` | targets `wiki/concepts/the.md`
- `bridge-concept-abstract` | risk `low` | targets `wiki/concepts/abstract.md`
- `bridge-concept-agents` | risk `low` | targets `wiki/concepts/agents.md`
- `bridge-concept-and` | risk `low` | targets `wiki/concepts/and.md`
- `bridge-concept-concepts` | risk `low` | targets `wiki/concepts/concepts.md`
- `bridge-concept-protocol` | risk `low` | targets `wiki/concepts/protocol.md`
- `bridge-concept-the` | risk `low` | targets `wiki/concepts/the.md`

### Page-Level Patch Plan
- `overloaded-concept-and` | patch step `3`
  - `wiki/concepts/and.md` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - `wiki/indexes/concept-quality.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - `wiki/indexes/rewrite-proposals.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- `overloaded-concept-the` | patch step `3`
  - `wiki/concepts/the.md` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - `wiki/indexes/concept-quality.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - `wiki/indexes/rewrite-proposals.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- `bridge-concept-abstract` | patch step `2`
  - `wiki/concepts/abstract.md` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - `wiki/indexes/graph-health.md` | mode `review` | sections `Bridge Concepts, Repair Signals`
- `bridge-concept-agents` | patch step `2`
  - `wiki/concepts/agents.md` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - `wiki/indexes/graph-health.md` | mode `review` | sections `Bridge Concepts, Repair Signals`

## 最近输出
- [What counter-evidence currently argues for keeping small agent runtimes in-process before adding heavy protocol or governance layers?](../../output/reports/query-20260415-021957-what-counter-evidence-currently-argues-for-keepi.md) | format `report` | protocol `research` | created `2026-04-15T02:19:57+00:00`
- [Summarize the dominant architecture patterns in the current agent corpus.](../../output/slides/query-20260415-015034-summarize-the-dominant-architecture-patterns-in-.md) | format `slides` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [Which architecture layers recur across modern LLM agent frameworks?](../../output/reports/query-20260415-015034-which-architecture-layers-recur-across-modern-ll.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [When should an agent runtime adopt MCP or A2A as explicit protocol boundaries?](../../output/reports/query-20260415-015034-when-should-an-agent-runtime-adopt-mcp-or-a2a-as.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [What governance and failure-mode controls are required for multi-agent systems?](../../output/reports/query-20260415-015034-what-governance-and-failure-mode-controls-are-re.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [Decision Memo Request · Should 炼丹炉 keep explicit protocol and governance layers inside the runtime?](../../output/reports/query-20260415-015034-should-keep-explicit-protocol-and-governance-lay-decision-memo.md) | format `decision-memo` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [SOP Request · Draft an operator SOP for curating and reviewing agent-runtime evidence.](../../output/reports/query-20260415-015034-draft-an-operator-sop-for-curating-and-reviewing-sop.md) | format `sop` | protocol `research` | created `2026-04-15T01:50:34+00:00`

## 当前协议 Pilot
- [研发协议 Pilot Scorecard](../../output/pilots/research.md) | stage `active` | 判断和 pack 已形成，但执行闭环还不够密。

### 当前缺口
- 有 `3` 个 protocol-related lifecycle concept backlog 尚未收敛。
- 还没有 execution receipt，可先从 dry-run / low-risk apply 开始。

### 下一动作
- 有 `3` 个 protocol-related lifecycle concept backlog 尚未收敛。
- 围绕 paper / repo / benchmark / experiment / architecture decision 组织知识。
- 重点审 regression、benchmark drift、过期实验结论和架构取舍。
- 优先抬升 weak concepts、failed experiments、regression signals。

## Lifecycle 治理摘要
- review concepts：`3`
- revisit concepts：`27`
- retired concepts：`0`
- active concepts：`0`
- formed judgments：`0`
- active judgments：`3`
- under-review judgments：`1`
- revised judgments：`1`
- retired judgments：`0`

### Lifecycle Concept Backlog
- [And](../../wiki/concepts/and.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [The](../../wiki/concepts/the.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [Abstract](../../wiki/concepts/abstract.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agent](../../wiki/concepts/agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agents](../../wiki/concepts/agents.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Autogen Multi Agent](../../wiki/concepts/autogen-multi-agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Concept](../../wiki/concepts/concept.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Crewai](../../wiki/concepts/crewai.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Debate](../../wiki/concepts/debate.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Decision](../../wiki/concepts/decision.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Judgment](../../wiki/concepts/judgment.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Concepts](../../wiki/concepts/concepts.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `6` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`

### Retired Concepts
- 当前没有 retired concept。

### Judgment Lifecycle Focus
- [Recurring Agent Layers Judgment](../../wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md) | kind `judgment` | state `待回看` | judgment_state `复审中` | invalidation `overdue-review,escalation-candidate` | active_corpora `7` | reasons `invalidation-signal,overdue-review,escalation-candidate`
- [Agent Governance Judgment](../../wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md) | kind `judgment` | state `活跃` | judgment_state `已修订` | active_corpora `7` | reasons `active-corpus-linked`

### Judgment Review Actions
- `Review Agent Governance Judgment` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md --status tracking`
- `Review Protocol Boundary Judgment` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md --status tracking`
- `Review Recurring Agent Layers Judgment` | priority `high` | reasons `escalation-candidate, overdue-review, counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md --status tracking`
- `Review Agent Governance Decision` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-015034-agent-governance-decision.md --status needs-revisit`
- `Review Runtime Protocol Layer Decision` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-015034-runtime-protocol-layer-decision.md --status needs-revisit`

## 最新输出 Packs
- [Decision Memo · Agent Governance Decision](../../output/packs/decision-memos/wiki-decisions-decision-20260415-015034-agent-governance-decision.md) | kind `Decision Memo` | meta `2026-04-15T01:53:07+00:00`
- [Decision Memo · Runtime Protocol Layer Decision](../../output/packs/decision-memos/wiki-decisions-decision-20260415-015034-runtime-protocol-layer-decision.md) | kind `Decision Memo` | meta `2026-04-15T01:51:03+00:00`
- [Judgment Memo · Agent Governance Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-agent-governance-judgment.md) | kind `Decision Memo` | meta `2026-04-15T02:19:57+00:00`
- [Judgment Memo · Protocol Boundary Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-protocol-boundary-judgment.md) | kind `Decision Memo` | meta `2026-04-15T01:51:03+00:00`
- [Judgment Memo · Recurring Agent Layers Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-recurring-agent-layers-judgment.md) | kind `Decision Memo` | meta `2026-04-15T01:51:03+00:00`
- [Review Pack · Recurring Agent Layers Judgment](../../output/packs/review/wiki-judgments-judgment-20260415-015034-recurring-agent-layers-judgment.md) | kind `Review Pack` | meta `overdue review, escalation candidate`
- [SOP Draft · 拆分过载概念 And](../../output/packs/sop-drafts/overloaded-concept-and.md) | kind `SOP Draft` | meta `high`
- [SOP Draft · 拆分过载概念 The](../../output/packs/sop-drafts/overloaded-concept-the.md) | kind `SOP Draft` | meta `high`

## 最近执行回执
- 当前协议还没有 execution receipt。

## 最近已审 / 已沉淀
- [Agent Governance Judgment](../../wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md) | status `已确认` | reviewed `2026-04-15T02:19:57+00:00`
- [Agent Governance Decision](../../wiki/decisions/decision-20260415-015034-agent-governance-decision.md) | status `已批准` | reviewed `2026-04-15T01:53:07+00:00`
- [Runtime Protocol Layer Decision](../../wiki/decisions/decision-20260415-015034-runtime-protocol-layer-decision.md) | status `已批准` | reviewed `2026-04-15T01:51:03+00:00`
- [Recurring Agent Layers Judgment](../../wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md) | status `已确认` | reviewed `2026-04-15T01:51:03+00:00`
- [Protocol Boundary Judgment](../../wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md) | status `已确认` | reviewed `2026-04-15T01:51:03+00:00`

## 快速命令
- `PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status`
- `PYTHONPATH=src python3 -m aiwiki.cli --root . ask "对当前主题做协议化总结" --format report --protocol research`
- `PYTHONPATH=src python3 -m aiwiki.cli --root . nightly`

## 快速跳转
- [审阅中心](./review-center.md)
- [执行中心](./execution-center.md)
- [执行审计](./execution-audit.md)
- [Agent Workbench](./agent-workbench.md)
- [认知历史](./cognitive-history.md)
- [输出 Pack 总览](./output-packs.md)
- [领域 Pilot 总览](./domain-pilots.md)
- [判断资产](./judgment-assets.md)
- [图谱视图](./graph-view.md)
- [修复待办](./repair-backlog.md)
- [协议总览](./protocols.md)
- [输出面板](./Outputs.md)
- [本地审阅面板](../../output/review/review-center.html)
- [本地图谱视图](../../output/graph/machine-memory.html)
- [本地炉心面板](../../output/control/furnace-center.html)
- [本地执行面板](../../output/control/execution-center.html)
- [本地执行审计面板](../../output/control/execution-audit.html)
