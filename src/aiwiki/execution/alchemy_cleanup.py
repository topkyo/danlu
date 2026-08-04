"""Superseded elixir cleanup — delete obsolete candidate tombstones."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..execution.receipts import compute_file_sha256
from ..render.paths import execution_receipts_dir
from ..utils.io import _restore_snapshots, _snapshot_file_bytes
from ..utils.path import relative_path
from .alchemy_helpers import (
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    SupersededCleanupApplyError,
    SupersededCleanupHalfWriteError,
    _candidate_path,
    _parse_elixir_frontmatter,
    _resolve_elixir_id,
    _settled_path,
)
from .alchemy_receipts import _persist_receipt_transactionally

logger = logging.getLogger("aiwiki")

def preview_superseded_elixir_cleanup(root: Path, *, limit: int = 50) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    candidate_root = root / CANDIDATE_ELIXIR_DIR
    records: list[dict[str, Any]] = []
    counts = {
        "cleanup_candidate": 0,
        "missing_superseded_target": 0,
        "non_settled_target": 0,
        "candidate_conflict": 0,
        "non_superseded": 0,
    }
    scanned_count = 0
    if candidate_root.exists():
        for path in sorted(candidate_root.rglob("*.md")):
            scanned_count += 1
            try:
                frontmatter = _parse_elixir_frontmatter(path)
            except (OSError, ValueError) as exc:
                status = "candidate_conflict"
                record = {
                    "elixir_id": path.stem,
                    "candidate_path": relative_path(root, path),
                    "superseded_by": "",
                    "status": status,
                    "reason": f"parse_error: {exc}",
                    "cleanup_supported": False,
                }
            else:
                elixir_id = str(frontmatter.get("elixir_id") or path.stem)
                state = str(frontmatter.get("elixir_state") or "")
                superseded_by = str(frontmatter.get("superseded_by") or "")
                if state != "superseded":
                    status = "non_superseded"
                    record = {
                        "elixir_id": elixir_id,
                        "candidate_path": relative_path(root, path),
                        "superseded_by": superseded_by,
                        "status": status,
                        "reason": f"candidate state is {state or 'unknown'}",
                        "cleanup_supported": False,
                    }
                elif not superseded_by:
                    status = "candidate_conflict"
                    record = {
                        "elixir_id": elixir_id,
                        "candidate_path": relative_path(root, path),
                        "superseded_by": "",
                        "status": status,
                        "reason": "superseded tombstone missing superseded_by",
                        "cleanup_supported": False,
                    }
                else:
                    target_path = (root / superseded_by).resolve()
                    settled_root = (root / ELIXIR_DIR).resolve()
                    if (
                        not (target_path == settled_root or settled_root in target_path.parents)
                        or target_path.suffix != ".md"
                    ):
                        status = "candidate_conflict"
                        reason = f"superseded_by outside settled elixir plane: {superseded_by}"
                        cleanup_supported = False
                    elif not target_path.exists():
                        status = "missing_superseded_target"
                        reason = "superseded target is missing"
                        cleanup_supported = False
                    else:
                        try:
                            target_frontmatter = _parse_elixir_frontmatter(target_path)
                        except (OSError, ValueError) as exc:
                            status = "candidate_conflict"
                            reason = f"target_parse_error: {exc}"
                            cleanup_supported = False
                        else:
                            target_state = str(target_frontmatter.get("elixir_state") or "")
                            if target_state != "settled":
                                status = "non_settled_target"
                                reason = f"superseded target state is {target_state or 'unknown'}"
                                cleanup_supported = False
                            else:
                                status = "cleanup_candidate"
                                reason = "valid superseded tombstone; deletion apply supported"
                                cleanup_supported = True
                    record = {
                        "elixir_id": elixir_id,
                        "candidate_path": relative_path(root, path),
                        "superseded_by": superseded_by,
                        "status": status,
                        "reason": reason,
                        "cleanup_supported": cleanup_supported,
                    }
            counts[status] += 1
            if len(records) < limit:
                records.append(record)

    return {
        "status": "ok",
        "mode": "dry_run",
        "side_effects_allowed": False,
        "delete_supported": True,
        "scanned_count": scanned_count,
        "returned_count": len(records),
        "limit": limit,
        "counts": counts,
        "records": records,
    }


def apply_superseded_elixir_cleanup(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    preview = preview_superseded_elixir_cleanup(root, limit=limit)
    targets = [record for record in preview["records"] if record.get("cleanup_supported")]
    applied_at_dt = datetime.now(timezone.utc)
    applied_at = applied_at_dt.isoformat()

    # Phase 1: plan — re-validate and collect deletion plans (no mutation).
    plans: list[dict[str, Any]] = []
    for record in targets:
        elixir_id = _resolve_elixir_id(root, str(record.get("elixir_id") or ""))
        candidate_path = _candidate_path(root, elixir_id)
        settled_path = _settled_path(root, elixir_id)
        if not candidate_path.exists():
            continue
        candidate_frontmatter = _parse_elixir_frontmatter(candidate_path)
        if str(candidate_frontmatter.get("elixir_state") or "") != "superseded":
            continue
        superseded_by = str(candidate_frontmatter.get("superseded_by") or "")
        if superseded_by != relative_path(root, settled_path):
            continue
        if not settled_path.exists():
            continue
        settled_frontmatter = _parse_elixir_frontmatter(settled_path)
        if str(settled_frontmatter.get("elixir_state") or "") != "settled":
            continue
        plans.append(
            {
                "elixir_id": elixir_id,
                "candidate_path": candidate_path,
                "settled_path": settled_path,
                "candidate_sha256": compute_file_sha256(candidate_path),
                "settled_sha256": compute_file_sha256(settled_path),
            }
        )

    # Phase 2: snapshot candidate bytes BEFORE unlink (these are the rollback sources).
    candidate_snapshots: dict[Path, bytes | None] = {
        plan["candidate_path"]: _snapshot_file_bytes(plan["candidate_path"]) for plan in plans
    }

    # Phase 3: mutate (unlink).
    deleted: list[dict[str, Any]] = []
    try:
        for plan in plans:
            plan["candidate_path"].unlink()
            deleted.append(
                {
                    "elixir_id": plan["elixir_id"],
                    "candidate_path": relative_path(root, plan["candidate_path"]),
                    "settled_path": relative_path(root, plan["settled_path"]),
                    "candidate_sha256": plan["candidate_sha256"],
                    "settled_sha256": plan["settled_sha256"],
                }
            )
    except Exception as tx_exc:
        logger.warning("superseded cleanup mutation failed; rolling back: %s", tx_exc)
        try:
            _restore_snapshots(candidate_snapshots)
        except Exception as rollback_exc:
            raise SupersededCleanupHalfWriteError(phase="mutation_rollback") from rollback_exc
        raise SupersededCleanupApplyError("superseded_cleanup_error: mutation failed; rolled back") from tx_exc

    # Phase 4: receipt (transactional).
    receipt_path_str = ""
    if deleted:
        receipt = _build_superseded_cleanup_receipt(root, deleted=deleted, applied_at=applied_at_dt, note=note)
        receipt_path_str = str(receipt.get("receipt_path") or "")

        _persist_receipt_transactionally(
            root,
            receipt=receipt,
            elixir_id="superseded-cleanup",
            operation="superseded_cleanup",
            rollback_data=lambda: _restore_snapshots(candidate_snapshots),
            receipt_error_cls=SupersededCleanupApplyError,
            half_write_error_factory=lambda phase: SupersededCleanupHalfWriteError(phase=phase),
        )

    return {
        **preview,
        "mode": "apply",
        "apply": True,
        "side_effects_allowed": True,
        "applied_at": applied_at,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "receipt_path": receipt_path_str,
    }


def _build_superseded_cleanup_receipt(
    root: Path,
    *,
    deleted: list[dict[str, Any]],
    applied_at: datetime,
    note: str | None,
) -> dict[str, Any]:
    action_id = _unique_superseded_cleanup_action_id(root, applied_at)
    receipt_path = execution_receipts_dir(root) / f"{action_id}.json"
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-elixir-superseded-cleanup",
        "applied_at": applied_at.isoformat(),
        "operation": "superseded-cleanup",
        "action_id": action_id,
        "title": "Delete superseded elixir candidate tombstones",
        "status": "resolved",
        "protocol": "",
        "subject_kind": "elixir_superseded_cleanup",
        "subject_id": action_id,
        "apply_mode": "elixir-superseded-cleanup",
        "note": note or "",
        "primary_path": "",
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "bundle": {
            "deleted_tombstones": deleted,
            "deleted_count": len(deleted),
        },
        "safe_apply_preview": None,
        "revert_supported": False,
    }


def _unique_superseded_cleanup_action_id(root: Path, applied_at: datetime) -> str:
    epoch_ms = int(applied_at.timestamp() * 1000)
    candidate = f"elixir-superseded-cleanup-{epoch_ms}"
    n = 2
    while (execution_receipts_dir(root) / f"{candidate}.json").exists():
        candidate = f"elixir-superseded-cleanup-{epoch_ms}-{n}"
        n += 1
    return candidate

