"""Runtime surface execution owners (炼丹炉 EP-018B group 1).

Owns the two top-level runtime orchestrators previously defined inline in
``aiwiki.app_compile``:

- ``nightly_health``: deterministic compile + lint + health state write.
- ``shell_status``: build and persist the product-shell summary.

These functions stay importable as ``aiwiki.app_compile.nightly_health`` and
``aiwiki.app_compile.shell_status`` through the PEP 562 compat seam at the
bottom of ``app_compile.py`` (``_LAZY_OWNERS`` now points these two names at
this module). No caller needs to change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_linting import lint_wiki, write_nightly_health
from ..app_protocol import ensure_layout
from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state import nightly_health_state_path
from ..app_utils import relative_path, runtime_write_lock, runtime_write_operation
from ..compile import compile_wiki


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
