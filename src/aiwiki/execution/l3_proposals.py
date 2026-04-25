"""L3 prompt/policy proposal manual execution surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_execution import append_execution_receipt_history
from ..app_protocol import ensure_layout
from ..app_render import append_wiki_log
from ..app_state import append_runtime_history, l3_proposal_state_path, load_json_document, save_json_document
from ..app_utils import (
    next_available_stem,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    sha256_file,
    slugify,
    utc_now,
)
from ..render.paths import execution_receipt_path

L3_PROPOSAL_KINDS = ("prompt_proposal", "policy_proposal")
L3_PROPOSAL_STATES = ("candidate", "accepted", "rejected", "reverted", "stale", "revert_conflict")
L3_TRIGGER_PATTERNS = ("failure_cluster", "recurring_feedback", "drift", "contract_failure", "manual_fixture")


def default_l3_proposal_state() -> dict[str, Any]:
    return {"version": 1, "proposals": []}


def load_l3_proposal_state(root: Path) -> dict[str, Any]:
    document = load_json_document(l3_proposal_state_path(root))
    if not isinstance(document, dict):
        return default_l3_proposal_state()
    proposals = document.get("proposals")
    if not isinstance(proposals, list):
        return default_l3_proposal_state()
    return {
        "version": int(document.get("version", 1) or 1),
        "proposals": [item for item in proposals if isinstance(item, dict)],
    }


def save_l3_proposal_state(root: Path, proposals: list[dict[str, Any]]) -> None:
    save_json_document(l3_proposal_state_path(root), {"version": 1, "proposals": proposals})


def l3_proposal_dir(root: Path, kind: str) -> Path:
    if kind == "prompt_proposal":
        return root / "output" / "_proposals" / "prompt"
    if kind == "policy_proposal":
        return root / "output" / "_proposals" / "policy"
    raise ValueError(f"Unsupported L3 proposal kind: {kind}")


def l3_revert_hint_path(root: Path, proposal: dict[str, Any]) -> Path:
    kind = str(proposal.get("kind") or "")
    proposal_id = str(proposal.get("proposal_id") or "proposal")
    return l3_proposal_dir(root, kind) / f"{slugify(proposal_id)}-revert-hint.md"


def _proposal_path(root: Path, kind: str, proposal_id: str) -> Path:
    return l3_proposal_dir(root, kind) / f"{slugify(proposal_id)}.md"


def _hash_path(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def _target_path(root: Path, kind: str, target_file: str) -> Path:
    normalized = target_file.strip().strip("'\"`")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    target = Path(normalized)
    if target.is_absolute() or ".." in target.parts or not normalized:
        raise ValueError("L3 proposal target_file must be a relative workspace path without traversal.")
    parts = target.parts
    if kind == "prompt_proposal":
        if len(parts) != 2 or parts[0] != "prompts" or target.suffix != ".md":
            raise ValueError("Prompt proposals may only target prompts/*.md.")
    elif kind == "policy_proposal":
        if len(parts) < 3 or parts[0] != "schema" or parts[1] != "policies":
            raise ValueError("Policy proposals may only target schema/policies/*.")
    else:
        raise ValueError(f"Unsupported L3 proposal kind: {kind}")
    return root / target.as_posix()


def _find_l3_proposal(proposals: list[dict[str, Any]], proposal_id: str) -> dict[str, Any]:
    for proposal in proposals:
        if str(proposal.get("proposal_id") or "") == proposal_id:
            return proposal
    raise FileNotFoundError(f"L3 proposal not found: {proposal_id}")


def _render_l3_proposal_page(proposal: dict[str, Any]) -> str:
    trigger = proposal.get("trigger") if isinstance(proposal.get("trigger"), dict) else {}
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    frontmatter = {
        "kind": str(proposal.get("kind") or ""),
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "target_file": str(proposal.get("target_file") or ""),
        "state": str(proposal.get("state") or "candidate"),
        "trigger_pattern": str(trigger.get("pattern") or ""),
        "evidence_count": int(trigger.get("evidence_count", 0) or 0),
        "before_hash": str(patch.get("before_hash") or ""),
        "patch_kind": str(patch.get("kind") or "full_replace"),
        "created_at": str(proposal.get("created_at") or ""),
    }
    if proposal.get("review_queue_entry_id"):
        frontmatter["review_queue_entry_id"] = str(proposal.get("review_queue_entry_id") or "")
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# L3 Proposal: {proposal.get('proposal_id')}",
        "",
        "## Rationale",
        str(proposal.get("rationale") or "").strip() or "(none)",
        "",
        "## Evidence",
    ]
    evidence_refs = [str(item) for item in proposal.get("evidence_refs", []) if isinstance(item, str)]
    lines.extend(f"- `{item}`" for item in evidence_refs)
    if not evidence_refs:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Revert Plan",
            f"- kind: `{proposal.get('revert_plan', {}).get('kind', 'restore_before_hash') if isinstance(proposal.get('revert_plan'), dict) else 'restore_before_hash'}`",
            "- fallback: `human_merge_required`",
            "",
            "## Proposed Content",
            "```",
            str(patch.get("content") or "").rstrip(),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _persist_l3_proposal_page(root: Path, proposal: dict[str, Any]) -> None:
    path = root / str(proposal.get("proposal_path") or "")
    if not path.is_absolute():
        path = root / str(proposal.get("proposal_path") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_l3_proposal_page(proposal), encoding="utf-8")


def _unique_l3_action_id(root: Path, prefix: str, proposal_id: str) -> str:
    seed = f"{prefix}-{slugify(proposal_id)}"
    stem = next_available_stem(execution_receipt_path(root, seed).parent, seed, ".json")
    return stem


def list_l3_proposals(
    root: Path,
    *,
    kind: str | None = None,
    state: str | None = None,
) -> list[dict[str, Any]]:
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    if kind:
        proposals = [item for item in proposals if str(item.get("kind") or "") == kind]
    if state:
        proposals = [item for item in proposals if str(item.get("state") or "") == state]
    proposals.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("proposal_id") or "")), reverse=True)
    return proposals


@runtime_write_operation
def create_l3_proposal(
    root: Path,
    *,
    kind: str,
    target_file: str,
    content: str,
    proposal_id: str | None = None,
    rationale: str = "",
    evidence_refs: list[str] | None = None,
    signal_ids: list[str] | None = None,
    pattern: str = "manual_fixture",
) -> dict[str, Any]:
    ensure_layout(root)
    if kind not in L3_PROPOSAL_KINDS:
        raise ValueError(f"Unsupported L3 proposal kind: {kind}")
    if pattern not in L3_TRIGGER_PATTERNS:
        raise ValueError(f"Unsupported L3 trigger pattern: {pattern}")
    target = _target_path(root, kind, target_file)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"L3 proposal target not found: {target_file}")
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    existing_ids = {str(item.get("proposal_id") or "") for item in proposals}
    normalized_id = slugify(proposal_id or f"prop-{Path(target_file).stem}")
    if normalized_id in existing_ids:
        raise ValueError(f"L3 proposal already exists: {normalized_id}")
    created_at = utc_now()
    before_hash = _hash_path(target)
    proposal_path = _proposal_path(root, kind, normalized_id)
    evidence = [str(item) for item in (evidence_refs or []) if str(item).strip()]
    signals = [str(item) for item in (signal_ids or []) if str(item).strip()]
    proposal = {
        "kind": kind,
        "proposal_id": normalized_id,
        "target_file": relative_path(root, target),
        "trigger": {
            "signal_ids": signals,
            "pattern": pattern,
            "evidence_count": len(evidence),
        },
        "evidence_refs": evidence,
        "patch": {
            "kind": "full_replace",
            "before_hash": before_hash,
            "content": content.rstrip() + "\n",
        },
        "rationale": rationale,
        "revert_plan": {"kind": "restore_before_hash", "fallback": "human_merge_required"},
        "review_queue_entry_id": f"review-{normalized_id}",
        "state": "candidate",
        "created_at": created_at,
        "proposal_path": relative_path(root, proposal_path),
        "last_receipt_path": "",
        "revert_hint_path": "",
    }
    proposals.append(proposal)
    save_l3_proposal_state(root, proposals)
    _persist_l3_proposal_page(root, proposal)
    append_runtime_history(
        root,
        {
            "event_type": "l3-proposal-create",
            "occurred_at": created_at,
            "proposal_id": normalized_id,
            "kind": kind,
            "target_file": relative_path(root, target),
            "proposal_path": relative_path(root, proposal_path),
            "state": "candidate",
        },
    )
    append_wiki_log(
        root,
        "l3-proposal-create",
        normalized_id,
        [
            f"kind: `{kind}`",
            f"target: `{relative_path(root, target)}`",
            f"proposal: `{relative_path(root, proposal_path)}`",
        ],
    )
    return {
        "proposal_id": normalized_id,
        "kind": kind,
        "state": "candidate",
        "target_file": relative_path(root, target),
        "proposal_path": relative_path(root, proposal_path),
        "before_hash": before_hash,
    }


@runtime_write_operation
def apply_l3_proposal(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    proposal = _find_l3_proposal(proposals, proposal_id)
    state = str(proposal.get("state") or "")
    if state != "candidate":
        raise RuntimeError("Only candidate L3 proposals can be applied.")
    kind = str(proposal.get("kind") or "")
    target = _target_path(root, kind, str(proposal.get("target_file") or ""))
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"L3 proposal target not found: {proposal.get('target_file')}")
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    if str(patch.get("kind") or "") != "full_replace":
        raise RuntimeError("Only full_replace L3 proposals are supported in the manual baseline.")
    expected_before_hash = str(patch.get("before_hash") or "")
    current_hash = _hash_path(target)
    applied_at = utc_now()
    if current_hash != expected_before_hash:
        proposal["state"] = "stale"
        proposal["stale_at"] = applied_at
        proposal["stale_reason"] = "before_hash_mismatch"
        save_l3_proposal_state(root, proposals)
        _persist_l3_proposal_page(root, proposal)
        append_runtime_history(
            root,
            {
                "event_type": "l3-proposal-stale",
                "occurred_at": applied_at,
                "proposal_id": proposal_id,
                "target_file": relative_path(root, target),
                "expected_before_hash": expected_before_hash,
                "current_hash": current_hash,
            },
        )
        raise RuntimeError("L3 proposal target is stale: before_hash mismatch.")

    before_content = target.read_text(encoding="utf-8")
    after_content = str(patch.get("content") or "")
    target.write_text(after_content, encoding="utf-8")
    after_hash = _hash_path(target)
    action_id = _unique_l3_action_id(root, "l3-proposal-apply", proposal_id)
    receipt_path = execution_receipt_path(root, action_id)
    receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-l3-proposal",
        "applied_at": applied_at,
        "operation": "apply",
        "action_id": action_id,
        "subject_kind": "l3_proposal",
        "subject_id": proposal_id,
        "proposal_kind": kind,
        "target_file": relative_path(root, target),
        "proposal_path": str(proposal.get("proposal_path") or ""),
        "before_hash": expected_before_hash,
        "after_hash": after_hash,
        "before_content": before_content,
        "after_content": after_content,
        "note": note or "",
        "revert_supported": True,
        "receipt_path": relative_path(root, receipt_path),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, receipt)
    proposal["state"] = "accepted"
    proposal["accepted_at"] = applied_at
    proposal["last_receipt_path"] = relative_path(root, receipt_path)
    proposal["after_hash"] = after_hash
    save_l3_proposal_state(root, proposals)
    _persist_l3_proposal_page(root, proposal)
    append_runtime_history(
        root,
        {
            "event_type": "l3-proposal-apply",
            "occurred_at": applied_at,
            "proposal_id": proposal_id,
            "target_file": relative_path(root, target),
            "receipt_path": relative_path(root, receipt_path),
            "before_hash": expected_before_hash,
            "after_hash": after_hash,
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "l3-proposal-apply",
        proposal_id,
        [
            f"target: `{relative_path(root, target)}`",
            f"receipt: `{relative_path(root, receipt_path)}`",
        ],
    )
    return {
        "proposal_id": proposal_id,
        "state": "accepted",
        "target_file": relative_path(root, target),
        "receipt_path": relative_path(root, receipt_path),
        "before_hash": expected_before_hash,
        "after_hash": after_hash,
    }


def _resolve_l3_receipt_path(root: Path, receipt_id: str) -> Path:
    candidate = receipt_id.strip().strip("'\"`")
    if not candidate:
        raise ValueError("receipt_id is required.")
    path = Path(candidate)
    if path.is_absolute():
        return path
    if "/" in candidate or candidate.endswith(".json"):
        return root / candidate
    return execution_receipt_path(root, candidate)


@runtime_write_operation
def revert_l3_proposal(root: Path, receipt_id: str, *, note: str | None = None) -> dict[str, Any]:
    receipt_path = _resolve_l3_receipt_path(root, receipt_id)
    receipt = load_json_document(receipt_path)
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("L3 proposal receipt is not valid.")
    if str(receipt.get("generated_by") or "") != "aiwiki-l3-proposal" or str(receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only L3 proposal apply receipts can be reverted.")
    proposal_id = str(receipt.get("subject_id") or "")
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    proposal = _find_l3_proposal(proposals, proposal_id)
    target = _target_path(root, str(proposal.get("kind") or ""), str(receipt.get("target_file") or ""))
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"L3 proposal target not found: {receipt.get('target_file')}")
    expected_after_hash = str(receipt.get("after_hash") or "")
    current_hash = _hash_path(target)
    reverted_at = utc_now()
    if current_hash != expected_after_hash:
        proposal["state"] = "revert_conflict"
        proposal["revert_conflict_at"] = reverted_at
        hint_path = l3_revert_hint_path(root, proposal)
        hint_path.parent.mkdir(parents=True, exist_ok=True)
        hint_path.write_text(
            "\n".join(
                [
                    f"# Human Merge Required: {proposal_id}",
                    "",
                    f"- target_file: `{relative_path(root, target)}`",
                    f"- receipt_path: `{relative_path(root, receipt_path)}`",
                    f"- expected_after_hash: `{expected_after_hash}`",
                    f"- current_hash: `{current_hash}`",
                    "- fallback: `human_merge_required`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        proposal["revert_hint_path"] = relative_path(root, hint_path)
        save_l3_proposal_state(root, proposals)
        _persist_l3_proposal_page(root, proposal)
        append_runtime_history(
            root,
            {
                "event_type": "l3-proposal-revert-conflict",
                "occurred_at": reverted_at,
                "proposal_id": proposal_id,
                "target_file": relative_path(root, target),
                "receipt_path": relative_path(root, receipt_path),
                "hint_path": relative_path(root, hint_path),
                "expected_after_hash": expected_after_hash,
                "current_hash": current_hash,
            },
        )
        return {
            "proposal_id": proposal_id,
            "state": "revert_conflict",
            "target_file": relative_path(root, target),
            "receipt_path": relative_path(root, receipt_path),
            "hint_path": relative_path(root, hint_path),
            "current_hash": current_hash,
            "expected_after_hash": expected_after_hash,
        }

    target.write_text(str(receipt.get("before_content") or ""), encoding="utf-8")
    restored_hash = _hash_path(target)
    action_id = _unique_l3_action_id(root, "l3-proposal-revert", proposal_id)
    revert_receipt_path = execution_receipt_path(root, action_id)
    revert_receipt = {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-l3-proposal",
        "applied_at": reverted_at,
        "operation": "revert",
        "action_id": action_id,
        "subject_kind": "l3_proposal",
        "subject_id": proposal_id,
        "source_receipt_path": relative_path(root, receipt_path),
        "target_file": relative_path(root, target),
        "before_hash": str(receipt.get("before_hash") or ""),
        "after_hash": expected_after_hash,
        "restored_hash": restored_hash,
        "note": note or "",
        "revert_supported": False,
        "receipt_path": relative_path(root, revert_receipt_path),
    }
    revert_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    revert_receipt_path.write_text(json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_execution_receipt_history(root, revert_receipt)
    proposal["state"] = "reverted"
    proposal["reverted_at"] = reverted_at
    proposal["last_revert_receipt_path"] = relative_path(root, revert_receipt_path)
    save_l3_proposal_state(root, proposals)
    _persist_l3_proposal_page(root, proposal)
    append_runtime_history(
        root,
        {
            "event_type": "l3-proposal-revert",
            "occurred_at": reverted_at,
            "proposal_id": proposal_id,
            "target_file": relative_path(root, target),
            "source_receipt_path": relative_path(root, receipt_path),
            "receipt_path": relative_path(root, revert_receipt_path),
            "restored_hash": restored_hash,
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "l3-proposal-revert",
        proposal_id,
        [
            f"target: `{relative_path(root, target)}`",
            f"receipt: `{relative_path(root, revert_receipt_path)}`",
        ],
    )
    return {
        "proposal_id": proposal_id,
        "state": "reverted",
        "target_file": relative_path(root, target),
        "source_receipt_path": relative_path(root, receipt_path),
        "receipt_path": relative_path(root, revert_receipt_path),
        "restored_hash": restored_hash,
    }
