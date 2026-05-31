---
name: agentstack-execute-plan
description: Use when an approved AgentStack plan already exists and should be executed in order.
---

# AgentStack Execute Plan

Steps:

1. Read the plan and confirm it matches the current user request.
2. Execute tasks in order.
3. Run the task's targeted verify after meaningful changes.
4. Escalate to debug when verification fails.
5. Escalate to review for L2+ risk or complex diffs.
6. Before any commit or push after plan execution, spawn a separate read-only reviewer/subagent for L2+ or complex diffs.
7. If review findings cause material code changes, re-run targeted verify and repeat review or record why no repeat review is needed.
8. Finish with verification and review evidence.

Stop if the plan is stale, contradictory, or underspecified.
