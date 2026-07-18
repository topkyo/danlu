"""Runtime / run-log / LLM-receipt history loaders + universal audit append.

Extracted from the legacy app_state hub. Owned by the execution layer; the
`append_runtime_history` writer mirrors each event into the universal audit stream
via the sibling `execution.audit_preview` module. `append_execution_receipt_history`
was moved here from the legacy `app_execution` hub and follows the same pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..state.io import (
    _next_jsonl_line_number,
    load_json_document,
    load_jsonl_documents,
    load_jsonl_documents_strict,
)
from ..utils.audit import AuditMirrorError, AuditMirrorRollbackError
from ..utils.io import _durable_truncate, atomic_append_jsonl, runtime_write_operation
from ..utils.path import relative_path
from .paths import (
    execution_receipt_history_path,
    llm_receipt_log_path,
    run_log_path,
    runtime_history_path,
)


def load_runtime_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(runtime_history_path(root))


def load_runtime_history_strict(root: Path) -> list[dict[str, Any]]:
    """Strict variant of load_runtime_history for execution decision paths.

    Raises CorruptStateError on malformed JSONL. Use only on fact-layer /
    decision paths; dashboard/preview should keep best-effort load_runtime_history.
    """
    return load_jsonl_documents_strict(runtime_history_path(root))


def load_run_log_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(run_log_path(root))


def load_llm_receipt_history(root: Path) -> list[dict[str, Any]]:
    return load_jsonl_documents(llm_receipt_log_path(root))


@runtime_write_operation
def append_runtime_history(root: Path, event: dict[str, Any]) -> None:
    path = runtime_history_path(root)
    size_before = path.stat().st_size if path.exists() else 0
    line_number = _next_jsonl_line_number(path)
    atomic_append_jsonl(path, event)
    from .audit_preview import append_universal_audit_record

    try:
        append_universal_audit_record(
            root,
            source_stream="runtime_history",
            source_ref=f"{relative_path(root, path)}#L{line_number}",
            document=event,
        )
    except Exception as audit_exc:
        try:
            _durable_truncate(path, size_before)
        except Exception as truncate_exc:
            raise AuditMirrorRollbackError(
                "audit mirror append failed and primary truncate also failed: "
                f"audit={audit_exc!r}; truncate={truncate_exc!r}"
            ) from audit_exc
        raise AuditMirrorError(f"universal audit append failed; primary truncated: {audit_exc!r}") from audit_exc


@runtime_write_operation
def append_execution_receipt_history(root: Path, receipt: dict[str, Any]) -> None:
    path = execution_receipt_history_path(root)
    size_before = path.stat().st_size if path.exists() else 0
    line_number = _next_jsonl_line_number(path)
    atomic_append_jsonl(path, receipt)
    from .audit_preview import append_universal_audit_record

    try:
        append_universal_audit_record(
            root,
            source_stream="execution_receipts",
            source_ref=f"{relative_path(root, path)}#L{line_number}",
            document=receipt,
        )
    except Exception as audit_exc:
        try:
            _durable_truncate(path, size_before)
        except Exception as truncate_exc:
            raise AuditMirrorRollbackError(
                f"audit append failed and primary truncate also failed: audit={audit_exc!r}; truncate={truncate_exc!r}"
            ) from audit_exc
        raise AuditMirrorError(
            f"universal audit append failed; primary truncated: {audit_exc!r}"
        ) from audit_exc


__all__ = [
    "append_execution_receipt_history",
    "append_runtime_history",
    "load_llm_receipt_history",
    "load_run_log_history",
    "load_runtime_history",
    "load_runtime_history_strict",
    "recent_execution_dry_runs",
]


def recent_execution_dry_runs(root: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in reversed(load_runtime_history(root)):
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "")
        if "dry-run" not in event_type:
            continue
        preview_path = str(event.get("preview_path") or "")
        payload = load_json_document(root / preview_path) if preview_path else {}
        if not isinstance(payload, dict):
            payload = {}
        preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
        bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else {}
        safe_preview = bundle.get("safe_apply_preview") if isinstance(bundle.get("safe_apply_preview"), dict) else {}
        affected_paths = preview.get("affected_paths") if isinstance(preview.get("affected_paths"), list) else []
        if not affected_paths and isinstance(safe_preview.get("affected_paths"), list):
            affected_paths = safe_preview.get("affected_paths")
        records.append(
            {
                "event_type": event_type,
                "title": str(
                    payload.get("title")
                    or event.get("action_id")
                    or event.get("entry_id")
                    or event.get("slug")
                    or event_type
                ),
                "occurred_at": str(event.get("occurred_at") or payload.get("generated_at") or ""),
                "preview_path": preview_path,
                "bundle_path": str(event.get("bundle_path") or payload.get("bundle_path") or ""),
                "apply_mode": str(
                    payload.get("apply_mode")
                    or preview.get("apply_mode")
                    or safe_preview.get("apply_mode")
                    or event_type
                ),
                "affected_paths": [str(path) for path in affected_paths if isinstance(path, str) and path],
            }
        )
        if len(records) >= limit:
            break
    return records
