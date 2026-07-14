from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_utils import atomic_append_jsonl, runtime_write_lock, sha256_bytes
from .log_writer import _PLANNER_LOG_REL_PATH
from .schema import compute_planner_log_dedupe_key, validate_planner_log_record

_ROLLBACK_LOG_REL_PATH = ".aiwiki/state/planner-log-rollback.jsonl"


def preview_planner_log_rollback(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    path = root / _PLANNER_LOG_REL_PATH
    records: list[dict[str, Any]] = []
    scanned_count = 0
    matched_count = 0

    for line_number, record in _iter_planner_log(path):
        scanned_count += 1
        if signal_id is not None and record.get("signal_id") != signal_id:
            continue
        if trace_id is not None and record.get("trace_id") != trace_id:
            continue
        matched_count += 1
        if len(records) < limit:
            records.append(_rollback_preview_record(line_number, record))

    return {
        "status": "ok",
        "mode": "dry_run",
        "side_effects_allowed": False,
        "log_path": _PLANNER_LOG_REL_PATH,
        "scanned_count": scanned_count,
        "matched_count": matched_count,
        "returned_count": len(records),
        "limit": limit,
        "filters": {
            "signal_id": signal_id or "",
            "trace_id": trace_id or "",
        },
        "delete_supported": False,
        "rollback_strategy": "append_marker",
        "marker_planned": True,
        "records": records,
    }


def apply_planner_log_rollback_marker(
    root: Path,
    *,
    signal_id: str | None = None,
    trace_id: str | None = None,
    limit: int = 20,
    apply: bool = False,
) -> dict[str, Any]:
    preview = preview_planner_log_rollback(root, signal_id=signal_id, trace_id=trace_id, limit=limit)
    marker_path = root / _ROLLBACK_LOG_REL_PATH
    markers = [_marker_from_preview_record(record) for record in preview["records"] if isinstance(record, dict)]
    existing_ids = _existing_marker_ids(marker_path)
    appendable = [marker for marker in markers if marker["rollback_marker_id"] not in existing_ids]
    result = {
        **preview,
        "apply": apply,
        "rollback_log_path": _ROLLBACK_LOG_REL_PATH,
        "appended_count": 0,
        "skipped_existing_count": len(markers) - len(appendable),
        "markers": markers,
    }
    if not apply:
        return result

    with runtime_write_lock(root):
        if appendable:
            for marker in appendable:
                atomic_append_jsonl(marker_path, marker)
            result["appended_count"] = len(appendable)
    return result


def _iter_planner_log(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return []
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            payload = raw_line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid planner-log.jsonl JSON at line {line_number}: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"invalid planner-log.jsonl record at line {line_number}: expected object")
            validation = validate_planner_log_record(record)
            if not validation.ok:
                raise ValueError(f"invalid planner-log.jsonl record at line {line_number}: {'; '.join(validation.errors)}")
            records.append((line_number, record))
    return records


def _rollback_preview_record(line_number: int, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_ref": f"{_PLANNER_LOG_REL_PATH}#L{line_number}",
        "signal_id": str(record.get("signal_id") or ""),
        "trace_id": str(record.get("trace_id") or ""),
        "decision": str(record.get("decision") or ""),
        "mode": str(record.get("mode") or ""),
        "dedupe_key": compute_planner_log_dedupe_key(record),
        "decided_at": str(record.get("decided_at") or ""),
        "delete_supported": False,
        "rollback_strategy": "append_marker",
        "marker_planned": True,
    }


def _marker_from_preview_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "source_ref": str(record.get("source_ref") or ""),
        "signal_id": str(record.get("signal_id") or ""),
        "trace_id": str(record.get("trace_id") or ""),
        "decision": str(record.get("decision") or ""),
        "mode": str(record.get("mode") or ""),
    }
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))[:20]
    return {
        "schema_version": 1,
        "rollback_marker_id": f"planner-rollback-{digest}",
        **payload,
        "dedupe_key": str(record.get("dedupe_key") or ""),
        "decided_at": str(record.get("decided_at") or ""),
        "rollback_strategy": "append_marker",
        "delete_supported": False,
    }


def _existing_marker_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            payload = raw_line.strip()
            if not payload:
                continue
            try:
                record = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            rollback_marker_id = record.get("rollback_marker_id")
            if isinstance(rollback_marker_id, str) and rollback_marker_id:
                ids.add(rollback_marker_id)
    return ids
