# 炉心面板

- 最近编译时间：`2026-04-16T14:24:39+00:00`
- 当前协议：`research` (研发协议)
- 来源节点：`15`
- 概念节点：`30`
- 待审项目：`2`
- 已到期 / 升级：`0` / `0`
- Judgment formed / active / under-review / revised / retired：`0` / `6` / `2` / `2` / `0`
- 生命周期概念待审 / 已退役：`30` / `0`
- 证据漂移：`0`
- Judgment review actions：`10`
- Ready repair actions：`6`
- 可直接 apply 的动作：`0`
- Rewrite 提案：`12`
- 可直接 apply 的 rewrite：`0`
- 页级 patch step：`18`
- 当前协议 stage：`compounding`
- 当前协议 outputs / receipts：`12` / `3`
- 当前协议 review packs / memos / SOP：`2` / `4` / `8`
- 最近输出：`12`
- 本地控制面板：`output/control/furnace-center.html`

## 今天先做什么
1. 先处理 `5` 个 lifecycle concept backlog。
2. 先清理 `5` 个 judgment review action。
3. 继续审 `2` 个 decision / judgment 页面。

## 即刻可执行

### Execution Proposals
- `overloaded-concept-and` | risk `high` | targets `wiki/concepts/and.md`
- `overloaded-concept-the` | risk `high` | targets `wiki/concepts/the.md`
- `bridge-concept-and` | risk `low` | targets `wiki/concepts/and.md`
- `bridge-concept-the` | risk `low` | targets `wiki/concepts/the.md`
- `bridge-concept-abstract` | risk `low` | targets `wiki/concepts/abstract.md`
- `bridge-concept-agents` | risk `low` | targets `wiki/concepts/agents.md`
- `bridge-concept-judgment` | risk `low` | targets `wiki/concepts/judgment.md`
- `bridge-concept-protocol` | risk `low` | targets `wiki/concepts/protocol.md`

### Page-Level Patch Plan
- `overloaded-concept-and` | patch step `3`
  - `wiki/concepts/and.md` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - `wiki/indexes/concept-quality.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - `wiki/indexes/rewrite-proposals.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- `overloaded-concept-the` | patch step `3`
  - `wiki/concepts/the.md` | mode `rewrite` | sections `Summary, Related Sources, Related Concepts`
  - `wiki/indexes/concept-quality.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
  - `wiki/indexes/rewrite-proposals.md` | mode `review` | sections `Merge Candidates, Rewrite Priority`
- `bridge-concept-and` | patch step `2`
  - `wiki/concepts/and.md` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - `wiki/indexes/graph-health.md` | mode `review` | sections `Bridge Concepts, Repair Signals`
- `bridge-concept-the` | patch step `2`
  - `wiki/concepts/the.md` | mode `review` | sections `Summary, Related Concepts, Related Sources`
  - `wiki/indexes/graph-health.md` | mode `review` | sections `Bridge Concepts, Repair Signals`

## 最近输出
- [Why should 炼丹炉 separate facts, judgments, and position decisions for investing workflows?](../../output/reports/query-20260415-111456-why-should-separate-facts-judgments-and-position.md) | format `report` | protocol `investing` | created `2026-04-15T11:14:56+00:00`
- [Should 炼丹炉 stay one product shell with protocol-specific workflows instead of separate domain apps?](../../output/reports/query-20260415-111456-should-stay-one-product-shell-with-protocol-spec.md) | format `report` | protocol `product` | created `2026-04-15T11:14:56+00:00`
- [Decision Memo Request · Should 炼丹炉 ship investing as a first-class protocol with explicit thesis and review primitives?](../../output/reports/query-20260415-111456-should-ship-investing-as-a-first-class-protocol--decision-memo.md) | format `decision-memo` | protocol `investing` | created `2026-04-15T11:14:56+00:00`
- [Decision Memo Request · Should 炼丹炉 keep one core product shell and route by protocol instead of separate domain SKUs?](../../output/reports/query-20260415-111456-should-keep-one-core-product-shell-and-route-by--decision-memo.md) | format `decision-memo` | protocol `product` | created `2026-04-15T11:14:56+00:00`
- [When should 炼丹炉 keep protocol and governance layers conditional instead of always-on?](../../output/reports/query-20260415-111455-when-should-keep-protocol-and-governance-layers-.md) | format `report` | protocol `research` | created `2026-04-15T11:14:55+00:00`
- [What counter-evidence currently argues for keeping small agent runtimes in-process before adding heavy protocol or governance layers?](../../output/reports/query-20260415-021957-what-counter-evidence-currently-argues-for-keepi.md) | format `report` | protocol `research` | created `2026-04-15T02:19:57+00:00`
- [Summarize the dominant architecture patterns in the current agent corpus.](../../output/slides/query-20260415-015034-summarize-the-dominant-architecture-patterns-in-.md) | format `slides` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [Which architecture layers recur across modern LLM agent frameworks?](../../output/reports/query-20260415-015034-which-architecture-layers-recur-across-modern-ll.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [When should an agent runtime adopt MCP or A2A as explicit protocol boundaries?](../../output/reports/query-20260415-015034-when-should-an-agent-runtime-adopt-mcp-or-a2a-as.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [What governance and failure-mode controls are required for multi-agent systems?](../../output/reports/query-20260415-015034-what-governance-and-failure-mode-controls-are-re.md) | format `report` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [Decision Memo Request · Should 炼丹炉 keep explicit protocol and governance layers inside the runtime?](../../output/reports/query-20260415-015034-should-keep-explicit-protocol-and-governance-lay-decision-memo.md) | format `decision-memo` | protocol `research` | created `2026-04-15T01:50:34+00:00`
- [SOP Request · Draft an operator SOP for curating and reviewing agent-runtime evidence.](../../output/reports/query-20260415-015034-draft-an-operator-sop-for-curating-and-reviewing-sop.md) | format `sop` | protocol `research` | created `2026-04-15T01:50:34+00:00`

## 当前协议 Pilot
- [研发协议 Pilot Scorecard](../../output/pilots/research.md) | stage `compounding` | 已经出现判断、pack、执行和复审的复利迹象。

### 当前缺口
- 有 `4` 个 protocol-related lifecycle concept backlog 尚未收敛。

### 下一动作
- 有 `4` 个 protocol-related lifecycle concept backlog 尚未收敛。
- 围绕 paper / repo / benchmark / experiment / architecture decision 组织知识。
- 重点审 regression、benchmark drift、过期实验结论和架构取舍。
- 优先抬升 weak concepts、failed experiments、regression signals。

## Lifecycle 治理摘要
- review concepts：`2`
- revisit concepts：`28`
- retired concepts：`0`
- active concepts：`0`
- formed judgments：`0`
- active judgments：`6`
- under-review judgments：`2`
- revised judgments：`2`
- retired judgments：`0`

### Lifecycle Concept Backlog
- [And](../../wiki/concepts/and.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `12` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [The](../../wiki/concepts/the.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `12` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [Abstract](../../wiki/concepts/abstract.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agent](../../wiki/concepts/agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agents](../../wiki/concepts/agents.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Autogen Multi Agent](../../wiki/concepts/autogen-multi-agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Concept](../../wiki/concepts/concept.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Crewai](../../wiki/concepts/crewai.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Debate](../../wiki/concepts/debate.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Decision](../../wiki/concepts/decision.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Judgment](../../wiki/concepts/judgment.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Memory](../../wiki/concepts/memory.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `12` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`

### Retired Concepts
- 当前没有 retired concept。

### Judgment Lifecycle Focus
- [Agent Governance Decision](../../wiki/decisions/decision-20260415-015034-agent-governance-decision.md) | kind `decision` | state `待回看` | judgment_state `复审中` | invalidation `explicit-needs-revisit` | active_corpora `12` | reasons `invalidation-signal,explicit-needs-revisit`
- [Agent Governance Judgment](../../wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md) | kind `judgment` | state `待审` | judgment_state `复审中` | active_corpora `12` | reasons `pending-review-status`
- [Conditional Governance Threshold Judgment](../../wiki/judgments/judgment-20260415-111455-conditional-governance-threshold-judgment.md) | kind `judgment` | state `活跃` | judgment_state `已修订` | active_corpora `12` | reasons `active-corpus-linked`
- [Recurring Agent Layers Judgment](../../wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md) | kind `judgment` | state `活跃` | judgment_state `已修订` | active_corpora `12` | reasons `active-corpus-linked`

### Judgment Review Actions
- `Review Agent Governance Judgment` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-agent-governance-judgment.md --status confirmed`
- `Review Agent Governance Decision` | priority `high` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-015034-agent-governance-decision.md --status approved`
- `Review Conditional Governance Threshold Judgment` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-111455-conditional-governance-threshold-judgment.md --status tracking`
- `Review Investing Layer Separation Judgment` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-111456-investing-layer-separation-judgment.md --status tracking`
- `Review Protocol Boundary Judgment` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-protocol-boundary-judgment.md --status tracking`
- `Review Recurring Agent Layers Judgment` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md --status tracking`
- `Review Single Furnace Product Shell Judgment` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/judgments/judgment-20260415-111456-single-furnace-product-shell-judgment.md --status tracking`
- `Review Investing Protocol Decision` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-111456-investing-protocol-decision.md --status needs-revisit`
- `Review Runtime Protocol Layer Decision` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-015034-runtime-protocol-layer-decision.md --status needs-revisit`
- `Review Single Furnace Product Shell Decision` | priority `medium` | reasons `counter-evidence-candidate` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page wiki/decisions/decision-20260415-111456-single-furnace-product-shell-decision.md --status needs-revisit`

## 最新输出 Packs
- [Decision Memo · Runtime Protocol Layer Decision](../../output/packs/decision-memos/wiki-decisions-decision-20260415-015034-runtime-protocol-layer-decision.md) | kind `Decision Memo` | meta `2026-04-15T01:51:03+00:00`
- [Judgment Memo · Conditional Governance Threshold Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-111455-conditional-governance-threshold-judgment.md) | kind `Decision Memo` | meta `2026-04-15T11:22:01+00:00`
- [Judgment Memo · Protocol Boundary Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-protocol-boundary-judgment.md) | kind `Decision Memo` | meta `2026-04-15T01:51:03+00:00`
- [Judgment Memo · Recurring Agent Layers Judgment](../../output/packs/decision-memos/wiki-judgments-judgment-20260415-015034-recurring-agent-layers-judgment.md) | kind `Decision Memo` | meta `2026-04-15T12:39:25+00:00`
- [Review Pack · Agent Governance Decision](../../output/packs/review/wiki-decisions-decision-20260415-015034-agent-governance-decision.md) | kind `Review Pack` | meta `pending review`
- [Review Pack · Agent Governance Judgment](../../output/packs/review/wiki-judgments-judgment-20260415-015034-agent-governance-judgment.md) | kind `Review Pack` | meta `pending review`
- [SOP Draft · 拆分过载概念 And](../../output/packs/sop-drafts/overloaded-concept-and.md) | kind `SOP Draft` | meta `high`
- [SOP Draft · 拆分过载概念 The](../../output/packs/sop-drafts/overloaded-concept-the.md) | kind `SOP Draft` | meta `high`

## 最近执行回执
- `刷新引用快照 Protocol Boundary Judgment` | kind `apply` | action `refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment` | receipt `output/control/execution-receipts/refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment.json` | at `2026-04-15T09:49:48+00:00`
- `刷新引用快照 Protocol Boundary Judgment` | kind `apply` | action `refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment` | receipt `output/control/execution-receipts/refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment.json` | at `2026-04-15T09:38:52+00:00`
- `刷新引用快照 Protocol Boundary Judgment` | kind `revert` | action `refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment` | receipt `output/control/execution-receipts/refresh-citation-snapshots-judgment-20260415-015034-protocol-boundary-judgment.json` | at `2026-04-15T09:38:52+00:00`

## 最近已审 / 已沉淀
- [Recurring Agent Layers Judgment](../../wiki/judgments/judgment-20260415-015034-recurring-agent-layers-judgment.md) | status `已确认` | reviewed `2026-04-15T12:39:25+00:00`
- [Single Furnace Product Shell Judgment](../../wiki/judgments/judgment-20260415-111456-single-furnace-product-shell-judgment.md) | status `已确认` | reviewed `2026-04-15T11:22:02+00:00`
- [Single Furnace Product Shell Decision](../../wiki/decisions/decision-20260415-111456-single-furnace-product-shell-decision.md) | status `已批准` | reviewed `2026-04-15T11:22:02+00:00`
- [Investing Protocol Decision](../../wiki/decisions/decision-20260415-111456-investing-protocol-decision.md) | status `已批准` | reviewed `2026-04-15T11:22:02+00:00`
- [Investing Layer Separation Judgment](../../wiki/judgments/judgment-20260415-111456-investing-layer-separation-judgment.md) | status `已确认` | reviewed `2026-04-15T11:22:01+00:00`
- [Conditional Governance Threshold Judgment](../../wiki/judgments/judgment-20260415-111455-conditional-governance-threshold-judgment.md) | status `已确认` | reviewed `2026-04-15T11:22:01+00:00`

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
- `output/review/review-center.html`：本地审阅面板（浏览器 / 系统 HTML 入口）
- `output/graph/machine-memory.html`：本地图谱视图（若点开变成 Mihomo/Clash，说明系统接管了 `text/html`）
- `output/control/furnace-center.html`：本地炉心面板（浏览器 / 系统 HTML 入口）
- `output/control/execution-center.html`：本地执行面板（浏览器 / 系统 HTML 入口）
- `output/control/execution-audit.html`：本地执行审计面板（浏览器 / 系统 HTML 入口）
