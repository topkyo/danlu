"""Residual content-domain helpers (EP-017C step 4a).

This module previously held the machine-memory action, execution-policy,
patch-plan and repair-plan logic. Those four domains have been split into
dedicated owner subpackages:

- :mod:`aiwiki.memory.action_core` — machine-memory action domain
- :mod:`aiwiki.execution.policy`   — execution policy domain
- :mod:`aiwiki.execution.patch_plan` — patch plan domain
- :mod:`aiwiki.execution.repair_plan` — repair plan domain

What remains here are two small content-domain helpers with no cross-domain
dependencies: ``remove_stale_generated_markdown_files`` (generic markdown
cleanup) and ``concept_summary_is_placeholder`` (placeholder detection used
by content/runner code).
"""

from __future__ import annotations

from pathlib import Path

from .concepts import _concept_summary_matches_legacy_placeholder
from .io import preserved_section


def remove_stale_generated_markdown_files(directory: Path, active_stems: set[str]) -> int:
    removed = 0
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        if path.stem in active_stems:
            continue
        path.unlink()
        removed += 1
    return removed


def concept_summary_is_placeholder(markdown: str) -> bool:
    summary = preserved_section(markdown, "Summary", "")
    return _concept_summary_matches_legacy_placeholder(summary)
