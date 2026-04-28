"""Execution bundle and receipt assembly for apply/archive workflows."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_content import execution_bundle_path
from .app_state import (
    DEFAULT_PROTOCOL,
    execution_batch_receipt_path,
    execution_receipt_history_path,
    load_json_document,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
)
from .app_types import ExecutionBundle, ExecutionReceipt
from .app_utils import relative_path, sha256_bytes, slugify
from .render.paths import execution_receipt_path


def build_execution_bundle(
    root: Path,
    proposal: dict[str, Any],
    *,
    compiled_at: str,
) -> ExecutionBundle:
    patch_steps: list[dict[str, Any]] = []
    for index, patch in enumerate(proposal.get("page_patch_plan", []), start=1):
        patch_steps.append(
            {
                "step": index,
                "path": str(patch.get("path") or ""),
                "role": str(patch.get("role") or ""),
                "role_label": str(patch.get("role_label") or patch.get("role") or "page"),
                "mode": str(patch.get("mode") or "update"),
                "sections": list(patch.get("sections") or []),
                "summary": str(patch.get("summary") or ""),
                "exists": bool(patch.get("exists", False)),
                "command_hint": str(patch.get("command_hint") or ""),
            }
        )
    bundle: ExecutionBundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-compile",
        "compiled_at": compiled_at,
        "action_id": str(proposal.get("action_id") or ""),
        "title": str(proposal.get("title") or ""),
        "status": str(proposal.get("status") or "proposed"),
        "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
        "risk": str(proposal.get("risk") or "medium"),
        "priority": str(proposal.get("priority") or "medium"),
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "policy_decision": str(proposal.get("policy_decision") or ""),
        "policy_rule_id": str(proposal.get("policy_rule_id") or ""),
        "execution_band": str(proposal.get("execution_band") or ""),
        "impact_score": int(proposal.get("impact_score", 0) or 0),
        "priority_score": int(proposal.get("priority_score", 0) or 0),
        "summary": str(proposal.get("summary") or ""),
        "target_paths": list(proposal.get("target_paths") or []),
        "suggested_edits": list(proposal.get("suggested_edits") or []),
        "proposal_path": str(proposal.get("proposal_path") or ""),
        "bundle_path": str(proposal.get("bundle_path") or ""),
        "page_patch_plan": patch_steps,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
        "depends_on": [str(item) for item in proposal.get("depends_on", []) if isinstance(item, str) and item],
        "rollback_summary": str(proposal.get("rollback_summary") or ""),
        "command_hint": str(proposal.get("command_hint") or ""),
        "next_step": str(proposal.get("next_step") or ""),
        "dry_run_supported": bool(proposal.get("safe_apply_preview")),
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def execution_bundle_digest(bundle: dict[str, Any]) -> str:
    payload = {
        "action_id": str(bundle.get("action_id") or ""),
        "title": str(bundle.get("title") or ""),
        "status": str(bundle.get("status") or ""),
        "proposal_kind": str(bundle.get("proposal_kind") or ""),
        "risk": str(bundle.get("risk") or ""),
        "priority": str(bundle.get("priority") or ""),
        "protocol": str(bundle.get("protocol") or DEFAULT_PROTOCOL),
        "policy_decision": str(bundle.get("policy_decision") or ""),
        "policy_rule_id": str(bundle.get("policy_rule_id") or ""),
        "execution_band": str(bundle.get("execution_band") or ""),
        "impact_score": int(bundle.get("impact_score", 0) or 0),
        "priority_score": int(bundle.get("priority_score", 0) or 0),
        "summary": str(bundle.get("summary") or ""),
        "target_paths": list(bundle.get("target_paths") or []),
        "suggested_edits": list(bundle.get("suggested_edits") or []),
        "page_patch_plan": list(bundle.get("page_patch_plan") or []),
        "safe_apply_preview": bundle.get("safe_apply_preview"),
        "depends_on": list(bundle.get("depends_on") or []),
        "rollback_summary": str(bundle.get("rollback_summary") or ""),
        "command_hint": str(bundle.get("command_hint") or ""),
        "next_step": str(bundle.get("next_step") or ""),
        "dry_run_supported": bool(bundle.get("dry_run_supported")),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


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


def load_execution_bundle(path: Path) -> ExecutionBundle:
    document = load_json_document(path)
    if not isinstance(document, dict) or str(document.get("kind") or "") != "execution-bundle":
        raise RuntimeError(f"Invalid execution bundle: {path}")
    return document


def write_execution_bundle_document(path: Path, bundle: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_execution_dry_run_document(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_execution_batch_receipt(
    root: Path,
    *,
    batch_id: str,
    operation: str,
    generated_at: str,
    items: list[dict[str, Any]],
    note: str | None,
    revert_supported: bool,
    reverted_batch_id: str = "",
) -> dict[str, Any]:
    action_ids = [
        str(item.get("id") or item.get("action_id") or "")
        for item in items
        if isinstance(item, dict) and (item.get("id") or item.get("action_id"))
    ]
    page_paths = [
        str(item.get("path") or "")
        for item in items
        if isinstance(item, dict) and item.get("path")
    ]
    receipt_path = execution_batch_receipt_path(root, batch_id)
    return {
        "version": 1,
        "kind": "execution-batch-receipt",
        "generated_by": "aiwiki-batch-ops",
        "generated_at": generated_at,
        "batch_id": batch_id,
        "operation": operation,
        "note": note or "",
        "count": len(items),
        "action_ids": action_ids,
        "page_paths": page_paths,
        "revert_supported": revert_supported,
        "reverted_batch_id": reverted_batch_id,
        "items": items,
        "receipt_path": relative_path(root, receipt_path),
    }


def write_execution_batch_receipt_document(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_execution_receipt(
    root: Path,
    action: dict[str, Any],
    *,
    applied_at: str,
    note: str | None,
    proposal: dict[str, Any],
    operation: str = "apply",
    resulting_status: str = "resolved",
) -> ExecutionReceipt:
    bundle = build_execution_bundle(root, proposal, compiled_at=applied_at)
    preview = proposal.get("safe_apply_preview")
    preview_apply_mode = str(preview.get("apply_mode") or "") if isinstance(preview, dict) else ""
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-apply-action",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or ""),
        "status": resulting_status,
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "apply_mode": (
            preview_apply_mode
            if operation == "apply"
            else (f"{preview_apply_mode}-revert" if preview_apply_mode else "manual-repair-revert")
        ),
        "note": note or "",
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "receipt_path": relative_path(root, execution_receipt_path(root, str(action.get("id") or ""))),
        "bundle": bundle,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
    }


def build_material_archive_bundle(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> ExecutionBundle:
    command_hint = (
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . revert-archive {entry_id}"
        if operation == "apply"
        else f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-archive {entry_id}"
    )
    action_id = material_archive_action_id(entry_id)
    bundle: ExecutionBundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-material-archive",
        "compiled_at": applied_at,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "proposal_kind": "material-archive",
        "risk": "low",
        "priority": "low",
        "protocol": protocol,
        "summary": f"{operation} material archive override for `{entry_id}`.",
        "target_paths": [
            path
            for path in (
                source_path,
                relative_path(root, material_archive_state_path(root)),
                relative_path(root, material_state_path(root)),
            )
            if path
        ],
        "suggested_edits": [f"temperature `{current_temperature}` -> `{resulting_temperature}`"],
        "proposal_path": "",
        "bundle_path": relative_path(root, execution_bundle_path(root, action_id)),
        "page_patch_plan": [],
        "safe_apply_preview": {
            "apply_mode": (
                "material-temperature-archive"
                if operation == "apply"
                else "material-temperature-archive-revert"
            ),
            "state_path": relative_path(root, material_archive_state_path(root)),
            "entry": {
                "entry_id": entry_id,
                "active": operation == "apply",
                "temperature": resulting_temperature,
            },
            "affected_paths": [
                path
                for path in (
                    source_path,
                    relative_path(root, material_archive_state_path(root)),
                    relative_path(root, material_state_path(root)),
                )
                if path
            ],
            "follow_up": "执行后会重跑 compile，让 material-state / archive-candidates / ask 排序同步收敛。",
        },
        "command_hint": command_hint,
        "next_step": "如需恢复材料，再执行对应的 revert-archive。",
        "dry_run_supported": True,
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def build_material_archive_receipt(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    note: str | None,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> ExecutionReceipt:
    action_id = material_archive_action_id(entry_id)
    receipt_path = execution_receipt_path(root, action_id)
    bundle = build_material_archive_bundle(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        operation=operation,
        current_temperature=current_temperature,
        resulting_temperature=resulting_temperature,
    )
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-material-archive",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "protocol": protocol,
        "subject_kind": "material-archive",
        "subject_id": entry_id,
        "apply_mode": "material-temperature-archive" if operation == "apply" else "material-temperature-archive-revert",
        "note": note or "",
        "primary_path": source_path,
        "secondary_path": "",
        "current_temperature": current_temperature,
        "resulting_temperature": resulting_temperature,
        "receipt_path": relative_path(root, receipt_path),
        "bundle": bundle,
        "safe_apply_preview": bundle.get("safe_apply_preview"),
    }


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
    from .app_state import load_jsonl_documents_strict

    path = execution_receipt_history_path(root)
    latest: dict[str, Any] | None = None
    for entry in load_jsonl_documents_strict(path):
        if entry.get("subject_kind") == "elixir_promotion" and entry.get("subject_id") == elixir_id:
            latest = entry
    return latest


def append_execution_receipt_history(root: Path, receipt: dict[str, Any]) -> None:
    path = execution_receipt_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line_number = _next_jsonl_line_number(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
    from .execution.audit_preview import append_universal_audit_record

    append_universal_audit_record(
        root,
        source_stream="execution_receipts",
        source_ref=f"{relative_path(root, path)}#L{line_number}",
        document=receipt,
    )


def _next_jsonl_line_number(path: Path) -> int:
    if not path.exists():
        return 1
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count + 1
