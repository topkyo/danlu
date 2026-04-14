"""Execution bundle and receipt assembly for apply/archive workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .app_content import execution_receipt_path
from .app_state import (
    DEFAULT_PROTOCOL,
    execution_receipt_history_path,
    load_json_document,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
)
from .app_types import ExecutionBundle, ExecutionReceipt
from .app_utils import relative_path, sha256_bytes


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


def load_execution_bundle(path: Path) -> ExecutionBundle:
    document = load_json_document(path)
    if not isinstance(document, dict) or str(document.get("kind") or "") != "execution-bundle":
        raise RuntimeError(f"Invalid execution bundle: {path}")
    return document


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
        "bundle_path": "",
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
        "dry_run_supported": False,
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


def append_execution_receipt_history(root: Path, receipt: dict[str, Any]) -> None:
    path = execution_receipt_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
