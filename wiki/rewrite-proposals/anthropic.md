---
id: "rewrite-proposal-anthropic"
kind: "rewrite-proposal"
status: "proposed"
title: "Anthropic"
target_path: "wiki/concepts/anthropic.md"
source_signature: "497d7197a1644bb538bf7ec6c68553d71137bb90c7be3b537ba19bcd1b91fe43"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T14:24:31+00:00"
---

# Rewrite Proposal · Anthropic

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `6`
- Quality score: `76`
- Quality band: `stable`
- Apply ready: `False`
- First proposed: `2026-04-15T01:37:58+00:00`
- Last proposed: `2026-04-16T14:24:31+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/anthropic.md`
- Source signature: `497d7197a1644bb538bf7ec6c68553d71137bb90c7be3b537ba19bcd1b91fe43`
- Source pages: `wiki/sources/discovered-20260415013334-anthropic-tool-use-overview.md`

## Current Summary Snapshot
- 当前概念汇总了 `1` 个 source page：[Anthropic Tool Use Overview](../sources/discovered-20260415013334-anthropic-tool-use-overview.md)。
- 当前最直接的线索：This source is an Anthropic overview page for Claude tool use. The extracted content frames tool use as a mechanism where Claude can invoke either user-defined functions or Anthropic-provided tools,…
- 这还是单来源概念页；继续补充证据、冲突和例外后再升级为更硬的判断。

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite anthropic --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite anthropic`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite anthropic`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite anthropic`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
