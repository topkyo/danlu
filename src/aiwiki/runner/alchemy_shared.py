"""Shared helpers for alchemy apply primitives."""

from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.render.paths import execution_receipt_path


def _apply_paths(root, action_id, deps):
    receipt_path = execution_receipt_path(root, action_id)
    history_path = deps["execution_receipt_history_path"](root)
    audit_path = deps["relative_path"](root, history_path)
    return receipt_path, history_path, audit_path


def _capture_sizes(root, history_path):
    history_size = history_path.stat().st_size if history_path.exists() else 0
    audit_jsonl_path = root / AUDIT_STREAM_PATH
    audit_size = audit_jsonl_path.stat().st_size if audit_jsonl_path.exists() else 0
    return audit_jsonl_path, history_size, audit_size


def _trace_summary(deps, preview, candidates):
    trace_ids = deps["preview_trace_ids"](preview)
    trace_id = trace_ids[0] if trace_ids else ""
    candidate_ids = [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")]
    return trace_ids, trace_id, candidate_ids


def _rollback_truncate(deps, history_path, history_size, audit_jsonl_path, audit_size):
    if history_path.exists():
        deps["durable_truncate"](history_path, history_size)
    if audit_jsonl_path.exists():
        deps["durable_truncate"](audit_jsonl_path, audit_size)
