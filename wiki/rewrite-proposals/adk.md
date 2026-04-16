---
id: "rewrite-proposal-adk"
kind: "rewrite-proposal"
status: "proposed"
title: "Adk"
target_path: "wiki/concepts/adk.md"
source_signature: "7c3ca775a8bd8cbd5f421cbb5bd717fb4b780a36cef671aed6d0880cbfba868e"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T14:24:31+00:00"
---

# Rewrite Proposal · Adk

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
- Target page: `wiki/concepts/adk.md`
- Source signature: `7c3ca775a8bd8cbd5f421cbb5bd717fb4b780a36cef671aed6d0880cbfba868e`
- Source pages: `wiki/sources/discovered-20260415013428-google-adk-agents-overview.md`

## Current Summary Snapshot
- 基于当前唯一证据页，[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)，`ADK` 更像一个围绕 `BaseAgent` 组织 agent runtime 的框架抽象，而不是单一 agent 类型。
- 该页把 ADK agent 分成三类：`LlmAgent` / `Agent` 负责基于 LLM 的推理、规划、响应生成和动态工具选择；workflow agents（`SequentialAgent`、`ParallelAgent`、`LoopAgent`）负责确定性的流程编排；custom agents 直接扩展 `BaseAgent` 以承接定制逻辑或特殊集成。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)
- 当前证据还把 ADK 描述为一种组合式多 agent 组织方式：LLM agents 提供灵活执行，workflow agents 提供可预测流程骨架，custom agents 补足专用能力，重点在组合这些角色而不是只选一种。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)
- 除 agent 分类外，这页还显示 ADK 提供多种能力扩展面：模型替换、artifact 管理、预置 tools / integrations、自定义 tools、plugins、skills 和 lifecycle callbacks。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite adk --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite adk`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite adk`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite adk`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
