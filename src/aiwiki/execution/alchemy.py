"""Alchemy execution — mutation layer.

Owns: filesystem writes, atomic rename, snapshot/restore, receipt persistence
for elixir lifecycle (start → distill → finalize → promote/demote/revert).

Boundary: mutation only. Higher-level orchestration lives in
``runner/alchemy.py``. Transactional helpers (``_snapshot_file_bytes`` /
``_restore_file_bytes``) live in ``aiwiki.utils.io``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ..app_execution import (
    append_execution_receipt_history,
    build_elixir_demotion_receipt,
    build_elixir_promotion_receipt,
    build_elixir_revert_receipt,
    compute_file_sha256,
    find_latest_elixir_promotion_receipt,
)
from ..app_protocol import PROTOCOL_ELIXIR_REVIEW_DAYS
from ..app_state_paths import execution_receipt_history_path
from ..content.material import load_active_corpora_state
from ..render.paths import execution_receipts_dir
from ..utils.hash import sha256_bytes
from ..utils.io import _restore_file_bytes, _restore_snapshots, _snapshot_file_bytes, atomic_write_text
from ..utils.markdown import parse_frontmatter, strip_frontmatter
from ..utils.path import next_available_stem, relative_path
from ..utils.text import slugify
from ..utils.time import utc_now
from .alchemy_helpers import validate_promote_gate
from .audit_preview import AUDIT_STREAM_PATH
from .candidates import load_output_candidates_state

ELIXIR_DIR = "wiki/elixirs"
CANDIDATE_ELIXIR_DIR = ".aiwiki/staging/elixirs"
ELIXIR_STATE_VALUES = {"draft", "distilling", "candidate", "settled", "superseded"}
_ACTIVE_ELIXIR_STATES = {"draft", "distilling", "candidate"}
_PROMOTION_TS_FIELD = "promoted_at"
_PENDING_REFINEMENT_RE = re.compile(r"(?im)^\s*-\s*pending\s+refinement\.?\s*$")
logger = logging.getLogger("aiwiki")


class PromoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"promote_half_write_error[{phase}]: failed to rollback after promote failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class RevertHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"revert_half_write_error[{phase}]: failed to rollback after revert failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class DemoteHalfWriteError(RuntimeError):
    def __init__(self, *, settled_path: Path, candidate_path: Path, phase: str = "double_write") -> None:
        self.settled_path = settled_path
        self.candidate_path = candidate_path
        self.phase = phase
        super().__init__(
            f"demote_half_write_error[{phase}]: failed to rollback after demote failure; "
            f"manual repair required (settled={settled_path}, candidate={candidate_path})"
        )


class ElixirMutationBoundaryError(RuntimeError):
    """Base for receipt-boundary failures where mutation has been rolled back successfully."""


class PromoteReceiptError(ElixirMutationBoundaryError):
    pass


class RevertReceiptError(ElixirMutationBoundaryError):
    pass


class DemoteReceiptError(ElixirMutationBoundaryError):
    pass


class LegacyMigrationPlanError(ElixirMutationBoundaryError):
    """Raised when legacy migration planning fails before any mutation occurs.

    No rollback is needed — planning is read-only.
    """

    pass


class LegacyMigrationApplyError(ElixirMutationBoundaryError):
    """Raised when legacy migration mutation or receipt persistence fails.

    Implies rollback has been attempted (and succeeded); callers must NOT retry
    without re-running preview because the in-memory plan is stale.
    """

    pass


# Back-compat alias: receipt persistence failure was historically named
# LegacyMigrationReceiptError. Kept as an alias to LegacyMigrationApplyError
# so external try/except sites keep working.
LegacyMigrationReceiptError = LegacyMigrationApplyError


class LegacyMigrationHalfWriteError(RuntimeError):
    def __init__(self, *, phase: str = "rollback") -> None:
        self.phase = phase
        super().__init__(
            f"legacy_migration_half_write_error[{phase}]: failed to rollback after legacy migration failure; "
            "manual repair required"
        )


class SupersededCleanupPlanError(ElixirMutationBoundaryError):
    """Raised when superseded-cleanup planning fails before any mutation occurs."""

    pass


class SupersededCleanupApplyError(ElixirMutationBoundaryError):
    """Raised when superseded-cleanup mutation or receipt persistence fails.

    Implies rollback has been attempted.
    """

    pass


SupersededCleanupReceiptError = SupersededCleanupApplyError


class SupersededCleanupHalfWriteError(RuntimeError):
    def __init__(self, *, phase: str = "rollback") -> None:
        self.phase = phase
        super().__init__(
            f"superseded_cleanup_half_write_error[{phase}]: failed to rollback after superseded cleanup failure; "
            "manual repair required"
        )


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


# distill_history is stored as a JSON string in frontmatter because the simple YAML
# helpers in utils.markdown do not round-trip nested list-of-maps structures reliably.


def list_promoted_outputs_for_corpus(root: Path, corpus_id: str) -> list[dict[str, Any]]:
    """List every currently-promoted candidate belonging to ``corpus_id``.

    Authoritative provenance allowlist for elixir distill/seal: walks the full
    ``output_candidates`` state and returns every row whose ``corpus_id`` matches and
    whose ``candidate_state == "promoted"``.

    Deliberately does NOT use ``active_corpora.output_refs`` as an allowlist:
    ``output_refs`` is a recent-context ring buffer (last 8) maintained by
    ``upsert_active_corpus``; using it as a provenance allowlist would silently
    invalidate legitimate older promoted provenance once the corpus ran more than
    8 rounds. See oracle maintainability review EP-029 MUST-FIX #3.
    """
    state = load_output_candidates_state(root)
    results: list[dict[str, Any]] = []
    for candidate in state.get("candidates", []):
        if str(candidate.get("corpus_id") or "") != corpus_id:
            continue
        if str(candidate.get("candidate_state") or "") != "promoted":
            continue
        artifact_ref = str(candidate.get("artifact_ref") or "")
        promoted_to = str(candidate.get("promoted_to") or "")
        if promoted_to:
            results.append(
                {
                    "artifact_ref": artifact_ref,
                    "promoted_to": promoted_to,
                    "question": str(candidate.get("question") or ""),
                }
            )
    return results


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
            _write_atomic_text(candidate_path, plan["content"])
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


def _validate_source_outputs(root: Path, refs: list[str], *, allowed: set[str]) -> None:
    if not refs:
        raise ValueError("source outputs cannot be empty")
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("source output must be a non-empty wiki/derived ref")
        if ref.startswith("wiki/derived/"):
            if not (root / ref).is_file():
                raise ValueError(f"source output missing: {ref}")
            if ref not in allowed:
                raise ValueError(f"source output is not a promoted candidate for this corpus: {ref}")
            continue
        if ref.startswith("wiki/elixirs/"):
            path = root / ref
            if not path.is_file():
                raise ValueError(f"source output missing: {ref}")
            frontmatter = _parse_elixir_frontmatter(path)
            if str(frontmatter.get("elixir_state") or "") != "settled":
                raise ValueError(
                    f"引用金丹 {ref} 当前状态为 {frontmatter.get('elixir_state') or 'unknown'}，只能引用 settled 金丹"
                )
            continue
        raise ValueError(f"source output must be under wiki/derived/ or wiki/elixirs/: {ref}")


def _settled_path(root: Path, elixir_id: str) -> Path:
    return root / ELIXIR_DIR / f"{elixir_id}.md"


def _candidate_path(root: Path, elixir_id: str) -> Path:
    return root / CANDIDATE_ELIXIR_DIR / f"{elixir_id}.md"


def _resolve_elixir_id(root: Path, elixir_id: str) -> str:
    elixir_id = elixir_id.strip()
    if not elixir_id:
        raise ValueError("金丹 id 不能为空")
    if "/" in elixir_id or "\\" in elixir_id:
        raise ValueError(f"金丹 id 不允许包含路径分隔符: {elixir_id!r}")
    if elixir_id in {".", ".."}:
        raise ValueError(f"金丹 id 非法: {elixir_id!r}")
    elixir_root = root / ELIXIR_DIR
    candidate = elixir_root / f"{elixir_id}.md"
    if candidate.resolve().parent != elixir_root.resolve():
        raise ValueError(f"金丹 id 非法: {elixir_id!r}")
    return elixir_id


def _validate_state_for_path(root: Path, state: str, abs_path: Path) -> None:
    if state not in ELIXIR_STATE_VALUES:
        raise ValueError(f"invalid elixir_state: {state}")
    resolved = abs_path.resolve()
    settled_root = (root / ELIXIR_DIR).resolve()
    candidate_root = (root / CANDIDATE_ELIXIR_DIR).resolve()
    in_settled = resolved.parent == settled_root
    in_candidate = resolved.parent == candidate_root
    if not (in_settled or in_candidate):
        raise ValueError(f"elixir path must be under {ELIXIR_DIR} or {CANDIDATE_ELIXIR_DIR}: {abs_path}")
    if state == "settled" and not in_settled:
        raise ValueError(f"elixir_state settled must live under {ELIXIR_DIR}: {abs_path}")
    if state in {"draft", "distilling", "candidate", "superseded"} and not in_candidate:
        raise ValueError(f"elixir_state {state} must live under {CANDIDATE_ELIXIR_DIR}: {abs_path}")


def _read_elixir_anywhere(root: Path, elixir_id: str) -> tuple[Path, dict[str, Any]]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled = _settled_path(root, normalized_id)
    candidate = _candidate_path(root, normalized_id)
    # settled is source-of-truth; prefer it over stale candidate drafts.
    if settled.is_file():
        frontmatter = _parse_elixir_frontmatter(settled)
        _validate_state_for_path(root, str(frontmatter.get("elixir_state") or ""), settled)
        return settled, frontmatter
    if candidate.is_file():
        frontmatter = _parse_elixir_frontmatter(candidate)
        _validate_state_for_path(root, str(frontmatter.get("elixir_state") or ""), candidate)
        return candidate, frontmatter
    raise FileNotFoundError(f"elixir not found: {normalized_id}")


def _read_elixir_both_planes(
    root: Path, elixir_id: str
) -> tuple[tuple[dict[str, Any], str] | None, tuple[dict[str, Any], str] | None]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled = _settled_path(root, normalized_id)
    candidate = _candidate_path(root, normalized_id)

    def _read(path: Path) -> tuple[dict[str, Any], str] | None:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = _parse_elixir_frontmatter(path)
        body = text.split("---", 2)[-1].lstrip("\n")
        return frontmatter, body

    return _read(settled), _read(candidate)


def _collect_dependent_elixir_ids(root: Path, *, source_elixir_id: str) -> list[str]:
    """Return settled elixir ids whose derived_from references source elixir."""
    source_ref = f"wiki/elixirs/{source_elixir_id}.md"
    elixir_root = root / ELIXIR_DIR
    if not elixir_root.exists():
        return []

    dependent_ids: set[str] = set()
    for path in elixir_root.glob("*.md"):
        try:
            frontmatter = _parse_elixir_frontmatter(path)
        except (OSError, ValueError) as exc:
            logger.warning(
                "skip elixir during dependency scan: path=%s source_elixir_id=%s error=%s",
                path,
                source_elixir_id,
                exc,
            )
            continue

        if str(frontmatter.get("elixir_state") or "") != "settled":
            continue

        elixir_id = str(frontmatter.get("elixir_id") or "").strip()
        if not elixir_id or elixir_id == source_elixir_id:
            continue

        derived_from = frontmatter.get("derived_from")
        if not isinstance(derived_from, list):
            continue

        if any(isinstance(item, str) and item == source_ref for item in derived_from):
            dependent_ids.add(elixir_id)

    return sorted(dependent_ids)


def _detect_elixir_cycle(root: Path, new_elixir_path: str | Path, derived_from: list[str]) -> list[str] | None:
    def _norm(p: str | Path, root: Path = root) -> str:
        s = str(p).replace("\\", "/")
        if s.startswith("./"):
            s = s[2:]
        path = Path(s)
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                return str(path).replace("\\", "/")
        return path.as_posix()

    def _elixir_deps(abs_path: Path) -> list[str]:
        try:
            frontmatter = _parse_elixir_frontmatter(abs_path)
        except (OSError, ValueError) as e:
            raise ValueError(f"金丹文件无法解析: {abs_path} ({e})") from e
        deps = frontmatter.get("derived_from", [])
        if not isinstance(deps, list):
            return []
        return [_norm(item) for item in deps if isinstance(item, str) and _norm(item).startswith("wiki/elixirs/")]

    graph: dict[str, list[str]] = {}
    elixir_root = root / "wiki" / "elixirs"
    if elixir_root.exists():
        for f in elixir_root.rglob("*.md"):
            rel = _norm(f.relative_to(root))
            try:
                frontmatter = _parse_elixir_frontmatter(f)
            except (OSError, ValueError) as e:
                raise ValueError(f"金丹文件无法解析: {f} ({e})") from e
            if str(frontmatter.get("elixir_state") or "") != "settled":
                continue
            graph[rel] = _elixir_deps(f)

    start = _norm(new_elixir_path)
    graph[start] = [_norm(d) for d in derived_from if isinstance(d, str) and _norm(d).startswith("wiki/elixirs/")]

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in graph.get(node, []):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                i = stack.index(nxt)
                return stack[i:] + [nxt]
            if c == WHITE:
                cyc = dfs(nxt)
                if cyc:
                    return cyc
        stack.pop()
        color[node] = BLACK
        return None

    return dfs(start)


def _scaffold_elixir_markdown(
    *,
    elixir_id: str,
    protocol: str,
    topic: str,
    corpus_id: str,
    source_outputs: list[str],
    iteration: int,
    elixir_state: str,
    created_at: str,
    updated_at: str,
    distill_history: list[dict[str, Any]] | None = None,
    body: str | None = None,
) -> str:
    frontmatter = {
        "kind": "elixir",
        "elixir_id": elixir_id,
        "elixir_state": elixir_state,
        "protocol": protocol,
        "iteration": iteration,
        "provenance_corpus": corpus_id,
        "derived_from": source_outputs,
        "topic": topic,
        "counter_evidence": ["NONE_FOUND"],
        "confidence_level": "low",
        "created_at": created_at,
        "updated_at": updated_at,
        "distill_history_json": json.dumps(distill_history or [], ensure_ascii=False),
    }
    body = body or "\n".join(
        [
            "# Elixir",
            "",
            "## Thesis",
            "- Pending refinement.",
            "",
            "## Evidence",
            "- Pending refinement.",
            "",
            "## Open Questions",
            "- Pending refinement.",
            "",
        ]
    )
    return _render_inserted_frontmatter(frontmatter) + body.rstrip() + "\n"


def _elixir_body_has_pending_refinement(body: str) -> bool:
    return bool(_PENDING_REFINEMENT_RE.search(body))


def _first_section_lines(
    markdown: str, headings: tuple[str, ...], *, fallback: list[str], max_lines: int = 6
) -> list[str]:
    for heading in headings:
        match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown)
        if not match:
            continue
        lines: list[str] = []
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("```") or line.startswith("#"):
                continue
            if "_LLM:" in line or "机器记忆提示" in line or "查询入口：" in line:
                continue
            if not line.startswith(("-", "1.", "2.", "3.", "4.", "5.")):
                line = f"- {line}"
            lines.append(line)
            if len(lines) >= max_lines:
                break
        if lines:
            return lines
    return list(fallback)


def _seed_elixir_body_from_sources(root: Path, *, topic: str, source_outputs: list[str]) -> str:
    source_texts: list[str] = []
    existing_refs: list[str] = []
    for ref in source_outputs:
        path = root / ref
        if not path.is_file():
            continue
        existing_refs.append(ref)
        try:
            source_texts.append(strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    merged = "\n\n".join(source_texts)
    refs = existing_refs or source_outputs
    thesis = _first_section_lines(
        merged,
        ("结论", "Conclusion", "Investment Judgment", "Judgment", "Filed Content"),
        fallback=[f"- {topic} is seeded from {', '.join(refs[:3])}."],
        max_lines=3,
    )
    evidence = _first_section_lines(
        merged,
        ("关键证据", "Evidence", "Drivers And Catalysts", "Supporting Evidence"),
        fallback=[f"- Provenance source: `{ref}`." for ref in refs[:6]],
        max_lines=6,
    )
    questions = _first_section_lines(
        merged,
        ("反证与不确定性", "Open Questions", "Next Signals", "下次观察信号", "Risks And Invalidation"),
        fallback=["- Review counter evidence and refresh this elixir before relying on it for a stronger claim."],
        max_lines=5,
    )
    return "\n".join(
        [
            "# Elixir",
            "",
            "## Thesis",
            *thesis,
            "",
            "## Evidence",
            *evidence,
            "",
            "## Open Questions",
            *questions,
            "",
        ]
    )


def _render_inserted_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=True)}")
        else:
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=True)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _parse_elixir_frontmatter(path: Path) -> dict[str, Any]:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    raw_history = frontmatter.get("distill_history_json")
    if isinstance(raw_history, str):
        try:
            frontmatter["distill_history"] = json.loads(raw_history)
        except json.JSONDecodeError as e:
            raise ValueError(f"elixir {path} has corrupt distill_history_json") from e
    elif "distill_history_json" in frontmatter:
        frontmatter["distill_history"] = []
    return frontmatter


def _write_elixir_markdown(path: Path, *, frontmatter: dict[str, Any], body: str) -> None:
    # Preserve distill_history as JSON string so the lightweight YAML parser remains usable.
    serializable = dict(frontmatter)
    serializable["distill_history_json"] = json.dumps(serializable.pop("distill_history", []), ensure_ascii=False)
    content = _render_inserted_frontmatter(serializable) + body
    _write_atomic_text(path, content)


def _write_atomic_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _render_elixir_document(frontmatter: dict[str, Any], body: str) -> str:
    serializable = dict(frontmatter)
    serializable["distill_history_json"] = json.dumps(serializable.pop("distill_history", []), ensure_ascii=False)
    return _render_inserted_frontmatter(serializable) + body


def _find_corpus(root: Path, corpus_id: str) -> dict[str, Any]:
    state = load_active_corpora_state(root)
    for corpus in state.get("corpora", []):
        if str(corpus.get("corpus_id") or "") == corpus_id:
            return corpus
    raise FileNotFoundError(f"corpus not found: {corpus_id}")


def start_elixir(
    root: Path,
    corpus_id: str,
    *,
    topic: str,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    corpus = _find_corpus(root, corpus_id)  # validate corpus exists
    protocol_name = str(protocol or corpus.get("protocol") or "").strip()
    if not protocol_name:
        raise ValueError("protocol 不能为空")
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    if not promoted:
        raise ValueError(f"no promoted outputs for corpus {corpus_id}")
    source_outputs = [item["promoted_to"] for item in promoted if item.get("promoted_to")]
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for elixir_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, elixir_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{elixir_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {elixir_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    source_outputs = list(dict.fromkeys([*source_outputs, *include_paths]))
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    candidate_dir = root / CANDIDATE_ELIXIR_DIR
    candidate_dir.mkdir(parents=True, exist_ok=True)
    seed = f"elixir-{slugify(topic)[:40]}-{sha256_bytes(topic.encode())[:8]}"
    elixir_id = next_available_stem(candidate_dir, seed)
    settled_path = _settled_path(root, elixir_id)
    candidate_path = _candidate_path(root, elixir_id)
    _norm = str(settled_path.relative_to(root))
    if _norm in {str(Path(ref)) for ref in source_outputs}:
        raise ValueError(f"cannot reference self: {_norm}")
    cycle = _detect_elixir_cycle(root, settled_path, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    if settled_path.exists() or candidate_path.exists():
        raise FileExistsError(f"elixir already exists: {elixir_id}")
    now = utc_now()
    candidate_path.write_text(
        _scaffold_elixir_markdown(
            elixir_id=elixir_id,
            protocol=protocol_name,
            topic=topic,
            corpus_id=corpus_id,
            source_outputs=source_outputs,
            iteration=0,
            elixir_state="draft",
            created_at=now,
            updated_at=now,
            body=_seed_elixir_body_from_sources(root, topic=topic, source_outputs=source_outputs),
        ),
        encoding="utf-8",
    )
    _validate_state_for_path(root, "draft", candidate_path)
    return {
        "elixir_id": elixir_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{elixir_id}.md",
        "derived_from": source_outputs,
        "iteration": 0,
        "elixir_state": "draft",
        "protocol": protocol_name,
    }


def distill_elixir(
    root: Path, elixir_id: str, *, question: str, include_elixir_ids: list[str] | None = None
) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    source_path, frontmatter = _read_elixir_anywhere(root, normalized_id)
    if source_path.resolve().parent == (root / ELIXIR_DIR).resolve():
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    source_state = str(frontmatter.get("elixir_state") or "")
    if source_state == "settled":
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    if source_state not in _ACTIVE_ELIXIR_STATES:
        raise ValueError(f"unsupported_source_state: cannot distill elixir from state={source_state or 'unknown'}")
    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    existing = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    # Defense-in-depth: refuse to distill an elixir whose existing provenance was
    # tampered empty or points outside the current corpus allowlist. Prevents
    # silent provenance loss via frontmatter edits.
    if not existing:
        raise ValueError(f"elixir has empty derived_from, refusing to distill: {elixir_id}")
    _validate_source_outputs(root, existing, allowed=allowed)
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for include_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, include_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{include_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {include_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    merged = list(dict.fromkeys([*existing, *allowed, *include_paths]))
    _validate_source_outputs(root, merged, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in merged):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in merged if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, merged)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    target_path = _candidate_path(root, normalized_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    iteration = int(frontmatter.get("iteration", 0) or 0) + 1
    history = frontmatter.get("distill_history") if isinstance(frontmatter.get("distill_history"), list) else []
    history = list(history)
    history.append({"iteration": iteration, "question": question, "at": utc_now()})
    frontmatter.update(
        {
            "iteration": iteration,
            "derived_from": merged,
            "elixir_state": "distilling",
            "updated_at": utc_now(),
            "distill_history": history,
        }
    )
    original = source_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1]
    body = body.lstrip("\n")
    if _elixir_body_has_pending_refinement(body):
        body = _seed_elixir_body_from_sources(root, topic=question, source_outputs=merged)
    _write_elixir_markdown(target_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "distilling", target_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "iteration": iteration,
        "derived_from": merged,
        "elixir_state": "distilling",
    }


def finalize_elixir(root: Path, *, elixir_id: str) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("unsupported_source_state: cannot finalize settled elixir")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)

    if source_state == "candidate":
        raise ValueError("already_candidate: elixir already finalized")
    if source_state not in {"draft", "distilling"}:
        raise ValueError(f"unsupported_source_state: cannot finalize elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    # P4-INV-4 (Round 59): derive a protocol-aware default `review_after` when
    # the author did not set one explicitly, so the candidate carries a real
    # expiration anchor (Furnace Evolution Mechanics §7.2 target schema). Never
    # overwrite a value already in frontmatter.
    review_after_existing = str(frontmatter.get("review_after") or "").strip()
    review_after_value = review_after_existing or _default_elixir_review_after(
        protocol=str(frontmatter.get("protocol") or "general"),
    )

    frontmatter.update(
        {
            "elixir_state": "candidate",
            "updated_at": utc_now(),
            "review_after": review_after_value,
        }
    )
    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "candidate", candidate_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "candidate",
        "review_after": review_after_value,
    }


def _default_elixir_review_after(*, protocol: str) -> str:
    """Compute a default ISO date for a freshly finalized elixir's review_after.

    Returns YYYY-MM-DD (UTC). Falls back to the general window when the
    protocol is unknown.
    """
    days = PROTOCOL_ELIXIR_REVIEW_DAYS.get(protocol.strip(), PROTOCOL_ELIXIR_REVIEW_DAYS["general"])
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def promote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("already_promoted: settled elixir already exists")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)
    if source_state != "candidate":
        raise ValueError(f"unsupported_source_state: cannot promote elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith("wiki/derived/") for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    validate_promote_gate(frontmatter)

    counter_evidence_items = [str(item).strip() for item in frontmatter.get("counter_evidence", [])]
    counter_evidence_provenance = "none_found" if counter_evidence_items == ["NONE_FOUND"] else "real"

    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    if _elixir_body_has_pending_refinement(body):
        raise ValueError("elixir_body_placeholder: cannot promote elixir with pending refinement body")
    applied_at_dt = datetime.now(timezone.utc)
    applied_at = applied_at_dt.isoformat()

    settled_frontmatter = dict(frontmatter)
    settled_frontmatter.pop("sealed_at", None)
    settled_frontmatter.update(
        {
            "elixir_state": "settled",
            "promoted_at": applied_at,
            "counter_evidence_provenance": counter_evidence_provenance,
        }
    )
    tombstone_frontmatter = dict(frontmatter)
    tombstone_frontmatter.pop("sealed_at", None)
    tombstone_frontmatter.update(
        {
            "elixir_state": "superseded",
            "superseded_by": f"{ELIXIR_DIR}/{normalized_id}.md",
            "promoted_at": applied_at,
        }
    )

    settled_text = _render_elixir_document(settled_frontmatter, body)
    tombstone_text = _render_elixir_document(tombstone_frontmatter, body)
    protocol = str(frontmatter.get("protocol") or "")

    settled_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot pre-mutation state for rollback on receipt-persist failure.
    settled_snapshot = _snapshot_file_bytes(settled_path)  # expected None: gate above ensured non-existence
    candidate_snapshot = _snapshot_file_bytes(candidate_path)  # expected non-None: gate above ensured candidate exists

    _write_atomic_text(settled_path, settled_text)
    try:
        _write_atomic_text(candidate_path, tombstone_text)
    except Exception as exc:
        try:
            _restore_file_bytes(settled_path, settled_snapshot)
        except Exception as rollback_exc:
            raise PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    _validate_state_for_path(root, "settled", settled_path)
    _validate_state_for_path(root, "superseded", candidate_path)

    def _rollback_promote_data() -> None:
        _restore_file_bytes(candidate_path, candidate_snapshot)
        _restore_file_bytes(settled_path, settled_snapshot)

    try:
        primary_hash = compute_file_sha256(settled_path)
        secondary_hash = compute_file_sha256(candidate_path)
        receipt = build_elixir_promotion_receipt(
            root,
            elixir_id=normalized_id,
            slug=slugify(normalized_id),
            settled_path=settled_path,
            candidate_path=candidate_path,
            protocol=protocol,
            applied_at=applied_at_dt,
            note=note,
            primary_path_sha256=primary_hash,
            secondary_path_sha256=secondary_hash,
            counter_evidence=counter_evidence_items,
            confidence_level=str(frontmatter.get("confidence_level") or "").strip(),
            counter_evidence_provenance=counter_evidence_provenance,
        )
        receipt_result_path = str(receipt.get("receipt_path") or "")
        _persist_receipt_transactionally(
            root,
            receipt=receipt,
            elixir_id=normalized_id,
            operation="promote",
            rollback_data=_rollback_promote_data,
            receipt_error_cls=PromoteReceiptError,
            half_write_error_factory=lambda phase: PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase=phase
            ),
        )
    except (PromoteReceiptError, PromoteHalfWriteError):
        raise
    except Exception as receipt_exc:
        logger.warning(
            "elixir promote receipt preparation failed for %s; rolling back mutation: %s",
            normalized_id,
            receipt_exc,
        )
        try:
            _rollback_promote_data()
        except Exception as rollback_exc:
            raise PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="receipt_rollback"
            ) from rollback_exc
        raise PromoteReceiptError(
            f"promote_receipt_error: receipt persistence failed for elixir {normalized_id}; mutation rolled back"
        ) from receipt_exc

    return {
        "elixir_id": normalized_id,
        "path": f"{ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "settled",
        "promoted_at": applied_at,
        "receipt_path": receipt_result_path,
    }


def revert_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, _settled_body = settled_data

    latest_promotion = find_latest_elixir_promotion_receipt(root, elixir_id=normalized_id)
    if latest_promotion is None:
        raise ValueError("promotion_receipt_missing: latest promotion receipt not found")

    source_applied_at = str(latest_promotion.get("applied_at") or "")
    source_action_id = str(latest_promotion.get("action_id") or "")
    bundle = latest_promotion.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")
    expected_settled_hash = bundle.get("primary_path_sha256")
    expected_tombstone_hash = bundle.get("secondary_path_sha256")
    if (
        not isinstance(expected_settled_hash, str)
        or not expected_settled_hash.strip()
        or not isinstance(expected_tombstone_hash, str)
        or not expected_tombstone_hash.strip()
    ):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")

    actual_settled_hash = compute_file_sha256(settled_path)
    if actual_settled_hash != expected_settled_hash:
        raise ValueError("revert_conflict_settled_modified: settled elixir was modified after promotion")

    if candidate_data is None:
        raise ValueError("revert_tombstone_missing: superseded tombstone is required")
    tombstone_frontmatter, tombstone_body = candidate_data
    tombstone_state = str(tombstone_frontmatter.get("elixir_state") or "")
    if tombstone_state != "superseded":
        raise ValueError(f"unsupported_source_state: cannot revert elixir from state={tombstone_state or 'unknown'}")

    actual_tombstone_hash = compute_file_sha256(candidate_path)
    if actual_tombstone_hash != expected_tombstone_hash:
        raise ValueError("revert_conflict_candidate_modified: candidate tombstone no longer matches promotion receipt")

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_reverted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for revert: %s",
            normalized_id,
        )
        dependency_breaks = []

    tombstone_original_bytes = candidate_path.read_bytes()
    settled_original_bytes = settled_path.read_bytes()
    candidate_frontmatter = dict(tombstone_frontmatter)
    candidate_frontmatter["elixir_state"] = "candidate"
    candidate_frontmatter.pop("superseded_by", None)
    candidate_frontmatter.pop(_PROMOTION_TS_FIELD, None)
    candidate_text = _render_elixir_document(candidate_frontmatter, tombstone_body)

    _write_atomic_text(candidate_path, candidate_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            _restore_file_bytes(candidate_path, tombstone_original_bytes)
        except Exception as rollback_exc:
            raise RevertHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or tombstone_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_revert_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        source_receipt_applied_at=source_applied_at,
        source_receipt_action_id=source_action_id,
        dependency_breaks=dependency_breaks,
    )
    _persist_receipt_transactionally(
        root,
        receipt=receipt,
        elixir_id=normalized_id,
        operation="revert",
        rollback_data=lambda: (
            _restore_file_bytes(candidate_path, tombstone_original_bytes),
            _restore_file_bytes(settled_path, settled_original_bytes),
        ),
        receipt_error_cls=RevertReceiptError,
        half_write_error_factory=lambda phase: RevertHalfWriteError(
            settled_path=settled_path, candidate_path=candidate_path, phase=phase
        ),
    )

    return candidate_path


def demote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, settled_body = settled_data
    settled_state = str(settled_frontmatter.get("elixir_state") or "")
    if settled_state != "settled":
        raise ValueError(f"unsupported_source_state: cannot demote elixir from state={settled_state or 'unknown'}")

    had_candidate_before = candidate_data is not None
    candidate_snapshot = _snapshot_file_bytes(candidate_path) if had_candidate_before else None
    settled_snapshot = _snapshot_file_bytes(settled_path)
    if candidate_data is not None:
        candidate_frontmatter, _candidate_body = candidate_data
        candidate_state = str(candidate_frontmatter.get("elixir_state") or "")
        if candidate_state != "superseded":
            raise ValueError("demote_conflict_candidate_exists: candidate plane has conflicting non-superseded state")

    demoted_frontmatter = dict(settled_frontmatter)
    demoted_frontmatter["elixir_state"] = "candidate"
    demoted_frontmatter.pop("promoted_at", None)
    demoted_frontmatter.pop("sealed_at", None)
    demoted_frontmatter.pop("superseded_by", None)
    demoted_text = _render_elixir_document(demoted_frontmatter, settled_body)

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_demoted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for demote: %s",
            normalized_id,
        )
        dependency_breaks = []

    _write_atomic_text(candidate_path, demoted_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            _restore_file_bytes(candidate_path, candidate_snapshot)
        except Exception as rollback_exc:
            raise DemoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_demotion_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        dependency_breaks=dependency_breaks,
    )
    _persist_receipt_transactionally(
        root,
        receipt=receipt,
        elixir_id=normalized_id,
        operation="demote",
        rollback_data=lambda: (
            _restore_file_bytes(candidate_path, candidate_snapshot),
            _restore_file_bytes(settled_path, settled_snapshot),
        ),
        receipt_error_cls=DemoteReceiptError,
        half_write_error_factory=lambda phase: DemoteHalfWriteError(
            settled_path=settled_path, candidate_path=candidate_path, phase=phase
        ),
    )

    return candidate_path
