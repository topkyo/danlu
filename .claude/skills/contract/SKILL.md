---
name: contract
description: Freeze goal, scope, approach, and verification before implementation. For multi-file, cross-module, or runtime-affecting tasks.
---

# Sprint Contract

Freeze goal, scope, approach, and verification before writing code.

## When Required

- Multi-file changes
- Config / cross-module logic changes
- Anything affecting runtime behavior, deploy process, or resource budget

## When Optional

- Pure documentation
- Single-file, low-risk, local-only changes

## Output

Write to `.claude/contracts/active.md` using `.claude/contracts/TEMPLATE.md`.

## Rules

- Cross-module, runtime-affecting, or deploy-affecting work should fill `Problem / Context`, `Success Criteria`, `Constraints / Dependencies`, `Chosen Approach`, and `Execution Plan`
- Non-trivial work should also fill `Execution Policy` and `Stop Conditions`; default to `execution_mode: autonomous-closed-loop`, `ask_policy: blockers-only`, `max_debug_rounds: 3`
- Single-file, low-risk work may keep planning sections concise; `N/A` is acceptable where a section truly does not apply
- `In Scope` must be specific to modules or behaviors
- `Out Of Scope` must be explicit to prevent scope creep
- `Questions / Assumptions` must be explicit whenever work proceeds with unknowns
- If public interfaces, data flow, dependencies, or rollback complexity change materially, add an optional ADR using `.claude/contracts/ADR-TEMPLATE.md` and commit it under `docs/adr/` or the project's equivalent
- `Gate Artifacts` paths are live config for the scripts, not comment-only docs; keep them under `.claude/gates/*.md`
- `Gate Requirements`:
  - `verify`: required (guardrail)
  - `qa-review`: required or not-required (scaffolding)
  - `qa-runtime`: required or not-required
- `Stop Conditions` should state when to stop autonomous execution and ask the user instead of continuing local iteration
- `Fail Gate` must be a testable condition
