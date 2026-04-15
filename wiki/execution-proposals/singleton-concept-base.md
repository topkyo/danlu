---
title: "\u6269\u5c55\u5355\u8282\u70b9\u6982\u5ff5 Base"
kind: "execution-proposal"
status: "proposed"
action_id: "singleton-concept-base"
proposal_kind: "expand-concept"
risk: "medium"
priority: "medium"
protocol: "research"
policy_decision: "review"
policy_rule_id: "proposed-triage"
priority_score: "61"
impact_score: "53"
target_paths:
  - "wiki/concepts/base.md"
generated_by: "aiwiki-compile"
last_compiled_at: "2026-04-15T02:19:57+00:00"
---

# 扩展单节点概念 Base

## Overview
- Action id: `singleton-concept-base`
- Status: `待处理`
- Kind: `expand-concept`
- Risk: `medium`
- Protocol: `research`
- Priority: `medium`
- Priority score: `61`
- Impact score: `53`
- Policy decision: `review`
- Policy rule: `proposed-triage`
- Targets: `wiki/concepts/base.md`
- Bundle: `output/control/execution-bundles/singleton-concept-base.json`

## Strategy
- 扩展单节点概念的来源覆盖或相关概念边界。 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。
- Rollback: 回滚时需要人工恢复目标页，然后重跑 compile。

## Suggested Edits
- 补更多来源或相关概念反链。
- 重写摘要时强调当前证据仍然有限。
- 如果概念过窄，考虑降级为 source-specific note。
- 如果涉及研发概念，明确 benchmark、experiment、architecture tradeoff 和 regression risk。
- 优先把 next experiment 或 validation path 写清楚。

## Page-Level Patch Plan
- `wiki/concepts/base.md` | role `概念页` | mode `update` | exists `True` | sections `Summary, Related Sources, Related Concepts`
  - 补来源覆盖、显式有限证据，并更新相关概念边界。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。
- `wiki/indexes/concept-quality.md` | role `索引页` | mode `review` | exists `True` | sections `Rewrite Priority, Open Questions`
  - 在概念质量和索引层确认是否需要持续重写或补料。 同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。

## Commands
- Suggested apply: `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action singleton-concept-base --bundle output/control/execution-bundles/singleton-concept-base.json`
- Suggested next step: `PYTHONPATH=src python3 -m aiwiki.cli --root . review-action singleton-concept-base --status accepted --note "Accepted for manual repair."`

## Safe Apply Preview
- 当前 proposal 不支持低风险 safe apply。

## Related Links
- [执行中心](../indexes/execution-center.md)
- [机器记忆修复计划](../indexes/machine-memory-repair-plan.md)
- [机器记忆动作队列](../indexes/machine-memory-actions.md)
- [炉心面板](../indexes/furnace-center.md)
- [Execution Bundle](../../output/control/execution-bundles/singleton-concept-base.json)
