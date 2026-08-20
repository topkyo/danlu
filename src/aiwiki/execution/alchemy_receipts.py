"""Transactional receipt persistence helpers for alchemy execution."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from ..execution.history import append_execution_receipt_history
from ..utils.io import _restore_file_bytes, _snapshot_file_bytes, atomic_write_text
from .alchemy_helpers import ElixirMutationBoundaryError
from .audit_preview import AUDIT_STREAM_PATH
from .paths import execution_receipt_history_path

logger = logging.getLogger("aiwiki")

def _snapshot_receipt_artifacts(root: Path) -> dict[str, tuple[Path, bytes | None]]:
    """Snapshot receipt-side artifacts before a mutation receipt is persisted.

    Includes:
        - execution receipt history JSONL
        - universal audit stream JSONL

    Per-action receipt files are snapshot lazily once their path is known
    (see ``_persist_receipt_transactionally`` and the inline promote receipt block).
    """
    history_path = execution_receipt_history_path(root)
    audit_path = root / AUDIT_STREAM_PATH
    return {
        "history": (history_path, _snapshot_file_bytes(history_path)),
        "audit": (audit_path, _snapshot_file_bytes(audit_path)),
    }


def _restore_receipt_artifacts(snapshots: dict[str, tuple[Path, bytes | None]]) -> None:
    """Restore receipt-side artifacts to pre-mutation bytes. Best-effort error-collecting."""
    errors: list[Exception] = []
    for path, snapshot in snapshots.values():
        try:
            _restore_file_bytes(path, snapshot)
        except Exception as exc:  # pragma: no cover - escalated via aggregate
            errors.append(exc)
    if errors:
        raise errors[0]


def _persist_receipt_transactionally(
    root: Path,
    *,
    receipt: dict[str, Any],
    elixir_id: str,
    operation: str,
    rollback_data: Callable[[], None],
    receipt_error_cls: type[ElixirMutationBoundaryError],
    half_write_error_factory: Callable[[str], RuntimeError],
) -> Path:
    """Persist a mutation receipt as a single transaction.

    Writes the per-action receipt JSON, appends to ``execution-receipts.jsonl`` and the universal
    audit stream. On any failure: restores per-action receipt bytes + history JSONL + audit JSONL,
    then invokes ``rollback_data()`` to restore the data-layer artifacts that triggered the receipt.

    On secondary failure (rollback itself fails) raises ``half_write_error_factory(phase)`` so the
    caller can surface a half-write boundary error.
    """
    receipt_path = root / str(receipt.get("receipt_path") or "")
    receipt_artifact_snapshots = _snapshot_receipt_artifacts(root)
    receipt_path_snapshot = _snapshot_file_bytes(receipt_path)
    try:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        append_execution_receipt_history(root, receipt)
    except Exception as receipt_exc:
        logger.warning(
            "elixir %s receipt persistence failed for %s; rolling back mutation: %s",
            operation,
            elixir_id,
            receipt_exc,
        )
        try:
            _restore_file_bytes(receipt_path, receipt_path_snapshot)
            _restore_receipt_artifacts(receipt_artifact_snapshots)
            rollback_data()
        except Exception as rollback_exc:
            raise half_write_error_factory("receipt_rollback") from rollback_exc
        raise receipt_error_cls(
            f"{operation}_receipt_error: receipt persistence failed for elixir {elixir_id}; mutation rolled back"
        ) from receipt_exc
    return receipt_path

