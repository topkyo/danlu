from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.io import (
    summarize_runtime_event_for_shell,
)
from ..execution.history import load_runtime_history
from ..execution.paths import llm_receipt_log_path, run_log_path
from ..execution.policy import load_execution_receipt_history
from ..input_router import is_obsidian_open_link
from ..llm import classify_backend_error
from ..render.paths import (
    shell_summary_path,
)
from ..state.io import load_json_document
from ..utils.path import relative_path
from .helpers import (
    LLM_PRIMARY_HEALTH_EVENTS,
    _build_llm_rerun_command,
    _first_non_empty,
    _latest_llm_receipt,
)


def shell_recent_runs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    history = load_runtime_history(root)
    runs: list[dict[str, Any]] = []
    for event in reversed(history):
        summary = summarize_runtime_event_for_shell(event)
        if summary.get("ignored_by_shell"):
            continue
        runs.append(summary)
        if len(runs) >= limit:
            break
    return runs


def shell_latest_shell_sync_run(root: Path) -> dict[str, Any]:
    """Return a metadata snapshot of the on-disk shell-summary.json.

    Reads the previously-persisted summary artifact (if any) and returns a
    trimmed record describing *when it was written and by which writer label*.

    Semantics (per EP-012 contract, option B; reaffirmed by EP-015 Path 3):
    - This is NOT strictly "the last successful shell-status run". Any CLI
      entrypoint that calls `write_shell_summary` (shell-status itself,
      compile / compile_wiki, dashboard, shell-search, nightly, plus indirect
      callers via `--auto` / `auto_process_once`) leaves the same file on
      disk with `generated_by = "aiwiki-shell-status"`. The plugin must treat
      this as a metadata snapshot of whatever summary is currently persisted.
    - In-flight states (running shell-status invocations) are surfaced by
      the plugin itself from its own command history (own in-flight only,
      not a domain health source). Failure states are NOT synthesized from
      the plugin's recentRuns anymore; the plugin relies on this snapshot
      as the single domain source and only overlays its own running work.

    Returned fields:
    - `generated_at`: ISO UTC timestamp string from the prior summary
    - `generated_by`: writer label string (always "aiwiki-shell-status" today)
    - `summary_path`: repo-relative path string
    - `file_mtime_epoch`: POSIX seconds (float) since epoch from `Path.stat().st_mtime`
    - `contract_version`: int
    - `active_protocol`: str

    This is always called *before* the current build writes a new summary, so
    it reports the *prior* on-disk record rather than the in-flight one.
    Returns `{}` when no summary file exists yet (fresh vault).
    """
    summary_path = shell_summary_path(root)
    if not summary_path.exists():
        return {}
    document = load_json_document(summary_path)
    if not isinstance(document, dict) or not document:
        return {}
    generated_at = str(document.get("generated_at") or "")
    generated_by = str(document.get("generated_by") or "")
    relative_summary_path = str(document.get("summary_path") or relative_path(root, summary_path))
    try:
        mtime_epoch = summary_path.stat().st_mtime
    except OSError:
        mtime_epoch = 0.0
    return {
        "generated_at": generated_at,
        "generated_by": generated_by,
        "summary_path": relative_summary_path,
        "file_mtime_epoch": float(mtime_epoch),
        "contract_version": int(document.get("contract_version") or 0),
        "active_protocol": str(document.get("active_protocol") or ""),
    }


def shell_recent_receipts(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    receipts = load_execution_receipt_history(root)
    summaries = [
        {
            "action_id": str(receipt.get("action_id") or ""),
            "applied_at": str(receipt.get("applied_at") or ""),
            "operation": str(receipt.get("operation") or ""),
            "protocol": str(receipt.get("protocol") or ""),
            "receipt_path": str(receipt.get("receipt_path") or ""),
            "status": str(receipt.get("status") or ""),
            "subject_id": str(receipt.get("subject_id") or ""),
            "subject_kind": str(receipt.get("subject_kind") or ""),
            "title": str(receipt.get("title") or ""),
        }
        for receipt in receipts
        if not is_obsidian_open_link(str(receipt.get("question") or ""))
    ]
    return summaries[:limit]


def shell_latest_llm_run(root: Path) -> dict[str, Any]:
    receipt = _latest_llm_receipt(root, preferred_events=LLM_PRIMARY_HEALTH_EVENTS)
    if not receipt:
        return {}
    event_name = str(receipt.get("event") or "")
    status = str(receipt.get("status") or "unknown")
    error = _first_non_empty(receipt, ["error", "fallback_reason"])
    target = str(receipt.get("target") or "").strip()
    delivery_mode = str(receipt.get("delivery_mode") or "")
    fallback_used = bool(receipt.get("fallback_used"))
    fallback_from = str(receipt.get("fallback_from") or "")
    result_path = ""
    if event_name in {"run-ask", "run-ask-frontdoor"}:
        result_path = target
    elif event_name == "run-lint":
        result_path = str(receipt.get("target") or "").strip()
    elif event_name == "run-nightly":
        result_path = str(receipt.get("state_path") or "").strip()
    elif event_name == "run-compile-summary":
        updated_pages = receipt.get("updated_pages")
        if isinstance(updated_pages, list) and updated_pages:
            result_path = str(updated_pages[0] or "").strip()
    return {
        "event": event_name,
        "status": status,
        "checked_at": _first_non_empty(receipt, ["created_at"]),
        "backend_requested": str(receipt.get("backend_requested") or ""),
        "backend_effective": str(receipt.get("backend_effective") or ""),
        "model_selected": str(receipt.get("model_selected") or ""),
        "model_final": str(receipt.get("model_final") or ""),
        "fallback_stage": str(receipt.get("fallback_stage") or ""),
        "fallback_reason": str(receipt.get("fallback_reason") or ""),
        "contract_validated": bool(receipt.get("contract_validated")),
        "prompt_profile": str(receipt.get("prompt_profile") or ""),
        "retry_prompt_profile": str(receipt.get("retry_prompt_profile") or ""),
        "duration_ms": int(receipt.get("duration_ms", 0) or 0),
        "error": error,
        "delivery_mode": delivery_mode,
        "primary_attempt_status": str(receipt.get("primary_attempt_status") or status),
        "primary_error": str(receipt.get("primary_error") or error),
        "fallback_used": fallback_used,
        "fallback_from": fallback_from,
        "fallback_command": str(receipt.get("fallback_command") or ""),
        "result_path": result_path,
        "receipt_path": relative_path(root, llm_receipt_log_path(root)),
        "log_path": relative_path(root, run_log_path(root)),
        "run_log_path": relative_path(root, run_log_path(root)),
        "rerun_command": _build_llm_rerun_command(receipt),
        "target": target,
    }


def shell_llm_health(root: Path, llm_status: dict[str, Any], *, latest_llm_run: dict[str, Any]) -> dict[str, Any]:
    configured = bool(llm_status.get("configured"))
    current_backend = str(llm_status.get("backend") or "")
    current_model = str(llm_status.get("effective_model") or llm_status.get("model") or "")
    latest_backend = str(latest_llm_run.get("backend_effective") or latest_llm_run.get("backend_requested") or "")
    latest_model = str(latest_llm_run.get("model_final") or latest_llm_run.get("model_selected") or "")
    latest_status = str(latest_llm_run.get("status") or "")
    delivery_mode = str(latest_llm_run.get("delivery_mode") or "")
    route_drift = bool(current_backend and latest_backend and current_backend != latest_backend)
    if not configured:
        return {
            "status": "unknown",
            "reason": "LLM is not configured.",
            "backend": current_backend,
            "model": current_model,
            "backend_requested": str(llm_status.get("backend_requested") or ""),
            "backend_effective": current_backend,
            "model_selected": latest_model,
            "model_final": latest_model or current_model,
            "checked_at": str(latest_llm_run.get("checked_at") or ""),
            "source": str(latest_llm_run.get("event") or ""),
            "fallback_command": "",
            "fallback_stage": str(latest_llm_run.get("fallback_stage") or ""),
            "fallback_reason": str(latest_llm_run.get("fallback_reason") or ""),
            "contract_validated": bool(latest_llm_run.get("contract_validated")),
            "log_path": str(latest_llm_run.get("log_path") or ""),
            "result_path": str(latest_llm_run.get("result_path") or ""),
            "receipt_path": str(latest_llm_run.get("receipt_path") or ""),
            "rerun_command": str(latest_llm_run.get("rerun_command") or latest_llm_run.get("recovery_command") or ""),
            "route_drift": False,
            "route_drift_reason": "",
        }
    if not latest_llm_run:
        return {
            "status": "unknown",
            "reason": "No recent LLM health check yet.",
            "backend": current_backend,
            "model": current_model,
            "backend_requested": str(llm_status.get("backend_requested") or ""),
            "backend_effective": current_backend,
            "model_selected": "",
            "model_final": current_model,
            "checked_at": "",
            "source": "",
            "fallback_command": "",
            "fallback_stage": "",
            "fallback_reason": "",
            "contract_validated": False,
            "log_path": "",
            "result_path": "",
            "receipt_path": "",
            "rerun_command": "",
            "route_drift": False,
            "route_drift_reason": "",
        }
    error_text = _first_non_empty(latest_llm_run, ["error", "fallback_reason"])
    error_kind = classify_backend_error(error_text) if error_text else ""
    status = "healthy"
    reason = "Recent run-ask succeeded." if latest_status == "success" else error_text
    fallback_command = str(latest_llm_run.get("fallback_command") or "")
    if delivery_mode == "deterministic-fallback":
        status = "degraded"
        reason = "Recent run-ask fell back to deterministic scaffold (legacy receipt)."
        fallback_command = fallback_command or "run-ask"
    elif delivery_mode == "skipped":
        reason = f"Recent {str(latest_llm_run.get('event') or 'LLM run')} skipped (no LLM invocation)."
    elif delivery_mode == "llm-fallback-chain":
        status = "degraded"
        stage = str(latest_llm_run.get("fallback_stage") or "")
        if stage == "model-chain":
            reason = "LLM completed via model-chain fallback."
        elif stage == "prompt-profile":
            reason = "LLM completed via prompt-profile retry."
        elif stage:
            reason = f"LLM completed via fallback ({stage})."
        else:
            reason = "LLM completed via fallback chain."
    elif delivery_mode == "llm-failed":
        status = "degraded"
        reason = "LLM failed before completing the primary route."
    if latest_status != "success":
        status = "degraded" if error_kind in {"quota", "timeout", "auth", "unavailable"} else "failed"
        if not reason:
            reason = "Latest LLM run failed."
    elif route_drift and delivery_mode != "deterministic-fallback":
        status = "unknown"
        reason = "Current route changed since the last recorded ask."
    return {
        "status": status,
        "reason": reason,
        "delivery_mode": delivery_mode,
        "backend": current_backend or latest_backend,
        "model": current_model or latest_model,
        "backend_requested": str(latest_llm_run.get("backend_requested") or llm_status.get("backend_requested") or ""),
        "backend_effective": latest_backend or current_backend,
        "model_selected": str(latest_llm_run.get("model_selected") or ""),
        "model_final": latest_model or current_model,
        "checked_at": str(latest_llm_run.get("checked_at") or ""),
        "source": str(latest_llm_run.get("event") or ""),
        "fallback_command": fallback_command,
        "fallback_stage": str(latest_llm_run.get("fallback_stage") or ""),
        "fallback_reason": str(latest_llm_run.get("fallback_reason") or ""),
        "contract_validated": bool(latest_llm_run.get("contract_validated")),
        "log_path": str(latest_llm_run.get("log_path") or ""),
        "result_path": str(latest_llm_run.get("result_path") or ""),
        "receipt_path": str(latest_llm_run.get("receipt_path") or ""),
        "rerun_command": str(latest_llm_run.get("rerun_command") or latest_llm_run.get("recovery_command") or ""),
        "route_drift": route_drift,
        "route_drift_reason": "Current route changed since the last recorded ask." if route_drift else "",
    }


def shell_drift_warnings(
    memory: dict[str, Any],
    *,
    judgment_assets: dict[str, Any],
    compile_state: dict[str, Any],
    aging_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        key = (str(item.get("kind") or ""), str(item.get("path") or ""), str(item.get("message") or ""))
        if key in seen:
            return
        seen.add(key)
        warnings.append(dict(item))

    for item in compile_state.get("drift_warnings", []) or []:
        _add(item)

    if isinstance(aging_state, dict):
        for item in aging_state.get("warnings", []) or []:
            _add(item)

    drift = memory.get("drift", {})
    if isinstance(drift, dict):
        for path in drift.get("missing_source_pages", [])[:4]:
            _add(
                {
                    "kind": "source-reference-break",
                    "path": str(path),
                    "message": f"Missing source page `{path}`.",
                }
            )
        for path in drift.get("missing_concept_pages", [])[:4]:
            _add(
                {
                    "kind": "concept-disappear",
                    "path": str(path),
                    "message": f"Missing concept page `{path}`.",
                }
            )
    attention_pages = judgment_assets.get("attention_pages", [])
    if isinstance(attention_pages, list):
        for page in attention_pages[:4]:
            if not isinstance(page, dict):
                continue
            invalidation_rule = str(page.get("invalidation_rule") or "")
            if not invalidation_rule:
                continue
            _add(
                {
                    "kind": "judgment-invalidation",
                    "path": str(page.get("path") or ""),
                    "message": f"{str(page.get('title') or page.get('path') or 'judgment')} requires invalidation review.",
                }
            )
    return warnings[:8]


def shell_compound_suggest_actions(compound_suggest: dict[str, Any]) -> list[dict[str, Any]]:
    """Map scarce compound_suggest items into suggested_next_actions entries."""

    if not isinstance(compound_suggest, dict):
        return []
    actions: list[dict[str, Any]] = []
    seen_commands: set[str] = set()
    for item in compound_suggest.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command") or "").strip()
        title = str(item.get("title") or item.get("report_title") or "").strip()
        report_path = str(item.get("report_path") or "").strip()
        if not command or not title or command in seen_commands:
            continue
        seen_commands.add(command)
        actions.append(
            {
                "kind": "compound-suggest",
                "title": title,
                "command": command,
                "path": report_path,
                "reason": str(item.get("reason") or item.get("signal") or "compound-suggest"),
                "action": str(item.get("action") or ""),
                "signal": str(item.get("signal") or ""),
                "linked_refs": list(item.get("linked_refs") or []),
                "corpus_id": str(item.get("corpus_id") or ""),
            }
        )
    return actions
