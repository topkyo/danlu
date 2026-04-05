# Verify

Local code quality check entry point.

```bash
bash scripts/verify.sh
```

`verify.sh` is the single source of truth. `deploy_gate.sh` also calls it.
Adapt contents (linter, formatter, type checker) to your project's toolchain.
