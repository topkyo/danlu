"""Residual content-domain helpers (EP-017C step 4a).

This module previously held the machine-memory action, execution-policy,
patch-plan and repair-plan logic. Those four domains have been split into
dedicated owner subpackages:

- :mod:`aiwiki.memory.action_core` — machine-memory action domain
- :mod:`aiwiki.execution.policy`   — execution policy domain
- :mod:`aiwiki.execution.patch_plan` — patch plan domain
- :mod:`aiwiki.execution.repair_plan` — repair plan domain

What remains here is one small content-domain helper with no cross-domain
dependencies: ``concept_summary_is_placeholder`` (placeholder detection used
by content/runner code).
"""

from __future__ import annotations

from .concepts import _concept_summary_matches_legacy_placeholder
from .io import preserved_section


def concept_summary_is_placeholder(markdown: str) -> bool:
    summary = preserved_section(markdown, "Summary", "")
    return _concept_summary_matches_legacy_placeholder(summary)
