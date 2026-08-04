"""Authoritative execution receipt writers for runtime actions.

Owner for execution receipt assembly (runtime actions + elixir lifecycle).
Extracted from the legacy ``app_execution`` hub.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..render.paths import (
    execution_receipt_path,
    execution_receipts_dir,
)
from ..state.io import load_jsonl_documents_strict
from ..utils.io import atomic_write_text
from ..utils.path import next_available_stem, relative_path
from ..utils.text import slugify
from ..utils.time import utc_now
from .history import append_execution_receipt_history
from .paths import execution_receipt_history_path
from .types import ExecutionReceipt

_CORE_RECEIPT_FIELDS = {
    "version",
    "kind",
    "generated_by",
    "applied_at",
    "operation",
    "status",
    "action_id",
    "subject_kind",
    "subject_id",
    "target_file",
    "primary_path",
    "receipt_path",
    "revert_supported",
}


class ExecutionReceiptValidationError(ValueError):
    """Raised when an execution receipt is missing required fields."""


def _validate_execution_receipt_fields(
    *,
    operation: str,
    status: str,
    target_file: str,
) -> None:
    if not str(operation or "").strip():
        raise ExecutionReceiptValidationError("operation must be non-empty")
    if not str(status or "").strip():
        raise ExecutionReceiptValidationError("status must be non-empty")
    if not str(target_file or "").strip():
        raise ExecutionReceiptValidationError("target_file must be non-empty")


def write_execution_receipt(
    root: Path,
    *,
    operation: str,
    generated_by: str,
    subject_kind: str,
    subject_id: str,
    target_file: str,
    status: str = "success",
    primary_path: str = "",
    secondary_path: str = "",
    protocol: str = "",
    revert_supported: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a JSON execution receipt and append it to receipt history.

    This is the action-level audit stream consumed by dogfood maturity gates.
    It is intentionally separate from LLM attempt telemetry.
    """

    _validate_execution_receipt_fields(operation=operation, status=status, target_file=target_file)
    receipt_dir = execution_receipts_dir(root)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    seed_target = Path(target_file).stem or subject_id or operation
    seed = slugify(f"{operation}-{seed_target}") or slugify(operation) or "execution-receipt"
    action_id = next_available_stem(receipt_dir, seed, suffix=".json")
    receipt_path = receipt_dir / f"{action_id}.json"
    receipt_rel = relative_path(root, receipt_path)
    receipt: dict[str, Any] = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": generated_by,
        "applied_at": utc_now(),
        "operation": operation,
        "status": status,
        "action_id": action_id,
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "target_file": target_file,
        "primary_path": primary_path or target_file,
        "receipt_path": receipt_rel,
        "revert_supported": bool(revert_supported),
    }
    if secondary_path:
        receipt["secondary_path"] = secondary_path
    if protocol:
        receipt["protocol"] = protocol
    if extra:
        receipt.update({key: value for key, value in extra.items() if key not in _CORE_RECEIPT_FIELDS})
    atomic_write_text(
        receipt_path,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    try:
        append_execution_receipt_history(root, receipt)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            receipt_path.unlink()
        raise
    return receipt


def compute_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unique_elixir_action_id(root: Path, base: str, applied_at: datetime) -> str:
    epoch_ms = int(applied_at.timestamp() * 1000)
    candidate = f"{base}-{epoch_ms}"
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{epoch_ms}-{n}"
        n += 1
    return candidate


def build_elixir_promotion_receipt(
    root: Path,
    *,
    elixir_id: str,
    slug: str,
    settled_path: Path,
    candidate_path: Path,
    protocol: str,
    applied_at: datetime | None = None,
    note: str | None,
    primary_path_sha256: str,
    secondary_path_sha256: str,
    counter_evidence: list[str],
    confidence_level: str,
    counter_evidence_provenance: str,
) -> ExecutionReceipt:
    applied_at_value = applied_at or datetime.now(timezone.utc)
    applied_at_iso = applied_at_value.isoformat()
    action_id = _unique_elixir_action_id(root, f"elixir-promote-{slug}", applied_at_value)
    receipt_path = execution_receipt_path(root, action_id)
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-elixir-promote",
        "applied_at": applied_at_iso,
        "operation": "promote",
        "action_id": action_id,
        "title": f"Promote elixir {elixir_id}",
        "status": "resolved",
        "protocol": protocol,
        "subject_kind": "elixir_promotion",
        "subject_id": elixir_id,
        "apply_mode": "elixir-promote",
        "note": note or "",
        "primary_path": relative_path(root, settled_path),
        "secondary_path": relative_path(root, candidate_path),
        "receipt_path": relative_path(root, receipt_path),
        "bundle": {
            "primary_path_sha256": primary_path_sha256,
            "secondary_path_sha256": secondary_path_sha256,
            "counter_evidence": list(counter_evidence),
            "confidence_level": confidence_level,
            "counter_evidence_provenance": counter_evidence_provenance,
        },
        "safe_apply_preview": None,
    }


def build_elixir_revert_receipt(
    root: Path,
    *,
    elixir_id: str,
    slug: str,
    wiki_path: Path,
    candidate_path: Path,
    protocol: str,
    applied_at: datetime | None = None,
    note: str | None,
    source_receipt_applied_at: str,
    source_receipt_action_id: str,
    dependency_breaks: list[dict[str, Any]] | None = None,
) -> ExecutionReceipt:
    applied_at_value = applied_at or datetime.now(timezone.utc)
    applied_at_iso = applied_at_value.isoformat()
    action_id = _unique_elixir_action_id(root, f"elixir-revert-{slug}", applied_at_value)
    receipt_path = execution_receipt_path(root, action_id)
    bundle: dict[str, Any] = {
        "from_state": "settled",
        "tombstone_from_state": "superseded",
        "to_state": "candidate",
        "candidate_path": relative_path(root, candidate_path),
        "wiki_path": relative_path(root, wiki_path),
        "source_receipt_applied_at": source_receipt_applied_at,
        "source_receipt_action_id": source_receipt_action_id,
    }
    if dependency_breaks is not None:
        bundle["dependency_breaks"] = list(dependency_breaks)

    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-elixir-revert",
        "applied_at": applied_at_iso,
        "operation": "revert",
        "action_id": action_id,
        "title": f"Revert elixir {elixir_id}",
        "status": "resolved",
        "protocol": protocol,
        "subject_kind": "elixir_revert",
        "subject_id": elixir_id,
        "apply_mode": "elixir-revert",
        "note": note or "",
        "primary_path": relative_path(root, candidate_path),
        "secondary_path": relative_path(root, wiki_path),
        "receipt_path": relative_path(root, receipt_path),
        "bundle": bundle,
        "safe_apply_preview": None,
    }


def build_elixir_demotion_receipt(
    root: Path,
    *,
    elixir_id: str,
    slug: str,
    wiki_path: Path,
    candidate_path: Path,
    protocol: str,
    applied_at: datetime | None = None,
    note: str | None,
    dependency_breaks: list[dict[str, Any]] | None = None,
) -> ExecutionReceipt:
    applied_at_value = applied_at or datetime.now(timezone.utc)
    applied_at_iso = applied_at_value.isoformat()
    action_id = _unique_elixir_action_id(root, f"elixir-demote-{slug}", applied_at_value)
    receipt_path = execution_receipt_path(root, action_id)
    bundle: dict[str, Any] = {
        "from_state": "settled",
        "to_state": "candidate",
        "candidate_path": relative_path(root, candidate_path),
        "wiki_path": relative_path(root, wiki_path),
    }
    if dependency_breaks is not None:
        bundle["dependency_breaks"] = list(dependency_breaks)

    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-elixir-demote",
        "applied_at": applied_at_iso,
        "operation": "demote",
        "action_id": action_id,
        "title": f"Demote elixir {elixir_id}",
        "status": "resolved",
        "protocol": protocol,
        "subject_kind": "elixir_demotion",
        "subject_id": elixir_id,
        "apply_mode": "elixir-demote",
        "note": note or "",
        "primary_path": relative_path(root, candidate_path),
        "secondary_path": relative_path(root, wiki_path),
        "receipt_path": relative_path(root, receipt_path),
        "bundle": bundle,
        "safe_apply_preview": None,
    }


def find_latest_elixir_promotion_receipt(root: Path, *, elixir_id: str) -> dict[str, Any] | None:
    """Authoritative reader for elixir promotion receipts (used by revert hash-gate).

    Fail-closed semantics: corrupt JSONL lines raise ``CorruptStateError`` rather than being
    silently skipped. A corrupt receipt history can otherwise cause revert to select a stale
    receipt or report missing, both of which are silent fact-layer corruption.
    """
    path = execution_receipt_history_path(root)
    latest: dict[str, Any] | None = None
    for entry in load_jsonl_documents_strict(path):
        if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
            latest = entry
    return latest


__all__ = [
    "ExecutionReceiptValidationError",
    "build_elixir_demotion_receipt",
    "build_elixir_promotion_receipt",
    "build_elixir_revert_receipt",
    "compute_file_sha256",
    "find_latest_elixir_promotion_receipt",
    "write_execution_receipt",
]
