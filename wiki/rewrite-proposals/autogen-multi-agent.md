---
id: "rewrite-proposal-autogen-multi-agent"
kind: "rewrite-proposal"
status: "proposed"
title: "Autogen Multi Agent"
target_path: "wiki/concepts/autogen-multi-agent.md"
source_signature: "99700057476935ddecec83f53b627a853eb60c3bbfe5526afbe54ca3c36b7087"
generated_by: "aiwiki-run-compile"
last_compiled_at: "2026-04-16T02:08:48+00:00"
---

# Rewrite Proposal · Autogen Multi Agent

## Proposal Status
- Status: `待审提案`
- Priority: `high`
- Score: `6`
- Quality score: `76`
- Quality band: `stable`
- Apply ready: `False`
- First proposed: `2026-04-15T01:37:58+00:00`
- Last proposed: `2026-04-16T02:08:48+00:00`
- Reviewed at: `none`
- Applied at: `none`
- Reverted at: `none`

## Target
- Target page: `wiki/concepts/autogen-multi-agent.md`
- Source signature: `99700057476935ddecec83f53b627a853eb60c3bbfe5526afbe54ca3c36b7087`
- Source pages: `wiki/sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md`

## Current Summary Snapshot
- 当前证据把 `Autogen Multi Agent` 指向 AutoGen 框架中的一种多智能体协作模式：多个 solver agent 围绕同一个问题进行多轮推理交换，再由一个 aggregator agent 收集最终答案并按多数票产出结果。[AutoGen Multi Agent Debate Pattern](../sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)
- 这页更像是一个“实现型设计模式”而不是被验证过的通用能力结论。来源重点在消息拓扑、topic/subscription 机制、轮次控制和 runtime 组织方式，而不是系统 benchmark 或泛化效果。[AutoGen Multi Agent Debate Pattern](../sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)
- 现有来源只明确展示了一个 math problem worked example：四个 solver 最终都得到 `72`，aggregator 再输出 `72`。这说明端到端流程可运行，但不足以证明 multi-agent debate 在准确率、鲁棒性或成本上优于其他方案。[AutoGen Multi Agent Debate Pattern](../sources/discovered-20260415013331-autogen-multi-agent-debate-pattern.md)

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
- Review: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite autogen-multi-agent --status accepted`
- Apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite autogen-multi-agent`
- Verify: `PYTHONPATH=src python3 -m aiwiki.cli --root . verify-rewrite autogen-multi-agent`
- Revert: `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-rewrite autogen-multi-agent`

## Proposed Markdown
- 当前还没有生成候选重写内容。先运行 `run-compile`。
