"""Aggregate local LLM receipt telemetry for operator reports."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .app_state import load_llm_receipt_history


def aggregate_llm_telemetry(root: Path, *, limit: int = 50) -> dict[str, Any]:
    """Summarize recent LLM receipts without exposing secrets or full prompts."""

    history = load_llm_receipt_history(root)
    recent = [item for item in history if isinstance(item, dict)][-max(1, limit) :]
    total = len(recent)
    status_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    error_classes: Counter[str] = Counter()
    latencies: list[int] = []

    for item in recent:
        status_counts[str(item.get("status") or "unknown")] += 1
        backend = str(item.get("backend_effective") or item.get("backend") or item.get("backend_requested") or "unknown")
        backend_counts[backend] += 1
        model = str(item.get("model_final") or item.get("model") or item.get("model_selected") or "")
        if model:
            model_counts[model] += 1
        error_class = str(item.get("error_class") or item.get("failure_reason") or "")
        if error_class and str(item.get("status") or "") in {"failed", "error", "blocked"}:
            error_classes[error_class] += 1
        duration = item.get("duration_ms")
        if isinstance(duration, (int, float)) and duration >= 0:
            latencies.append(int(duration))

    successes = sum(count for key, count in status_counts.items() if key in {"success", "ok"})
    failures = total - successes
    success_rate = round(successes / total, 4) if total else None

    return {
        "kind": "llm-telemetry-report",
        "version": 1,
        "receipt_path": ".aiwiki/logs/llm-receipts.jsonl",
        "sample_size": total,
        "limit": limit,
        "success_count": successes,
        "failure_count": failures,
        "success_rate": success_rate,
        "status_counts": dict(sorted(status_counts.items())),
        "backend_counts": dict(sorted(backend_counts.items())),
        "model_counts": dict(sorted(model_counts.items())),
        "error_class_counts": dict(sorted(error_classes.items())),
        "latency_ms": {
            "count": len(latencies),
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "max": max(latencies) if latencies else None,
        },
        "note": "Probe results from llm-check --probe are separate from run telemetry.",
    }


def _percentile(values: list[int], pct: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def aggregate_backend_telemetry(root: Path, *, limit: int = 100) -> dict[str, Any]:
    """Summarize execution receipts for operator backend/operation usage."""

    from .app_state import execution_receipt_history_path, load_jsonl_documents
    from .metrics_io import _receipt_json_paths

    records: list[dict[str, Any]] = []
    for path in _receipt_json_paths(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            records.append(payload)
    for item in load_jsonl_documents(execution_receipt_history_path(root)):
        if isinstance(item, dict):
            records.append(item)
    recent = records[-max(1, limit) :]
    operation_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    legacy_empty_status = 0
    for item in recent:
        operation = str(item.get("operation") or "unknown")
        operation_counts[operation] += 1
        status = str(item.get("status") or "").strip()
        if not status:
            legacy_empty_status += 1
            status = "legacy-empty"
        status_counts[status] += 1
        backend = str(
            item.get("llm_backend")
            or item.get("backend")
            or item.get("backend_effective")
            or ""
        ).strip()
        if backend:
            backend_counts[backend] += 1
    return {
        "kind": "backend-telemetry-report",
        "version": 1,
        "receipt_sources": [
            "output/control/execution-receipts/*.json",
            ".aiwiki/state/execution-receipts.jsonl",
        ],
        "sample_size": len(recent),
        "limit": limit,
        "operation_counts": dict(sorted(operation_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "backend_counts": dict(sorted(backend_counts.items())),
        "legacy_empty_status_count": legacy_empty_status,
        "note": "Backend fields appear on run-ask receipts when present; probe results stay separate.",
    }


__all__ = ["aggregate_backend_telemetry", "aggregate_llm_telemetry"]
