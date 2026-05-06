"""Reconcile execution receipt history with receipt files.

R95.4 adds a best-effort marker pass for historical false-success residue:
successful apply lines in ``execution-receipts.jsonl`` whose receipt file is
missing, unsafe to resolve, or content-mismatched are recorded in the universal
audit stream as deterministic, idempotent markers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..app_state import execution_receipt_history_path
from ..app_utils import relative_path, runtime_write_lock, sha256_bytes, utc_now
from .audit_preview import AUDIT_STREAM_PATH, _existing_audit_event_ids, append_audit

RECONCILIATION_SOURCE_STREAM = "audit_reconciliation"
RECONCILIATION_EVENT_TYPE = "receipt_false_success_detected"
SUCCESS_OPERATIONS = frozenset({"apply"})


def reconcile_execution_receipts(root: Path) -> dict[str, Any]:
    """Scan execution receipt history and append false-success audit markers."""

    history_path = execution_receipt_history_path(root)
    if not history_path.exists():
        return _empty_result()

    audit_path = root / AUDIT_STREAM_PATH
    existing_ids = _existing_audit_event_ids(audit_path) if audit_path.exists() else set()
    scanned_count = 0
    appended_count = 0
    skipped_duplicate_count = 0
    findings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    rel_history = relative_path(root, history_path)

    for line_no, line in _iter_jsonl_lines(history_path):
        scanned_count += 1
        try:
            doc = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": line_no, "error": f"invalid_json: {exc}"})
            continue
        if not isinstance(doc, dict):
            errors.append({"line": line_no, "error": "invalid_json: expected object"})
            continue
        if doc.get("operation") not in SUCCESS_OPERATIONS:
            continue

        reason = _classify_apply_line(root, doc)
        if reason is None:
            continue

        source_ref = f"{rel_history}#L{line_no}"
        event_id = _reconciliation_event_id(source_ref)
        finding = {
            "line": line_no,
            "reason": reason,
            "action_id": str(doc.get("action_id") or ""),
        }
        findings.append(finding)
        if event_id in existing_ids:
            skipped_duplicate_count += 1
            finding["appended"] = False
            finding["skip_reason"] = "duplicate"
            continue

        occurred_at = utc_now()
        record = {
            "audit_event_id": event_id,
            "source_stream": RECONCILIATION_SOURCE_STREAM,
            "source_ref": source_ref,
            "event_type": RECONCILIATION_EVENT_TYPE,
            "occurred_at": occurred_at,
            "subject": {
                "kind": str(doc.get("subject_kind", "") or ""),
                "id": str(doc.get("subject_id") or doc.get("action_id") or ""),
            },
            "target_action_id": str(doc.get("action_id") or ""),
            "target_receipt_path": str(doc.get("receipt_path") or ""),
            "target_operation": str(doc.get("operation") or ""),
            "reason": reason,
            "detected_at": occurred_at,
        }
        try:
            with runtime_write_lock(root):
                append_result = append_audit(
                    RECONCILIATION_SOURCE_STREAM,
                    record,
                    event_id=event_id,
                    root=root,
                )
            if append_result.written:
                appended_count += 1
                existing_ids.add(event_id)
                finding["appended"] = True
            else:
                skipped_duplicate_count += 1
                existing_ids.add(event_id)
                finding["appended"] = False
                finding["skip_reason"] = append_result.reason
        except Exception as exc:  # noqa: BLE001 - per-line reconciliation should continue
            errors.append({"line": line_no, "error": str(exc)})
            finding["appended"] = False
            finding["error"] = str(exc)

    return {
        "status": "ok" if not errors else "partial",
        "scanned_count": scanned_count,
        "findings_count": len(findings),
        "appended_count": appended_count,
        "skipped_duplicate_count": skipped_duplicate_count,
        "findings": findings,
        "errors": errors,
    }


def _empty_result() -> dict[str, Any]:
    return {
        "status": "ok",
        "scanned_count": 0,
        "findings_count": 0,
        "appended_count": 0,
        "skipped_duplicate_count": 0,
        "findings": [],
        "errors": [],
    }


def _iter_jsonl_lines(path: Path) -> Iterator[tuple[int, str]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            payload = line.strip()
            if payload:
                yield line_no, payload


def _classify_apply_line(root: Path, doc: dict[str, Any]) -> str | None:
    receipt_path_raw = str(doc.get("receipt_path") or "")
    if not receipt_path_raw:
        return "receipt_path_missing"

    root_abs = root.resolve()
    receipt_abs = (root / receipt_path_raw).resolve()
    try:
        receipt_abs.relative_to(root_abs)
    except ValueError:
        return "path_traversal_suspicious"

    if not receipt_abs.exists():
        return "receipt_path_missing"

    # Re-validate immediately before reading to close the symlink-replacement
    # TOCTOU window between the resolve check and the read.
    try:
        revalidated = receipt_abs.resolve(strict=True)
    except FileNotFoundError:
        return "receipt_path_missing"
    except OSError:
        return "path_traversal_suspicious"
    try:
        revalidated.relative_to(root_abs)
    except ValueError:
        return "path_traversal_suspicious"

    try:
        content = json.loads(revalidated.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "receipt_content_mismatch"
    if not isinstance(content, dict):
        return "receipt_content_mismatch"
    if content.get("action_id") != doc.get("action_id"):
        return "receipt_content_mismatch"
    if content.get("operation") != doc.get("operation"):
        return "receipt_content_mismatch"
    if str(content.get("subject_kind") or "") != str(doc.get("subject_kind") or ""):
        return "receipt_content_mismatch"
    if str(content.get("subject_id") or "") != str(doc.get("subject_id") or ""):
        return "receipt_content_mismatch"
    return None


def _reconciliation_event_id(source_ref: str) -> str:
    digest_payload = f"{source_ref}|{RECONCILIATION_EVENT_TYPE}"
    return "audit-" + sha256_bytes(digest_payload.encode("utf-8"))[:20]
