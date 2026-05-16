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
from ..app_content import action_supports_low_risk_apply
from ..app_linting import lint_wiki, write_nightly_health
from ..app_protocol import ensure_layout
from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state import load_machine_memory_action_state, nightly_health_state_path
from ..app_utils import relative_path, runtime_write_lock, runtime_write_operation
from ..compile import compile_wiki


def _append_run_event(root: Path, event: dict[str, Any]) -> None:
    from ..runner.receipts import _append_log

    _append_log(root, event)


def nightly_health(root: Path) -> dict[str, Any]:
    with runtime_write_lock(root):
        return _nightly_health_unlocked(root)


def _nightly_health_unlocked(root: Path) -> dict[str, Any]:
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
    auto_failed: list[dict[str, Any]] = []
    try:
        action_state = load_machine_memory_action_state(root)
        accepted_ids = [
            str(a.get("id") or "")
            for a in action_state.get("actions", [])
            if isinstance(a, dict)
            and action_supports_low_risk_apply(a)
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
            except Exception as exc:
                auto_failed.append(
                    {"id": aid, "reason": str(exc), "error_type": type(exc).__name__}
                )
        if auto_applied:
            compile_result = compile_wiki(root)
    except Exception as exc:
        _append_run_event(
            root,
            {
                "event": "nightly_auto_consume_outer_failure",
                "reason": str(exc),
                "error_type": type(exc).__name__,
            },
        )

    state = write_nightly_health(
        root,
        compile_result,
        lint_result,
        promotion_result=promotion_result,
        semantic_report="",
        llm_used=False,
    )
    from ..agent_loop import attach_agent_loop_to_nightly_state, run_nightly_agent_loop_preview

    agent_loop = run_nightly_agent_loop_preview(root)
    state = attach_agent_loop_to_nightly_state(root, state, agent_loop)

    drift_aging: dict[str, Any] = {}
    try:
        from ..drift_scan import drift_scan

        drift_aging = drift_scan(root)
    except Exception as exc:
        _append_run_event(
            root,
            {
                "event": "nightly_drift_scan_failure",
                "reason": str(exc),
                "error_type": type(exc).__name__,
            },
        )

    return {
        "compile": compile_result,
        "lint": lint_result,
        "promotions": promotion_result,
        "aging": state["aging"],
        "agent_loop": state.get("agent_loop", {}),
        "drift_aging": drift_aging,
        "repair_backlog": state["repair_backlog"]["path"],
        "auto_applied": auto_applied,
        "auto_failed": auto_failed,
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }


@runtime_write_operation
def shell_status(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    return write_shell_summary(root, summary)


__all__ = ["nightly_health", "shell_status"]
