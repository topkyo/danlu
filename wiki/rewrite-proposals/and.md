---
id: "rewrite-proposal-and"
kind: "rewrite-proposal"
status: "proposed"
title: "And"
target_path: "wiki/concepts/and.md"
source_signature: "e1f9f03997b0754828731a58a1ab44e70a26b835c64b3620e3d713b16e7aee6f"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-15T03:37:27+00:00"
---

# Rewrite Proposal · And

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `5`
- Quality score: `64`
- Quality band: `watch`
- Apply ready: `False`
- First proposed: `2026-04-15T01:54:06+00:00`
- Last proposed: `2026-04-15T03:37:27+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/and.md`
- Source signature: `e1f9f03997b0754828731a58a1ab44e70a26b835c64b3620e3d713b16e7aee6f`
- Source pages: `wiki/sources/discovered-20260415013128-building-effective-agents.md, wiki/sources/discovered-20260415013329-react-paper-abstract.md, wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md, wiki/sources/discovered-20260415013344-model-context-protocol-introduction.md, wiki/sources/discovered-20260415013427-voyager-paper-abstract.md, wiki/sources/discovered-20260415013428-google-adk-agents-overview.md, wiki/sources/discovered-20260415013529-a2a-key-concepts.md, wiki/sources/discovered-20260415013612-crewai-agents-concept.md`

## Current Summary Snapshot
当前证据不支持 `And` 作为一个独立、稳定、可操作的 research concept。更可信的解释是：它是概念抽取过程把高频连接词误提升为 concept page 的结果。八个来源里，`and` 的主要作用都是把两个或多个机制、角色或能力并列起来，而不是指向一套单独的方法、协议或系统。（[Building Effective Agents](../sources/discovered-20260415013128-building-effective-agents.md), [ReAct Paper Abstract](../sources/discovered-20260415013329-react-paper-abstract.md), [AutoGen Multi Agent Debate Pattern](../sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md), [Model Context Protocol Introduction](../sources/discovered-20260415013344-model-context-protocol-introduction.md), [Voyager Paper Abstract](../sources/discovered-20260415013427-voyager-paper-abstract.md), [Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md), [A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md), [CrewAI Agents Concept](../sources/discovered-20260415013612-crewai-agents-concept.md)）

如果强行保留本页，当前最稳妥的综合只能是：这些来源反复强调 agent 系统往往由“X and Y”的组合关系构成，例如 reasoning and acting、planning and tool use、 deterministic workflow and model-driven autonomy、client and server、memory and tools、single-agent execution and multi-agent coordination。`and` 在这里更像“组合性”或“并置关系”的语言信号，而不是一个应单独建页的概念。（[ReAct Paper Abstract](../sources/discovered-20260415013329-react-paper-abstract.md), [Building Effective Agents](../sources/discovered-20260415013128-building-effective-agents.md), [Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md), [A2A Key Concepts](../sources/discovered-20260415013529-a2a-key-concepts.md), [CrewAI Agents Concept](../sources/discovered-20260415013612-crewai-agents-concept.md)）

## Rewrite Strategy
- Issues: `conflicting-source-signals, evidence-gap`
- Strategy: 并列呈现冲突来源，明确分歧和适用边界。 保留证据缺口和不确定性，避免过强结论。

## Verification
- Status: `not-run`
- Checked at: `none`
- Summary: Verification has not run yet.
- Issues: `none`

## Rollback
- Previous snapshot available: `False`
- Last applied at: `none`
- Revert note: none

## Commands
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite and --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite and`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite and`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite and`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
