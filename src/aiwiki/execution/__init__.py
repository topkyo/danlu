"""Execution owner subpackage (炼丹炉 scoped primitives).

EP-018B migration is complete. Each execution-layer function now has a
dedicated owner module in this subpackage:

- :mod:`aiwiki.execution.ask`              — ``ask_question`` / ``file_back``
- :mod:`aiwiki.execution.candidates`       — output candidate promote/demote
- :mod:`aiwiki.execution.lifecycle`        — concept retire/reactivate +
                                              knowledge-lifecycle runtime
- :mod:`aiwiki.execution.concept_rewrite`  — ``apply-rewrite`` / ``revert-rewrite``
- :mod:`aiwiki.execution.archive`          — ``apply-archive`` / ``revert-archive``
- :mod:`aiwiki.execution.machine_memory_actions` — ``apply-action`` / ``revert-action``
- :mod:`aiwiki.execution.machine_memory_batch`   — nightly batch orchestration
- :mod:`aiwiki.execution.review`           — ``review`` primitive
- :mod:`aiwiki.execution.alchemy`          — ``alchemy-start/distill/finalize/promote/revert/demote``
- :mod:`aiwiki.execution.l3_proposals`     — manual L3 proposal lifecycle + generation preview
- :mod:`aiwiki.execution.audit_preview`    — universal audit stream read-only preview
- :mod:`aiwiki.execution.runtime_surfaces` — runtime primitive surfaces

These modules implement the **scoped primitives** protected by the 9+
Feasibility Contract in ``docs/Furnace Agent Architecture.md`` §2.2 and
``docs/Furnace Evolution Mechanics.md`` §12.3: future scheduling / planner /
proposal layers must compose these primitives rather than replace them, and
the operator-visible ``apply-* / revert-*`` CLI surface stays unchanged.

``aiwiki.app_compile`` is the legacy owner hub for the execution
subpackage; tests, scripts and third-party imports of
``aiwiki.app_compile.<name>`` receive the owner module's implementation
through the existing re-export surface. (The historical PEP 562
``_LAZY_OWNERS`` seam described in earlier versions of this docstring was
removed once compat callers converged on direct owner imports — see
``AGENTS.md` 架构清理定案`.)
"""

from __future__ import annotations

__all__: list[str] = []
