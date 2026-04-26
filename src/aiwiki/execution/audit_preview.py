"""Universal audit stream preview, backfill, and append helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_state import execution_receipt_history_path, llm_receipt_log_path, runtime_history_path
from ..app_utils import sha256_bytes
from .protocol_learnings import AUDIT_STATE_PATH

AUDIT_STREAM_PATH = ".aiwiki/state/audit.jsonl"


def preview_universal_audit_stream(root: Path, *, limit: int = 50) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be a positive integer.")

    records: list[dict[str, Any]] = []
    source_counts = {
        "execution_receipts": 0,
        "llm_receipts": 0,
        "runtime_history": 0,
        "protocol_learnings_age": 0,
    }

    for source_stream, path in (
        ("execution_receipts", execution_receipt_history_path(root)),
        ("llm_receipts", llm_receipt_log_path(root)),
        ("runtime_history", runtime_history_path(root)),
    ):
        rel_path = _known_relative_path(root, path)
        for line_number, document in _iter_jsonl_documents(path):
            source_counts[source_stream] += 1
            if len(records) < limit:
                records.append(_audit_record(source_stream, f"{rel_path}#L{line_number}", document))

    age_audit_path = root / AUDIT_STATE_PATH
    if age_audit_path.exists():
        document = _load_json_document(age_audit_path)
        if document:
            source_counts["protocol_learnings_age"] += 1
            if len(records) < limit:
                records.append(_audit_record("protocol_learnings_age", AUDIT_STATE_PATH, document))

    scanned_count = sum(source_counts.values())
    return {
        "status": "ok",
        "mode": "dry_run",
        "side_effects_allowed": False,
        "audit_stream_path": AUDIT_STREAM_PATH,
        "audit_stream_exists": (root / AUDIT_STREAM_PATH).exists(),
        "scanned_count": scanned_count,
        "returned_count": len(records),
        "limit": limit,
        "source_counts": source_counts,
        "records": records,
    }


def backfill_universal_audit_stream(root: Path, *, limit: int = 50, apply: bool = False) -> dict[str, Any]:
    preview = preview_universal_audit_stream(root, limit=limit)
    audit_path = root / AUDIT_STREAM_PATH
    existing_ids = _existing_audit_event_ids(audit_path)
    appendable = [
        record
        for record in preview["records"]
        if isinstance(record, dict) and str(record.get("audit_event_id") or "") not in existing_ids
    ]
    result = {
        **preview,
        "apply": apply,
        "appended_count": 0,
        "skipped_existing_count": len(preview["records"]) - len(appendable),
    }
    if not apply:
        return result

    if appendable:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as handle:
            for record in appendable:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        result["appended_count"] = len(appendable)
        result["audit_stream_exists"] = True
    return result


def append_universal_audit_record(root: Path, *, source_stream: str, source_ref: str, document: dict[str, Any]) -> dict[str, Any]:
    audit_path = root / AUDIT_STREAM_PATH
    record = _audit_record(source_stream, source_ref, document)
    if record["audit_event_id"] in _existing_audit_event_ids(audit_path):
        return {"status": "skipped_existing", "record": record, "audit_stream_path": AUDIT_STREAM_PATH}
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "appended", "record": record, "audit_stream_path": AUDIT_STREAM_PATH}


def _existing_audit_event_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for _, document in _iter_jsonl_documents(path):
        audit_event_id = document.get("audit_event_id")
        if isinstance(audit_event_id, str) and audit_event_id:
            ids.add(audit_event_id)
    return ids


def _iter_jsonl_documents(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            payload = line.strip()
            if not payload:
                continue
            try:
                document = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                rows.append((line_number, document))
    return rows


def _load_json_document(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _audit_record(source_stream: str, source_ref: str, document: dict[str, Any]) -> dict[str, Any]:
    event_type = _event_type(source_stream, document)
    occurred_at = _first_string(
        document,
        (
            "applied_at",
            "generated_at",
            "run_at",
            "created_at",
            "recorded_at",
            "completed_at",
            "started_at",
            "timestamp",
            "updated_at",
        ),
    )
    trace_id = _trace_id(document)
    subject = _subject(document, event_type)
    digest_payload = json.dumps(
        {
            "source_stream": source_stream,
            "source_ref": source_ref,
            "event_type": event_type,
            "subject": subject,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "audit_event_id": "audit-" + sha256_bytes(digest_payload.encode("utf-8"))[:20],
        "source_stream": source_stream,
        "source_ref": source_ref,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "trace_id": trace_id,
        "subject": subject,
        "revert_supported": bool(document.get("revert_supported", False)),
    }


def _event_type(source_stream: str, document: dict[str, Any]) -> str:
    if source_stream == "protocol_learnings_age":
        return "protocol_learnings_age"
    for key in ("operation", "event_type", "status", "kind"):
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return source_stream


def _trace_id(document: dict[str, Any]) -> str:
    value = document.get("trace_id")
    if isinstance(value, str):
        return value
    values = document.get("trace_ids")
    if isinstance(values, list):
        for item in values:
            if isinstance(item, str) and item:
                return item
    return ""


def _subject(document: dict[str, Any], event_type: str) -> dict[str, str]:
    subject_kind = _first_string(
        document,
        (
            "subject_kind",
            "proposal_kind",
            "kind",
            "event_type",
            "operation",
        ),
    )
    subject_id = _first_string(
        document,
        (
            "subject_id",
            "action_id",
            "batch_id",
            "proposal_id",
            "run_id",
            "signal_id",
            "elixir_id",
            "learning_id",
        ),
    )
    if not subject_kind:
        subject_kind = event_type
    return {"kind": subject_kind, "id": subject_id}


def _first_string(document: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _known_relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
