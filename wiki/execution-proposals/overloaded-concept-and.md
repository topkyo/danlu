---
title: "\u62c6\u5206\u8fc7\u8f7d\u6982\u5ff5 And"
kind: "execution-proposal"
status: "proposed"
action_id: "overloaded-concept-and"
proposal_kind: "split-concept"
risk: "high"
priority: "high"
protocol: "research"
policy_decision: "review"
policy_rule_id: "proposed-triage"
priority_score: "78"
impact_score: "70"
target_paths:
  - "wiki/concepts/and.md"
generated_by: "aiwiki-compile"
last_compiled_at: "2026-04-15T03:10:19+00:00"
---

# 拆分过载概念 And

## Overview
- Action id: `overloaded-concept-and`
- Status: `待处理`
- Kind: `split-concept`
- Risk: `high`
- Protocol: `research`
- Priority: `high`
- Priority score: `78`
- Impact score: `70`
- Policy decision: `review`
- Policy rule: `proposed-triage`
- Targets: `wiki/concepts/and.md`
- Bundle: `output/control/execution-bundles/overloaded-concept-and.json`

## Strategy
- 拆分过载概念，明确子概念边界和来源分流。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Rollback: 回滚时需要人工恢复目标页，然后重跑 compile。

## Suggested Edits
- 先定义更窄的子概念名称和边界。
- 把 source pages 重新分流到更具体的概念页。
- 在原概念页保留拆分说明和跳转链接。
- 如果涉及研发概念，明确 benchmark、experiment、architecture tradeoff 和 regression risk。
- 优先把 next experiment 或 validation path 写清楚。

## Page-Level Patch Plan
- `wiki/concepts/and.md` | role `概念页` | mode `rewrite` | exists `True` | sections `Summary, Related Sources, Related Concepts`
  - 缩窄概念边界、保留拆分说明，并给出后续子概念方向。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
- `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | exists `True` | sections `Merge Candidates, Rewrite Priority`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
- `wiki/indexes/rewrite-proposals.md` | role `索引页` | mode `review` | exists `True` | sections `Merge Candidates, Rewrite Priority`
  - 在概念质量层复核拆分理由和后续子概念候选。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。

## Commands
- Suggested apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action overloaded-concept-and --bundle output/control/execution-bundles/overloaded-concept-and.json`
- Suggested next step: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action overloaded-concept-and --status accepted --note "Accepted for manual repair."`

## Safe Apply Preview
- 当前 proposal 不支持低风险 safe apply。

## Related Links
- [执行中心](../indexes/execution-center.md)
- [机器记忆修复计划](../indexes/machine-memory-repair-plan.md)
- [机器记忆动作队列](../indexes/machine-memory-actions.md)
- [炉心面板](../indexes/furnace-center.md)
- [Execution Bundle](../../output/control/execution-bundles/overloaded-concept-and.json)
