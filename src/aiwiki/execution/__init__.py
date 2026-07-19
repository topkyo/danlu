"""Execution owner subpackage (炼丹炉 scoped primitives).

EP-018B migration is complete. Each execution-layer function now has a
dedicated owner module in this subpackage:

- :mod:`aiwiki.execution.ask`              — ``ask_question`` / ``file_back``
- :mod:`aiwiki.execution.candidates`       — output candidate promote/demote
- :mod:`aiwiki.execution.lifecycle`        — concept retire/reactivate +
                                              knowledge-lifecycle runtime
- :mod:`aiwiki.execution.concept_rewrite`  — concept rewrite library apply/revert
- :mod:`aiwiki.execution.archive`          — archive apply/revert library paths
- :mod:`aiwiki.execution.machine_memory_actions` — machine-memory action apply/revert
- :mod:`aiwiki.execution.machine_memory_batch`   — nightly batch orchestration
- :mod:`aiwiki.execution.review`           — ``review-page`` primitive
- :mod:`aiwiki.execution.alchemy`          — ``alchemy-start/distill/finalize/promote/revert/demote``
- :mod:`aiwiki.execution.l3_proposals`     — manual L3 proposal lifecycle + generation preview
- :mod:`aiwiki.execution.audit_preview`    — universal audit stream read-only preview
- :mod:`aiwiki.execution.runtime_surfaces` — runtime primitive surfaces

These modules implement the **scoped primitives** protected by the 9+
Feasibility Contract in ``docs/Furnace Agent Architecture.md`` §2.2 and
``docs/Furnace Evolution Mechanics.md`` §12.3: future scheduling / planner /
proposal layers must compose these primitives rather than replace them.
Post-W3/W8 operator surface is ``advanced compile`` / ``review-page`` /
``alchemy-revert``; library apply/revert paths have no matching CLI.
"""

from __future__ import annotations

__all__: list[str] = []
