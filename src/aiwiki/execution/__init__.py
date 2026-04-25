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
- :mod:`aiwiki.execution.protocol_learnings` — L2 protocol-learning lifecycle
- :mod:`aiwiki.execution.alchemy`          — ``alchemy-start/distill/finalize/promote/seal``
- :mod:`aiwiki.execution.runtime_surfaces` — runtime primitive surfaces

These modules implement the **scoped primitives** protected by the 9+
Feasibility Contract in ``docs/Furnace Agent Architecture.md`` §2.2 and
``docs/Furnace Evolution Mechanics.md`` §12.3: future scheduling / planner /
proposal layers must compose these primitives rather than replace them, and
the operator-visible ``apply-* / revert-*`` CLI surface stays unchanged.

``aiwiki.app_compile`` keeps a PEP 562 compat seam that re-exports every
execution name lazily via ``_LAZY_OWNERS``. External callers (tests,
scripts, third-party integrations) may still import
``aiwiki.app_compile.<name>`` and receive the owner module's implementation.
"""

from __future__ import annotations

__all__: list[str] = []
