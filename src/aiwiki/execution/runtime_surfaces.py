"""Runtime surface execution owners (炼丹炉 EP-018B group 1).

Owns the ``shell_status`` orchestrator previously defined inline in
``aiwiki.app_compile``: build and persist the product-shell summary.
(The historical ``nightly_health`` duplicate orchestrator was removed;
``aiwiki.runner``'s ``run_nightly`` is the single nightly path.)

Callers should import directly from this module; ``app_compile`` no longer
re-exports these names (the historical PEP 562 ``_LAZY_OWNERS`` seam was
removed once compat callers converged on direct owner imports).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_shell import build_shell_summary, write_shell_summary
from ..protocol.scaffold import ensure_layout
from ..utils.io import runtime_write_operation


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)


__all__ = ["shell_status"]
