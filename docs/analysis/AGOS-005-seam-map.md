# AGOS-005 Runtime Hub Seam Map

> Targeted slimming map for AGOS-005. No broad refactor.

## Priority order (ROI × blast radius)

| Rank | Module | ~LOC | Risk | First extraction candidate |
|------|--------|------|------|---------------------------|
| 1 | `runner/workflows.py` | 2772 | high | `runner/local_stats.py` — markdown/elixir local intent stats |
| 2 | `runner/alchemy.py` | 2589 | high | lane primitive receipt helpers (deferred) |
| 3 | `app_surfaces.py` | 1798 | medium | compile status link helpers (AOS-005a partial) |
| 4 | `app_protocol.py` | 1999 | high | do not touch without contract |
| 5 | `memory/execution_surfaces.py` | 1329 | medium | concept quality render helpers |

## Completed / in-flight

- AOS-005a: `app_surfaces` helper extraction + facade import cleanup
- AOS-006 signals adapter slim
- AGOS-006: `planner/log_writer.py` budget_hint routing
- AGOS-007: `llm_telemetry.py` aggregation module

## Facade rule

`app.py` remains compatibility shim. New business logic must not enter `app_surfaces` / `app_compile` facades; add owner module + tests.
