---
name: verify
description: Local code quality checks. Single source of truth for static verification.
---

Run project-local static checks. Adapt the entry point to your project.

## Entry Point

```bash
bash scripts/verify.sh
```

`verify.sh` is the single source of truth. `deploy_gate.sh` also calls it.

**Important**: `scripts/verify.sh` must exist before running `/verify` or `/deploy-gate`. Create it with your project's linter/formatter/type-check commands. Without it, deploy gate will fail.

## Typical Contents

- Linter (ruff, eslint, go vet, etc.)
- Formatter check (ruff format, prettier, gofmt)
- Compiler / syntax check (py_compile, tsc, go build)
- Type checker (mypy, tsc --noEmit)

## Notes

- Rules should be managed by a shared config file (pyproject.toml, tsconfig.json, etc.)
- This is a local host check, not a container or remote check
- Exclude third-party or generated code
