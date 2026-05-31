---
name: agentstack-devloop
description: "Use for small scoped code changes: orient, edit, targeted verify, and finish."
---

# AgentStack Devloop

Use this skill for L1 coding tasks.

Steps:

1. Read relevant repo instructions and test entrypoints.
2. Keep the edit scoped to the user request.
3. Run `scripts/agentstack-verify --target auto` when code changed.
4. If verification fails, record the focused attempt with `scripts/agentstack iteration`, then fix one hypothesis at a time or escalate to debug.
5. Finish with changes, verify result, risks, and follow-ups.

Skip this skill when the requirement is ambiguous enough for `agentstack-brainstorming` or when an approved plan should use `agentstack-execute-plan`.
