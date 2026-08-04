"""Legacy elixir migration — create superseded candidate tombstones for settled elixirs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..execution.receipts import compute_file_sha256
from ..render.paths import execution_receipts_dir
from ..utils.io import _restore_snapshots, _snapshot_file_bytes, atomic_write_text
from ..utils.path import relative_path
from .alchemy_helpers import (
    ELIXIR_DIR,
    LegacyMigrationApplyError,
    LegacyMigrationHalfWriteError,
    _candidate_path,
    _parse_elixir_frontmatter,
    _render_elixir_document,
    _resolve_elixir_id,
    _settled_path,
    _validate_state_for_path,
)
from .alchemy_receipts import _persist_receipt_transactionally

logger = logging.getLogger("aiwiki")

def preview_legacy_elixir_migration(root: Path, *, limit: int = 50) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    settled_root = root / ELIXIR_DIR
    records: list[dict[str, Any]] = []
    counts = {
        "legacy_missing_tombstone": 0,
        "current_tombstone": 0,
        "candidate_conflict": 0,
        "non_settled": 0,
    }
    scanned_count = 0
    if settled_root.exists():
        for path in sorted(settled_root.rglob("*.md")):
            scanned_count += 1
            try:
                frontmatter = _parse_elixir_frontmatter(path)
            except (OSError, ValueError) as exc:
                status = "candidate_conflict"
                record = {
                    "elixir_id": path.stem,
                    "wiki_path": relative_path(root, path),
                    "candidate_path": "",
                    "status": status,
                    "reason": f"parse_error: {exc}",
                    "migration_required": False,
                }
            else:
                elixir_id = str(frontmatter.get("elixir_id") or path.stem)
                state = str(frontmatter.get("elixir_state") or "")
                candidate_path = _candidate_path(root, elixir_id)
                if state != "settled":
                    status = "non_settled"
                    reason = f"wiki elixir state is {state or 'unknown'}"
                    migration_required = False
                elif not candidate_path.exists():
                    status = "legacy_missing_tombstone"
                    reason = "settled elixir has no candidate tombstone"
                    migration_required = True
                else:
                    try:
                        candidate_frontmatter = _parse_elixir_frontmatter(candidate_path)
                    except (OSError, ValueError) as exc:
                        status = "candidate_conflict"
                        reason = f"candidate_parse_error: {exc}"
                        migration_required = False
                    else:
                        candidate_state = str(candidate_frontmatter.get("elixir_state") or "")
                        superseded_by = str(candidate_frontmatter.get("superseded_by") or "")
                        if candidate_state == "superseded" and superseded_by == relative_path(root, path):
                            status = "current_tombstone"
                            reason = "candidate tombstone already matches settled elixir"
                            migration_required = False
                        else:
                            status = "candidate_conflict"
                            reason = f"candidate plane has state={candidate_state or 'unknown'}"
                            migration_required = False
                record = {
                    "elixir_id": elixir_id,
                    "wiki_path": relative_path(root, path),
                    "candidate_path": relative_path(root, candidate_path),
                    "status": status,
                    "reason": reason,
                    "migration_required": migration_required,
                }
            counts[status] += 1
            if len(records) < limit:
                records.append(record)

    return {
        "status": "ok",
        "mode": "dry_run",
        "side_effects_allowed": False,
        "scanned_count": scanned_count,
        "returned_count": len(records),
        "limit": limit,
        "counts": counts,
        "records": records,
    }


def apply_legacy_elixir_migration(root: Path, *, limit: int = 50, note: str | None = None) -> dict[str, Any]:
    preview = preview_legacy_elixir_migration(root, limit=limit)
    targets = [record for record in preview["records"] if record.get("migration_required")]
    applied_at_dt = datetime.now(timezone.utc)
    applied_at = applied_at_dt.isoformat()

    # Phase 1: plan — validate + render bytes, no writes.
    plans: list[dict[str, Any]] = []
    for record in targets:
        elixir_id = _resolve_elixir_id(root, str(record.get("elixir_id") or ""))
        settled_path = _settled_path(root, elixir_id)
        candidate_path = _candidate_path(root, elixir_id)
        if candidate_path.exists():
            continue
        frontmatter = _parse_elixir_frontmatter(settled_path)
        if str(frontmatter.get("elixir_state") or "") != "settled":
            continue
        original = settled_path.read_text(encoding="utf-8", errors="replace")
        body = original.split("---", 2)[-1].lstrip("\n")
        promoted_at = str(frontmatter.get("promoted_at") or "").strip() or applied_at
        tombstone_frontmatter = dict(frontmatter)
        tombstone_frontmatter.pop("sealed_at", None)
        tombstone_frontmatter.update(
            {
                "elixir_state": "superseded",
                "superseded_by": f"{ELIXIR_DIR}/{elixir_id}.md",
                "promoted_at": promoted_at,
            }
        )
        plans.append(
            {
                "elixir_id": elixir_id,
                "settled_path": settled_path,
                "candidate_path": candidate_path,
                "content": _render_elixir_document(tombstone_frontmatter, body),
                "promoted_at": promoted_at,
            }
        )

    # Phase 2: snapshot candidate paths (expected None — gate above ensured non-existence).
    candidate_snapshots: dict[Path, bytes | None] = {
        plan["candidate_path"]: _snapshot_file_bytes(plan["candidate_path"]) for plan in plans
    }

    # Phase 3: mutate.
    migrated: list[dict[str, Any]] = []
    try:
        for plan in plans:
            candidate_path = plan["candidate_path"]
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(candidate_path, plan["content"])
            _validate_state_for_path(root, "superseded", candidate_path)
            migrated.append(
                {
                    "elixir_id": plan["elixir_id"],
                    "wiki_path": relative_path(root, plan["settled_path"]),
                    "candidate_path": relative_path(root, candidate_path),
                    "promoted_at": plan["promoted_at"],
                    "candidate_sha256": compute_file_sha256(candidate_path),
                }
            )
    except Exception as tx_exc:
        logger.warning("legacy migration mutation failed; rolling back: %s", tx_exc)
        try:
            _restore_snapshots(candidate_snapshots)
        except Exception as rollback_exc:
            raise LegacyMigrationHalfWriteError(phase="mutation_rollback") from rollback_exc
        raise LegacyMigrationApplyError("legacy_migration_error: mutation failed; rolled back") from tx_exc

    # Phase 4: receipt (transactional).
    receipt_path_str = ""
    if migrated:
        receipt = _build_legacy_migration_receipt(root, migrated=migrated, applied_at=applied_at_dt, note=note)
        receipt_path_str = str(receipt.get("receipt_path") or "")

        _persist_receipt_transactionally(
            root,
            receipt=receipt,
            elixir_id="legacy-migration",
            operation="legacy_migration",
            rollback_data=lambda: _restore_snapshots(candidate_snapshots),
            receipt_error_cls=LegacyMigrationApplyError,
            half_write_error_factory=lambda phase: LegacyMigrationHalfWriteError(phase=phase),
        )

    return {
        **preview,
        "mode": "apply",
        "apply": True,
        "side_effects_allowed": True,
        "applied_at": applied_at,
        "migrated_count": len(migrated),
        "migrated": migrated,
        "receipt_path": receipt_path_str,
    }


def _build_legacy_migration_receipt(
    root: Path,
    *,
    migrated: list[dict[str, Any]],
    applied_at: datetime,
    note: str | None,
) -> dict[str, Any]:
    action_id = _unique_legacy_migration_action_id(root, applied_at)
    receipt_path = execution_receipts_dir(root) / f"{action_id}.json"
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-elixir-legacy-migration",
        "applied_at": applied_at.isoformat(),
        "operation": "legacy-migrate",
        "action_id": action_id,
        "title": "Migrate legacy elixir tombstones",
        "status": "resolved",
        "protocol": "",
        "subject_kind": "elixir_legacy_migration",
        "subject_id": action_id,
        "apply_mode": "elixir-legacy-migration",
        "note": note or "",
        "primary_path": "",
        "secondary_path": "",
        "receipt_path": relative_path(root, receipt_path),
        "bundle": {
            "created_tombstones": migrated,
            "created_count": len(migrated),
        },
        "safe_apply_preview": None,
        "revert_supported": False,
    }


def _unique_legacy_migration_action_id(root: Path, applied_at: datetime) -> str:
    epoch_ms = int(applied_at.timestamp() * 1000)
    candidate = f"elixir-legacy-migration-{epoch_ms}"
    n = 2
    while (execution_receipts_dir(root) / f"{candidate}.json").exists():
        candidate = f"elixir-legacy-migration-{epoch_ms}-{n}"
        n += 1
    return candidate

