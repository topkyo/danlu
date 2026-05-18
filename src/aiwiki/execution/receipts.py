"""Authoritative execution receipt writers for runtime actions."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from ..app_execution import append_execution_receipt_history
from ..app_utils import atomic_write_text, next_available_stem, relative_path, slugify, utc_now

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
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a JSON execution receipt and append it to receipt history.

    This is the action-level audit stream consumed by dogfood maturity gates.
    It is intentionally separate from LLM attempt telemetry.
    """

    receipt_dir = root / "output" / "control" / "execution-receipts"
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
        "revert_supported": False,
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
