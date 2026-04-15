# 协议总览

- 最近编译时间：`2026-04-15T02:19:57+00:00`
- 当前 active protocol：`research` (研发协议)
- 协议总数：`5`
- 状态文件：`.aiwiki/state/protocol.json`
- lifecycle concept backlog / retired：`30` / `0`
- 切换命令：`PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-set <slug>`

## 当前协议入口
- [schema/protocols/research/index.md](../../schema/protocols/research/index.md)
- [schema/protocols/research/taxonomy.md](../../schema/protocols/research/taxonomy.md)
- [schema/protocols/research/decision.md](../../schema/protocols/research/decision.md)
- [schema/protocols/research/judgment.md](../../schema/protocols/research/judgment.md)
- [schema/protocols/research/review.md](../../schema/protocols/research/review.md)
- [schema/protocols/research/nightly.md](../../schema/protocols/research/nightly.md)
- [schema/protocols/research/query.md](../../schema/protocols/research/query.md)

## 可用协议
- [通用协议](../../schema/protocols/general/index.md) | slug `general` | 默认的跨域协议，适合把事实、综合、判断和复审保持分层。
- [投资协议](../../schema/protocols/investing/index.md) | slug `investing` | 面向 thesis、risk、catalyst、invalidation 和 position decision 的协议。
- [运维协议](../../schema/protocols/ops/index.md) | slug `ops` | 面向 incident、runbook、mitigation、escalation 和 follow-up 的协议。
- [产品协议](../../schema/protocols/product/index.md) | slug `product` | 面向 user problem、insight、bet、metric 和 launch judgment 的协议。
- [研发协议](../../schema/protocols/research/index.md) | slug `research` | 面向 paper、repo、benchmark、experiment 和 architecture decision 的协议。

## Lifecycle Governance Summary
- 以下 lifecycle backlog 是全局 knowledge plane 工作面，按当前 active protocol 排序，不伪装成 protocol-specific 指标。
- review concepts：`2`
- revisit concepts：`28`
- retired concepts：`0`
- active concepts：`0`

## Lifecycle Concept Backlog
- [And](../../wiki/concepts/and.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [The](../../wiki/concepts/the.md) | kind `concept` | state `待回看` | invalidation `concept-conflict,concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-conflict,concept-evidence-gap`
- [Abstract](../../wiki/concepts/abstract.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agent](../../wiki/concepts/agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Agents](../../wiki/concepts/agents.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Autogen Multi Agent](../../wiki/concepts/autogen-multi-agent.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Concept](../../wiki/concepts/concept.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Crewai](../../wiki/concepts/crewai.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Crewai Agents Concept](../../wiki/concepts/crewai-agents-concept.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `rewrite-proposal-proposed,active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`
- [Debate](../../wiki/concepts/debate.md) | kind `concept` | state `待回看` | invalidation `concept-evidence-gap` | active_corpora `7` | review_signals `active-quality-pressure` | reasons `invalidation-signal,concept-evidence-gap`

## Retired Concepts
- 当前没有 retired concept。

## 运行原则
- 统一 runtime，不复制多个炉子。
- 领域差异优先落在 `schema/protocols/`。
- 查询、回流和审阅默认沿当前 active protocol 执行，但 page frontmatter 会保留显式 protocol 字段。

## 当前协议语义
- 默认协议：`research` (研发协议)
- Review window overrides:
  - `decision:needs-revisit` -> revisit `2`d / escalate `7`d
  - `decision:proposed` -> revisit `5`d / escalate `14`d
  - `judgment:tentative` -> revisit `4`d / escalate `10`d
  - `judgment:tracking` -> revisit `7`d / escalate `21`d
- Auto-promotion 标题前缀：decision `研发决策沉淀` / judgment `研发判断沉淀`
- Review focus：`重点审 regression、benchmark drift、过期实验结论和架构取舍。 / 待确认实验结论保留更高 revisit 频率。`
- Nightly focus：`优先抬升 weak concepts、failed experiments、regression signals。 / 把 recurring outputs 晋升成 architecture decision 或 engineering judgment。`
