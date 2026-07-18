"""Aggregate local LLM receipt telemetry for operator reports."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .execution.history import load_llm_receipt_history
from .llm import classify_backend_error


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
        backend = str(
            item.get("backend_effective") or item.get("backend") or item.get("backend_requested") or "unknown"
        )
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
    """Summarize recent execution and LLM receipts for operator backend usage."""

    from .app_state_paths import execution_receipt_history_path
    from .metrics_io import _receipt_json_paths
    from .state.io import load_jsonl_documents

    records: list[dict[str, Any]] = []
    seen_receipt_paths: set[str] = set()

    def add_record(payload: dict[str, Any]) -> None:
        receipt_path = str(payload.get("receipt_path") or "")
        if receipt_path:
            if receipt_path in seen_receipt_paths:
                return
            seen_receipt_paths.add(receipt_path)
        records.append(payload)

    for item in load_jsonl_documents(execution_receipt_history_path(root)):
        if isinstance(item, dict):
            add_record(item)
    for path in _receipt_json_paths(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            add_record(payload)
    ordered_records = [
        item
        for _, item in sorted(
            enumerate(records),
            key=lambda pair: (_receipt_timestamp(pair[1]), pair[0]),
        )
    ]
    recent = ordered_records[-max(1, limit) :]
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
        backend = str(item.get("llm_backend") or item.get("backend") or item.get("backend_effective") or "").strip()
        if backend:
            backend_counts[backend] += 1

    llm_history = [item for item in load_llm_receipt_history(root) if isinstance(item, dict)]
    llm_ordered = [
        item
        for _, item in sorted(
            enumerate(llm_history),
            key=lambda pair: (_receipt_timestamp(pair[1]), pair[0]),
        )
    ]
    llm_recent = llm_ordered[-max(1, limit) :]
    llm_status_counts: Counter[str] = Counter()
    llm_backend_counts: Counter[str] = Counter()
    llm_model_counts: Counter[str] = Counter()
    llm_error_class_counts: Counter[str] = Counter()
    llm_failure_category_counts: Counter[str] = Counter()
    failure_samples: list[dict[str, Any]] = []
    for item in llm_recent:
        llm_status = str(item.get("status") or "unknown")
        llm_status_counts[llm_status] += 1
        backend = str(
            item.get("backend_effective") or item.get("backend") or item.get("backend_requested") or "unknown"
        )
        llm_backend_counts[backend] += 1
        model = str(item.get("model_final") or item.get("model") or item.get("model_selected") or "")
        if model:
            llm_model_counts[model] += 1
        if llm_status not in {"failed", "error", "blocked"}:
            continue
        error_class = str(item.get("error_class") or "").strip()
        if error_class:
            llm_error_class_counts[error_class] += 1
        category = _llm_failure_category(item)
        llm_failure_category_counts[category] += 1
        failure_samples.append(
            {
                "event": str(item.get("event") or ""),
                "status": llm_status,
                "backend": backend,
                "model": model,
                "error_class": error_class,
                "failure_category": category,
                "created_at": str(item.get("created_at") or ""),
                "raw_response_path": str(item.get("raw_response_path") or ""),
            }
        )
    return {
        "kind": "backend-telemetry-report",
        "version": 2,
        "receipt_sources": [
            ".aiwiki/state/execution-receipts/*.json",
            ".aiwiki/state/execution-receipts.jsonl",
            ".aiwiki/logs/llm-receipts.jsonl",
        ],
        "sample_size": len(recent),
        "execution_sample_size": len(recent),
        "llm_sample_size": len(llm_recent),
        "limit": limit,
        "operation_counts": dict(sorted(operation_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "backend_counts": dict(sorted(backend_counts.items())),
        "legacy_empty_status_count": legacy_empty_status,
        "llm_status_counts": dict(sorted(llm_status_counts.items())),
        "llm_backend_counts": dict(sorted(llm_backend_counts.items())),
        "llm_model_counts": dict(sorted(llm_model_counts.items())),
        "llm_error_class_counts": dict(sorted(llm_error_class_counts.items())),
        "llm_failure_category_counts": dict(sorted(llm_failure_category_counts.items())),
        "quota_failure_count": int(llm_failure_category_counts.get("quota", 0)),
        "timeout_failure_count": int(llm_failure_category_counts.get("timeout", 0)),
        "unavailable_failure_count": int(llm_failure_category_counts.get("unavailable", 0)),
        "recent_failures": failure_samples[-8:],
        "note": (
            "Execution receipts show operation usage; LLM receipts add "
            "quota/timeout/unavailable classifications. Probe results stay separate."
        ),
    }


def _llm_failure_category(item: dict[str, Any]) -> str:
    explicit = str(item.get("error_class") or "").strip().lower()
    if explicit in {"quota", "timeout", "auth", "unavailable"}:
        return explicit
    text = " ".join(
        str(item.get(key) or "") for key in ("error", "failure_reason", "primary_error", "fallback_reason")
    ).strip()
    return classify_backend_error(text or explicit)


def _receipt_timestamp(item: dict[str, Any]) -> str:
    return str(
        item.get("applied_at") or item.get("created_at") or item.get("generated_at") or item.get("updated_at") or ""
    )


__all__ = ["aggregate_backend_telemetry", "aggregate_llm_telemetry"]
