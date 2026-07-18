"""LLM receipt, audit, and run-log helpers for runner workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiwiki.app_protocol import ensure_layout
from aiwiki.runner.clients import (
    _append_fallback_stage,
    _client_backend_name,
    _client_backend_requested,
    _client_model_name,
    _fallback_stage_label,
)
from aiwiki.runner.interfaces import SupportsComplete
from aiwiki.utils.io import atomic_append_jsonl


def _append_log(root: Path, event: dict[str, Any]) -> None:
    _append_jsonl_log(root, ".aiwiki/logs/runs.jsonl", event)


def _append_llm_receipt(root: Path, event: dict[str, Any]) -> None:
    from aiwiki.execution.audit_preview import append_universal_audit_record
    from aiwiki.utils.audit import AuditMirrorError, AuditMirrorRollbackError
    from aiwiki.utils.io import _durable_truncate

    log_path = root / ".aiwiki/logs/llm-receipts.jsonl"
    size_before = log_path.stat().st_size if log_path.exists() else 0
    payload, line_number = _append_jsonl_log(root, ".aiwiki/logs/llm-receipts.jsonl", event)
    try:
        append_universal_audit_record(
            root,
            source_stream="llm_receipts",
            source_ref=f".aiwiki/logs/llm-receipts.jsonl#L{line_number}",
            document=payload,
        )
    except Exception as audit_exc:
        try:
            _durable_truncate(log_path, size_before)
        except Exception as truncate_exc:
            raise AuditMirrorRollbackError(
                "audit mirror append failed and primary truncate also failed: "
                f"audit={audit_exc!r}; truncate={truncate_exc!r}"
            ) from audit_exc
        raise AuditMirrorError(f"universal audit append failed; primary truncated: {audit_exc!r}") from audit_exc


def _append_jsonl_log(root: Path, relative_log_path: str, event: dict[str, Any]) -> tuple[dict[str, Any], int]:
    ensure_layout(root)
    payload = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **event,
    }
    log_path = root / relative_log_path
    line_number = _next_jsonl_line_number(log_path)
    atomic_append_jsonl(log_path, payload)
    return payload, line_number


def _next_jsonl_line_number(path: Path) -> int:
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count + 1


_HISTORICAL_LINEAGE_KEYS = (
    "fallback_from",
    "fallback_command",
    "fallback_stage",
    "fallback_reason",
)


def _infer_delivery_mode(
    status: str, error: str = "", fallback_stage: str = "", explicit: str = "", skipped: bool = False
) -> str:
    if explicit:
        return explicit
    if skipped:
        return "skipped"
    if status == "failed" or error:
        return "llm-failed"
    if status == "success" and fallback_stage:
        return "llm-fallback-chain"
    if status == "success":
        return "llm-success"
    return ""


def _omit_empty_historical_lineage(payload: dict[str, Any]) -> None:
    """Drop empty historical fallback lineage keys so success receipts stay clean."""

    for key in _HISTORICAL_LINEAGE_KEYS:
        if not str(payload.get(key) or ""):
            payload.pop(key, None)


def _empty_llm_audit() -> dict[str, Any]:
    return {
        "backend_requested": "",
        "backend_effective": "",
        "model_selected": "",
        "model_final": "",
        "contract_validated": False,
    }


def _build_llm_audit(
    client: SupportsComplete | None,
    *,
    model_selected: str = "",
    fallback_stages: list[str] | None = None,
    fallback_reason: str = "",
    contract_validated: bool = False,
) -> dict[str, Any]:
    audit = _empty_llm_audit()
    stages = fallback_stages or []
    audit["model_selected"] = model_selected
    fallback_stage_label = _fallback_stage_label(stages)
    if fallback_stage_label:
        audit["fallback_stage"] = fallback_stage_label
    if fallback_reason:
        audit["fallback_reason"] = fallback_reason
    audit["contract_validated"] = contract_validated
    if client is None:
        return audit
    audit["backend_requested"] = _client_backend_requested(client)
    audit["backend_effective"] = _client_backend_name(client)
    audit["model_selected"] = model_selected or _client_model_name(client)
    audit["model_final"] = _client_model_name(client)
    return audit


def _merge_llm_audits(current: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = _empty_llm_audit()
    if isinstance(current, dict):
        merged.update(current)
    if not isinstance(update, dict):
        _omit_empty_historical_lineage(merged)
        return merged
    if not merged["backend_requested"]:
        merged["backend_requested"] = str(update.get("backend_requested") or "")
    if str(update.get("backend_effective") or ""):
        merged["backend_effective"] = str(update.get("backend_effective") or "")
    if not merged["model_selected"]:
        merged["model_selected"] = str(update.get("model_selected") or "")
    if str(update.get("model_final") or ""):
        merged["model_final"] = str(update.get("model_final") or "")
    stages: list[str] = []
    for label in (str(merged.get("fallback_stage") or ""), str(update.get("fallback_stage") or "")):
        for stage in label.split("+"):
            _append_fallback_stage(stages, stage)
    fallback_stage_label = _fallback_stage_label(stages)
    if fallback_stage_label:
        merged["fallback_stage"] = fallback_stage_label
    else:
        merged.pop("fallback_stage", None)
    if str(update.get("fallback_reason") or ""):
        merged["fallback_reason"] = str(update.get("fallback_reason") or "")
    elif not str(merged.get("fallback_reason") or ""):
        merged.pop("fallback_reason", None)
    merged["contract_validated"] = bool(merged.get("contract_validated")) or bool(update.get("contract_validated"))
    _omit_empty_historical_lineage(merged)
    return merged


def _llm_audit_from_result(result: dict[str, Any]) -> dict[str, Any]:
    audit = _empty_llm_audit()
    if not isinstance(result, dict):
        return audit
    for key in audit:
        if key == "contract_validated":
            audit[key] = bool(result.get(key))
        else:
            audit[key] = str(result.get(key) or "")
    for key in ("fallback_stage", "fallback_reason"):
        value = str(result.get(key) or "")
        if value:
            audit[key] = value
    return audit


def classify_fallback_stage(
    event: dict[str, Any],
    *,
    status: str,
    error: str = "",
    skipped: bool = False,
) -> str:
    """Classify the delivery mode for an LLM attempt receipt."""

    return _infer_delivery_mode(
        status,
        error=error,
        fallback_stage=str(event.get("fallback_stage") or ""),
        explicit=str(event.get("delivery_mode") or ""),
        skipped=skipped,
    )


def build_llm_attempt_receipt(
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    *,
    status: str,
    error: str = "",
    response_id: str = "",
    usage: dict[str, Any] | None = None,
    raw_response_path: str = "",
    error_class: str = "",
    skipped: bool = False,
) -> dict[str, Any]:
    """Build the normalized receipt payload for one LLM attempt."""

    usage_payload = usage if isinstance(usage, dict) else {}
    normalized_event = {**llm_audit, **base_event}
    normalized_event["delivery_mode"] = classify_fallback_stage(
        normalized_event, status=status, error=error, skipped=skipped
    )
    normalized_event.setdefault("fallback_used", False)
    if not normalized_event["fallback_used"]:
        normalized_event["fallback_used"] = bool(
            normalized_event.get("delivery_mode") == "deterministic-fallback"
            or str(normalized_event.get("fallback_stage") or "")
        )
    _omit_empty_historical_lineage(normalized_event)
    normalized_event.setdefault("primary_attempt_status", "")
    normalized_event.setdefault("primary_error", "")
    normalized_raw_response_path = raw_response_path or ""
    if not normalized_raw_response_path and status != "success" and error:
        normalized_raw_response_path = "no_response"
    normalized_event.update(
        {
            "status": status,
            "response_id": response_id,
            "usage": usage_payload,
            "raw_response_path": normalized_raw_response_path,
            "error_class": error_class,
            "error_message": error,
        }
    )
    if error:
        normalized_event["error"] = error
    audit_update = {
        "delivery_mode": normalized_event.get("delivery_mode", ""),
        "fallback_used": bool(normalized_event.get("fallback_used", False)),
        "primary_attempt_status": str(normalized_event.get("primary_attempt_status") or ""),
        "primary_error": str(normalized_event.get("primary_error") or ""),
    }
    for historical_lineage_key in _HISTORICAL_LINEAGE_KEYS:
        if historical_lineage_key in normalized_event:
            audit_update[historical_lineage_key] = str(normalized_event.get(historical_lineage_key) or "")
        else:
            llm_audit.pop(historical_lineage_key, None)
    llm_audit.update(audit_update)
    return normalized_event


def append_receipt_and_audit(
    root: Path,
    receipt: dict[str, Any],
    *,
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    error: str = "",
) -> None:
    """Append a built LLM receipt to receipt, universal audit, and run logs."""

    _append_llm_receipt(root, receipt)
    run_event = {
        **base_event,
        "backend": str(llm_audit.get("backend_effective") or ""),
        "model": str(llm_audit.get("model_final") or ""),
        **receipt,
    }
    # base_event may still carry empty historical lineage keys; drop them so
    # runs.jsonl matches the omitted llm-receipt shape.
    _omit_empty_historical_lineage(run_event)
    if error:
        run_event["error"] = error
    _append_log(root, run_event)


def record_llm_attempt(
    root: Path,
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    *,
    status: str,
    error: str = "",
    response_id: str = "",
    usage: dict[str, Any] | None = None,
    raw_response_path: str = "",
    error_class: str = "",
    skipped: bool = False,
) -> dict[str, Any]:
    """Build, classify, and append one LLM attempt receipt through the single entrypoint."""

    receipt = build_llm_attempt_receipt(
        base_event,
        llm_audit,
        status=status,
        error=error,
        response_id=response_id,
        usage=usage,
        raw_response_path=raw_response_path,
        error_class=error_class,
        skipped=skipped,
    )
    append_receipt_and_audit(root, receipt, base_event=base_event, llm_audit=llm_audit, error=error)
    return receipt


def _append_llm_receipt_and_log(
    root: Path,
    base_event: dict[str, Any],
    llm_audit: dict[str, Any],
    *,
    status: str,
    error: str = "",
    response_id: str = "",
    usage: dict[str, Any] | None = None,
    raw_response_path: str = "",
    error_class: str = "",
    skipped: bool = False,
) -> None:
    """Compatibility wrapper for legacy imports; prefer record_llm_attempt."""

    record_llm_attempt(
        root,
        base_event,
        llm_audit,
        status=status,
        error=error,
        response_id=response_id,
        usage=usage,
        raw_response_path=raw_response_path,
        error_class=error_class,
        skipped=skipped,
    )
