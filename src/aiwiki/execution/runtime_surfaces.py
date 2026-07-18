"""Runtime surface execution owners (炼丹炉 EP-018B group 1).

Owns the two top-level runtime orchestrators previously defined inline in
``aiwiki.app_compile``:

- ``nightly_health``: deterministic compile + lint + health state write.
- ``shell_status``: build and persist the product-shell summary.

Callers should import directly from this module; ``app_compile`` no longer
re-exports these names (the historical PEP 562 ``_LAZY_OWNERS`` seam was
removed once compat callers converged on direct owner imports).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_linting import lint_wiki, write_nightly_health
from ..app_shell import build_shell_summary, write_shell_summary
from ..compile import compile_wiki
from ..lifecycle.paths import nightly_health_state_path
from ..protocol.scaffold import ensure_layout
from ..utils.io import runtime_write_lock, runtime_write_operation
from ..utils.path import relative_path


def nightly_health(root: Path) -> dict[str, Any]:
    with runtime_write_lock(root):
        return _nightly_health_unlocked(root)


def _nightly_health_unlocked(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)

    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        semantic_report="",
        llm_used=False,
    )

    return {
        "compile": compile_result,
        "lint": lint_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)


__all__ = ["nightly_health", "shell_status"]
