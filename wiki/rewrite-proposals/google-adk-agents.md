---
id: "rewrite-proposal-google-adk-agents"
kind: "rewrite-proposal"
status: "proposed"
title: "Google Adk Agents"
target_path: "wiki/concepts/google-adk-agents.md"
source_signature: "568cc14723922355e03151b1cb36900ddc50ae3605a35ee7473206c296fa27eb"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T02:08:48+00:00"
---

# Rewrite Proposal · Google Adk Agents

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `6`
- Quality score: `78`
- Quality band: `stable`
- Apply ready: `False`
- First proposed: `2026-04-15T01:49:42+00:00`
- Last proposed: `2026-04-16T02:08:48+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/google-adk-agents.md`
- Source signature: `568cc14723922355e03151b1cb36900ddc50ae3605a35ee7473206c296fa27eb`
- Source pages: `wiki/sources/discovered-20260415013428-google-adk-agents-overview.md`

## Current Summary Snapshot
- 基于当前唯一证据页，[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)，`Google ADK agents` 更适合理解为 ADK 围绕 `BaseAgent` 提供的一组 agent 类型与组合模式，而不是某一个单独的具体类。该页把 ADK agent 定义为可自主达成目标、可与用户交互、可使用外部工具、也可与其他 agents 协作的自包含执行单元。
- 当前证据支持一个三分法。`LlmAgent` / `Agent` 被描述为以 LLM 为核心引擎的 agent，用于自然语言理解、推理、规划、响应生成和动态工具选择；workflow agents（`SequentialAgent`、`ParallelAgent`、`LoopAgent`）负责以顺序、并行或循环等确定性模式编排其他 agents，并且流程控制本身不依赖 LLM；custom agents 则通过直接扩展 `BaseAgent` 来承接标准类型之外的定制逻辑、控制流或集成需求。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)
- 这页最稳定的综合结论不是“哪一种 agent 最重要”，而是 ADK 把多 agent 系统表达为角色组合：LLM agents 负责更灵活的语言型任务执行，workflow agents 负责可预测的流程骨架，custom agents 负责专用能力或特殊规则。换言之，ADK 在这里强调的是组合式架构，而不是互斥式类型选择。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)
- 当前来源还把 `Google ADK agents` 放在一个可扩展 runtime 视角下理解：除了 agent 类型本身，ADK 还提供模型替换、artifacts、预置 tools / integrations、自定义 tools、plugins、skills 和 callbacks 等扩展面，用来增强 agent 能力与执行生命周期中的可插入行为。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)
- 证据边界必须保持显式。现有来源是 overview page，不是详细 API 文档；它提到了高层 comparison table 和后续细分页面，但抓取内容没有包含表格细节、配置差异、实现约束、性能对比或最佳实践。因此，这个 concept page 目前只能稳定承载 taxonomy 和 architecture-shape 层面的综合，不能把每类 agent 的具体行为、默认设置或适用边界写成强事实。[Google ADK Agents Overview](../sources/discovered-20260415013428-google-adk-agents-overview.md)

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite google-adk-agents --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite google-adk-agents`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite google-adk-agents`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite google-adk-agents`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
