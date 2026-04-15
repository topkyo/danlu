---
id: "rewrite-proposal-agentic"
kind: "rewrite-proposal"
status: "proposed"
title: "Agentic"
target_path: "wiki/concepts/agentic.md"
source_signature: "2921a14fec04ee48b4a5e95b8d01a56cd04af86c28aa6184d328cdc9391be385"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-15T09:19:10+00:00"
---

# Rewrite Proposal · Agentic

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `6`
- Quality score: `78`
- Quality band: `stable`
- Apply ready: `False`
- First proposed: `2026-04-15T03:10:19+00:00`
- Last proposed: `2026-04-15T09:19:10+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/agentic.md`
- Source signature: `2921a14fec04ee48b4a5e95b8d01a56cd04af86c28aa6184d328cdc9391be385`
- Source pages: `wiki/sources/discovered-20260415013411-langgraph-agentic-concepts.md`

## Current Summary Snapshot
- 当前仓库里，`agentic` 只被一个来源页明确点名：[`wiki/sources/discovered-20260415013411-langgraph-agentic-concepts.md`](../sources/discovered-20260415013411-langgraph-agentic-concepts.md)。
- 该来源页能确认的事实只有：LangGraph 存在一个标题为 `LangGraph Agentic Concepts` 的页面，抓取时 HTTP 状态为 `200`，但保存下来的正文只有 `Redirecting...`，没有保留实际概念说明、示例或设计 guidance。见 [`wiki/sources/discovered-20260415013411-langgraph-agentic-concepts.md`](../sources/discovered-20260415013411-langgraph-agentic-concepts.md)。
- 因此，本页目前只能把 `agentic` 记录为“LangGraph 文档中的一个概念入口”，不能把常见业界对 agentic system 的含义直接写成这里的已证实结论。

## Rewrite Strategy
- Issues: `soft-hardness, single-source, evidence-gap, merge-boundary`
- Strategy: 保留证据缺口和不确定性，避免过强结论。 保持保守措辞，并指出还缺哪些来源。 检查是否需要合并或拆分概念边界。

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite agentic --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite agentic`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite agentic`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite agentic`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
