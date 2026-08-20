"""Execution owner subpackage (炼丹炉 scoped primitives).

EP-018B migration is complete. Each execution-layer function now has a
dedicated owner module in this subpackage:

- :mod:`aiwiki.execution.ask`              — ``ask_question``
- :mod:`aiwiki.execution.file_back`        — ``file_back``
- :mod:`aiwiki.execution.candidates`       — output candidate promote/demote
- :mod:`aiwiki.execution.review`           — ``review-page`` primitive
- :mod:`aiwiki.execution.alchemy`          — ``advanced alchemy start|distill|finalize|promote|revert|demote``
- :mod:`aiwiki.execution.audit_preview`    — universal audit stream read-only preview
- :mod:`aiwiki.execution.runtime_surfaces` — runtime primitive surfaces

These modules implement the **scoped primitives** protected by the 9+
Feasibility Contract in ``docs/Furnace Agent Architecture.md`` §2.2 and
``docs/Furnace Evolution Mechanics.md`` §12.3: future scheduling / planner /
proposal layers must compose these primitives rather than replace them.
Post-W3/W8 operator surface is ``advanced compile`` / ``advanced review-page`` /
``advanced alchemy revert``.
"""

from __future__ import annotations

__all__: list[str] = []
