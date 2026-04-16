# 概念质量

- 最近编译时间：`2026-04-16T02:08:48+00:00`
- 弱概念页：`30`
- 稳定概念页：`0`
- 占位概念页：`0`
- 合并候选：`12`
- 重写候选：`30`
- 冲突信号：`2`
- 证据缺口：`44`
- 平均质量分：`80.0`
- Quality bands： strong `8` / stable `20` / watch `2` / fragile `0`
- Hardness： hard `2` / medium `3` / soft `25`
- Rewrite 提案：`12`
- 待审提案：`12`
- 可应用提案：`0`
- 已验证提案：`0`
- 可回滚提案：`0`

## Hard Concepts
- [Protocol](../concepts/protocol.md) | hardness `hard` | confidence `medium` | sources `4` | quality `86`
- [Agents](../concepts/agents.md) | hardness `hard` | confidence `medium` | sources `3` | quality `93`
- [Memory](../concepts/memory.md) | hardness `medium` | confidence `medium` | sources `5` | quality `90`
- [Judgment](../concepts/judgment.md) | hardness `medium` | confidence `medium` | sources `3` | quality `93`
- [Abstract](../concepts/abstract.md) | hardness `medium` | confidence `medium` | sources `3` | quality `90`

## Rewrite Now
- [And](../concepts/and.md) | hardness `soft` | issues `soft-hardness, conflicting-source-signals, evidence-gap` | sources `8` | related `6` | quality `64` | band `watch`
  - metrics: coverage `100` / consistency `65` / evidence `2` / recency `100`
- [The](../concepts/the.md) | hardness `soft` | issues `soft-hardness, conflicting-source-signals, evidence-gap` | sources `12` | related `6` | quality `64` | band `watch`
  - metrics: coverage `100` / consistency `65` / evidence `0` / recency `100`
- [Autogen Multi Agent](../concepts/autogen-multi-agent.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `76` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `85`
- [A2a](../concepts/a2a.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [A2a Key Concepts](../concepts/a2a-key-concepts.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Adk](../concepts/adk.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Agentic](../concepts/agentic.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Anthropic](../concepts/anthropic.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `2` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Anthropic Tool Use](../concepts/anthropic-tool-use.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `2` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Google Adk Agents](../concepts/google-adk-agents.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Langgraph](../concepts/langgraph.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`
- [Langgraph Agentic Concepts](../concepts/langgraph-agentic-concepts.md) | hardness `soft` | issues `soft-hardness, single-source, evidence-gap, merge-boundary` | sources `1` | related `4` | quality `78` | band `stable`
  - metrics: coverage `35` / consistency `100` / evidence `86` / recency `100`

## Quality Distribution
- Strong / Stable / Watch / Fragile： `8` / `20` / `2` / `0`

## Rewrite Priority
- [And](../concepts/and.md) | priority `high` | score `6` | quality `64` | band `watch` | issues `soft-hardness, conflicting-source-signals, evidence-gap`
  - strategy: 并列呈现冲突来源，明确分歧和适用边界。 保留证据缺口和不确定性，避免过强结论。
- [The](../concepts/the.md) | priority `high` | score `6` | quality `64` | band `watch` | issues `soft-hardness, conflicting-source-signals, evidence-gap`
  - strategy: 并列呈现冲突来源，明确分歧和适用边界。 保留证据缺口和不确定性，避免过强结论。
- [Autogen Multi Agent](../concepts/autogen-multi-agent.md) | priority `high` | score `6` | quality `76` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [A2a](../concepts/a2a.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [A2a Key Concepts](../concepts/a2a-key-concepts.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Adk](../concepts/adk.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Agentic](../concepts/agentic.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Anthropic](../concepts/anthropic.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Anthropic Tool Use](../concepts/anthropic-tool-use.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Google Adk Agents](../concepts/google-adk-agents.md) | priority `high` | score `6` | quality `78` | band `stable` | issues `soft-hardness, single-source, evidence-gap, merge-boundary`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。

## Rewrite Proposals
- [A2a](../rewrite-proposals/a2a.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [A2a Key Concepts](../rewrite-proposals/a2a-key-concepts.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Adk](../rewrite-proposals/adk.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Agentic](../rewrite-proposals/agentic.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [And](../rewrite-proposals/and.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 并列呈现冲突来源，明确分歧和适用边界。 保留证据缺口和不确定性，避免过强结论。
- [Anthropic](../rewrite-proposals/anthropic.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Anthropic Tool Use](../rewrite-proposals/anthropic-tool-use.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Autogen Multi Agent](../rewrite-proposals/autogen-multi-agent.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Google Adk Agents](../rewrite-proposals/google-adk-agents.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。
- [Langgraph](../rewrite-proposals/langgraph.md) | status `待审提案` | priority `high` | apply_ready `False` | verification `pending`
  - strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。

## Conflict Signals
- [And](../concepts/and.md) | signal `benefit-vs-risk` | sources `wiki/sources/discovered-20260415013128-building-effective-agents.md, wiki/sources/discovered-20260415013329-react-paper-abstract.md`
- [The](../concepts/the.md) | signal `benefit-vs-risk` | sources `wiki/sources/discovered-20260415013128-building-effective-agents.md, wiki/sources/discovered-20260415013329-react-paper-abstract.md`

## Evidence Gaps
- [A2A Key Concepts](../concepts/a2a.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` | markers `incomplete, partial`
- [A2A Key Concepts](../concepts/a2a-key-concepts.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` | markers `incomplete, partial`
- [A2A Key Concepts](../concepts/concepts.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` | markers `incomplete, partial`
- [A2A Key Concepts](../concepts/memory.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` | markers `incomplete, partial`
- [A2A Key Concepts](../concepts/protocol.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013529-a2a-key-concepts.md` | markers `incomplete, partial`
- [Anthropic Tool Use Overview](../concepts/anthropic.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013334-anthropic-tool-use-overview.md` | markers `truncated`
- [Anthropic Tool Use Overview](../concepts/anthropic-tool-use.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013334-anthropic-tool-use-overview.md` | markers `truncated`
- [Anthropic Tool Use Overview](../concepts/the.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013334-anthropic-tool-use-overview.md` | markers `truncated`
- [AutoGen Multi Agent Debate Pattern](../concepts/agent.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md` | markers `incomplete, partial, truncated, weak`
- [AutoGen Multi Agent Debate Pattern](../concepts/and.md) | kind `evidence-gap` | source `wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md` | markers `incomplete, partial, truncated, weak`

## Merge Candidates
- [A2a](../concepts/a2a.md) <-> [A2a Key Concepts](../concepts/a2a-key-concepts.md) | shared_sources `1` | shared_tokens `a2a`
- [A2a Key Concepts](../concepts/a2a-key-concepts.md) <-> [Concepts](../concepts/concepts.md) | shared_sources `1` | shared_tokens `concepts`
- [Adk](../concepts/adk.md) <-> [Google Adk Agents](../concepts/google-adk-agents.md) | shared_sources `1` | shared_tokens `adk`
- [Agent](../concepts/agent.md) <-> [Autogen Multi Agent](../concepts/autogen-multi-agent.md) | shared_sources `1` | shared_tokens `agent`
- [Agentic](../concepts/agentic.md) <-> [Langgraph Agentic Concepts](../concepts/langgraph-agentic-concepts.md) | shared_sources `1` | shared_tokens `agentic`
- [Agents](../concepts/agents.md) <-> [Building Effective Agents](../concepts/building-effective-agents.md) | shared_sources `1` | shared_tokens `agents`
- [Agents](../concepts/agents.md) <-> [Google Adk Agents](../concepts/google-adk-agents.md) | shared_sources `1` | shared_tokens `agents`
- [Anthropic](../concepts/anthropic.md) <-> [Anthropic Tool Use](../concepts/anthropic-tool-use.md) | shared_sources `1` | shared_tokens `anthropic`
- [Building Effective Agents](../concepts/building-effective-agents.md) <-> [Effective](../concepts/effective.md) | shared_sources `1` | shared_tokens `effective`
- [Concepts](../concepts/concepts.md) <-> [Langgraph Agentic Concepts](../concepts/langgraph-agentic-concepts.md) | shared_sources `1` | shared_tokens `concepts`

## Stable Concepts
- 当前还没有稳定概念页。

## 相关链接
- [概念索引](./concepts.md)
- [机器记忆](./machine-memory.md)
- [动作队列](./machine-memory-actions.md)
- [修复计划](./machine-memory-repair-plan.md)
- [Rewrite Proposals](./rewrite-proposals.md)
- [修复待办](./repair-backlog.md)
