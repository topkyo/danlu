# Codex Harness

Codex harness artifact root for this project.

## Principles

- Guardrails always, scaffolding as needed
- Calibration-driven degradation
- Stage-scoped workflow loading
- Same gate scripts as Claude, different artifact root

### Guardrails
- `verify.sh` — deterministic static checks
- `qa-runtime` — empirical behavior verification (per contract)
- `deploy-gate` — boundary enforcement

### Scaffolding
- `contract` — prevent scope drift and capture lightweight context, approach, and plan
- `qa-review` — prevent generator bias, preferably with an isolated reviewer
- `PROGRESS.md` — prevent cross-session amnesia

## Directory

- `contracts/`: enhanced sprint contract template, optional ADR template, and active contract
- `gates/`: qa-review / qa-runtime gate artifacts
- `workflows/`: stage runbooks

## Entry Points

```bash
HARNESS_DIR=.codex bash scripts/write_gate_artifact.sh qa-review --status pass --summary "no findings" --reviewer-mode same-context --reviewer-fallback-reason "isolated reviewer unavailable"
```

Strict tiers additionally expose:

```bash
HARNESS_DIR=.codex bash scripts/deploy_gate.sh
HARNESS_DIR=.codex bash scripts/deploy_with_gate.sh
```

`verify.sh` is shared and does not need HARNESS_DIR.

Architecture-grade changes may add a committed ADR using `.codex/contracts/ADR-TEMPLATE.md`.

Load only the workflow needed for the current stage. Do not preload every harness workflow into one long-running context.
