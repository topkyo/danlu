# Contract

Freeze goal, scope, approach, and verification before implementation.

## When Required
- Multi-file changes
- Config / cross-module logic changes
- Anything affecting runtime behavior or deploy

## When Optional
- Pure documentation
- Single-file, low-risk, local-only changes

## Output
Write to `.codex/contracts/active.md` using `.codex/contracts/TEMPLATE.md`.

## Rules
- Cross-module, runtime-affecting, or deploy-affecting work should fill `Problem / Context`, `Success Criteria`, `Constraints / Dependencies`, `Chosen Approach`, and `Execution Plan`
- Non-trivial work should also fill `Execution Policy` and `Stop Conditions`; the default is `execution_mode: autonomous-closed-loop`, `ask_policy: blockers-only`, `max_debug_rounds: 3`
- Single-file, low-risk work may keep planning sections concise; `N/A` is acceptable where a section truly does not apply
- `In Scope` must be specific
- `Out Of Scope` must be explicit
- `Questions / Assumptions` must be explicit whenever work proceeds with unknowns
- If public interfaces, data flow, dependencies, or rollback complexity change materially, add an optional ADR using `.codex/contracts/ADR-TEMPLATE.md` and commit it under `docs/adr/` or the project's equivalent
- `Fail Gate` must be testable
- `Gate Requirements` must declare:
  - `verify`: required (guardrail, cannot be not-required)
  - `qa-review`: required or not-required (scaffolding)
  - `qa-runtime`: required or not-required (guardrail, but pure-doc changes may skip)
- `Gate Artifacts` defaults:
  - `qa-review`: `.codex/gates/qa-review.md`
  - `qa-runtime`: `.codex/gates/qa-runtime.md`
  Scripts read these paths from the contract. Keep custom paths under `.codex/gates/*.md`.
- `Stop Conditions` should include when to stop autonomous execution and ask the user instead of continuing local iteration
