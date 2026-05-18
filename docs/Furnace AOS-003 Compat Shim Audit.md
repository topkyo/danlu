# Furnace AOS-003 Compat Shim Audit

Scope: AOS-003 `Kernel shim retirement and hub slimming`.

Decision: retire only private `aiwiki.app_memory_surfaces` query-helper re-export paths in this milestone. Keep public/tested facade seams stable.

## Classification

| Path / surface | Owner | Classification | Decision |
| --- | --- | --- | --- |
| `src/aiwiki/app.py` | static compatibility shim | `keep-stable` | In-tree usage is weak, but README commits to the `aiwiki.app` external import surface. Do not retire in AOS-003. |
| `src/aiwiki/app_content.py` | `aiwiki.content.*`, lifecycle/render owners | `keep-stable` / `split-later` | Still used by runtime, scripts, and tests. No safe whole-file retirement candidate. |
| `src/aiwiki/app_compile.py` | compile / ask / review / nightly orchestration | `keep-stable` / `split-later` | Legacy owner, not a dead facade. Still used by runner/tests; large-hub extraction is out of AOS-003 scope. |
| `src/aiwiki/app_memory_surfaces.py` public/tested symbols | `aiwiki.memory.*`, `aiwiki.app_memory_query` | `keep-stable` | Still supports public imports and tested patch seams such as `build_machine_memory_query_routes` and `render_machine_memory_graph_html`. |
| `aiwiki.app_memory_surfaces._machine_memory_query_payload_hash` | `aiwiki.app_memory_query` | `delete-now` | Private underscore helper, no repo evidence of imports through `app_memory_surfaces`; owner path remains available. |
| `aiwiki.app_memory_surfaces._route_anchor_candidates` | `aiwiki.app_memory_query` | `delete-now` | Private underscore helper, no repo evidence of imports through `app_memory_surfaces`; owner path remains available. |
| `src/aiwiki/app_memory.py` lazy owner map for private query helpers | `aiwiki.app_memory_query` | `split-later` | Looks removable later, but it is a second facade surface. AOS-003 keeps it stable to avoid widening the first slimming step. |

## Reference evidence

- Repo search found public `app_memory_surfaces` consumers for `render_machine_memory_graph_html` and the tested patch seam `aiwiki.app_memory_surfaces.build_machine_memory_query_routes`.
- Repo search found no in-tree imports or qualified access for `aiwiki.app_memory_surfaces._machine_memory_query_payload_hash` or `aiwiki.app_memory_surfaces._route_anchor_candidates`.
- The real definitions remain in `src/aiwiki/app_memory_query.py`; internal owner usage continues through direct owner imports.
- No Product Shell, acceptance, dogfood, CLI, receipt, audit, or revert schema path depends on the removed private facade bindings.

## Net complexity change

- Removed two obsolete private re-export bindings from a compatibility facade.
- Kept the public/tested facade surface stable.
- Clarified the module comment so future code imports private query helpers from `aiwiki.app_memory_query` directly instead of adding new facade seams.
