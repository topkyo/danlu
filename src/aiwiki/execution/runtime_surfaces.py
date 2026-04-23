"""Runtime surface execution owners (炼丹炉 EP-018B group 1).

Owns the two top-level runtime orchestrators previously defined inline in
``aiwiki.app_compile``:

- ``nightly_health``: compile + lint + recurring-output promotion + low-risk
  machine-memory action auto-consumption + health state write.
- ``shell_status``: build and persist the product-shell summary.

These functions stay importable as ``aiwiki.app_compile.nightly_health`` and
``aiwiki.app_compile.shell_status`` through the PEP 562 compat seam at the
bottom of ``app_compile.py`` (``_LAZY_OWNERS`` now points these two names at
this module). No caller needs to change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_compile_ops import promote_recurring_outputs
from ..app_linting import lint_wiki, write_nightly_health
from ..app_protocol import (
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    ensure_layout,
)
from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state import load_machine_memory_action_state, nightly_health_state_path
from ..app_utils import relative_path, runtime_write_operation
from ..compile import compile_wiki


def nightly_health(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    promotion_result = promote_recurring_outputs(root)
    if promotion_result["count"]:
        compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)

    # Auto-consume accepted low-risk actions (planner auto-consumption).
    # Resolve ``apply_machine_memory_action`` lazily via ``aiwiki.app_compile``
    # so that EP-018B group 6 can flip its ``_LAZY_OWNERS`` entry without
    # touching this module. Today it still self-references app_compile.
    from .. import app_compile as _app_compile

    auto_applied: list[dict[str, Any]] = []
    try:
        action_state = load_machine_memory_action_state(root)
        accepted_ids = [
            str(a.get("id") or "")
            for a in action_state.get("actions", [])
            if isinstance(a, dict)
            and str(a.get("status") or "") == "accepted"
            and bool(a.get("active", True))
            and (
                str(a.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
                or str(a.get("kind") or "") in RESOLVABLE_MONITOR_ACTION_KINDS
            )
        ]
        for aid in accepted_ids:
            try:
                dry = _app_compile.apply_machine_memory_action(
                    root, aid, note="nightly auto-consume", dry_run=True
                )
                result = _app_compile.apply_machine_memory_action(
                    root,
                    aid,
                    note="nightly auto-consume",
                    bundle_path=str(dry.get("bundle_path") or ""),
                )
                auto_applied.append(result)
            except Exception:
                pass  # skip individual failures; don't block nightly
        if auto_applied:
            compile_result = compile_wiki(root)
    except Exception:
        pass  # don't let auto-consumption errors block nightly

    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        promotion_result=promotion_result,
        semantic_report="",
        llm_used=False,
    )
    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "repair_backlog": state["repair_backlog"]["path"],
        "auto_applied": auto_applied,
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)


__all__ = ["nightly_health", "shell_status"]
