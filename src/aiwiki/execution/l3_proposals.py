"""L3 prompt/policy proposal manual execution surface."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ..app_execution import append_execution_receipt_history
from ..app_protocol import ensure_layout
from ..app_render import append_wiki_log
from ..app_state import (
    CorruptStateError,
    append_runtime_history,
    execution_receipt_history_path,
    l3_proposal_state_path,
    load_json_document_strict,
    runtime_history_path,
    save_json_document,
)
from ..app_utils import (
    _durable_truncate,
    atomic_write_bytes,
    atomic_write_text,
    next_available_stem,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    sha256_file,
    slugify,
    utc_now,
)
from ..render.paths import execution_receipt_path
from .alchemy import _restore_file_bytes, _snapshot_file_bytes
from .audit_preview import AUDIT_STREAM_PATH

L3_PROPOSAL_KINDS = ("prompt_proposal", "policy_proposal")
L3_PROPOSAL_STATES = ("candidate", "accepted", "rejected", "reverted", "stale", "revert_conflict")
L3_TRIGGER_PATTERNS = ("failure_cluster", "recurring_feedback", "drift", "contract_failure", "manual_fixture")
_PLANNER_LOG_REL_PATH = ".aiwiki/state/planner-log.jsonl"

logger = logging.getLogger(__name__)


class L3PostApplyAuditError(RuntimeError):
    def __init__(
        self,
        action_id: str,
        failed_step: str,
        *,
        target_file: str,
        before_hash: str,
        after_hash: str,
        target_reverted: bool = False,
        deleted_receipt_path: str = "",
    ):
        suffix = "; target reverted" if target_reverted else ""
        super().__init__(f"L3 apply audit step '{failed_step}' failed for {action_id}{suffix}")
        self.action_id = action_id
        self.failed_step = failed_step
        self.target_file = target_file
        self.before_hash = before_hash
        self.after_hash = after_hash
        self.target_reverted = target_reverted
        self.deleted_receipt_path = deleted_receipt_path


class L3RevertError(RuntimeError):
    """Raised when L3 transactional rollback cannot restore the target."""


class L3ProposalCreateError(RuntimeError):
    """Raised when L3 proposal creation fails and rollback succeeds."""


class L3ProposalCreateHalfWriteError(RuntimeError):
    """Raised when L3 proposal creation fails and rollback also fails; manual recovery needed."""


def default_l3_proposal_state() -> dict[str, Any]:
    return {"version": 1, "proposals": []}


def load_l3_proposal_state(root: Path) -> dict[str, Any]:
    """Strict loader for L3 proposal authoritative state.

    Raises ``CorruptStateError`` (via ``load_json_document_strict``) if the
    state file exists but is unparseable, preserving fail-closed governance
    semantics. Missing files yield the default empty state. Structural faults
    (non-dict document, non-list ``proposals``) also raise ``CorruptStateError``
    so callers cannot silently overwrite a damaged registry.
    """

    path = l3_proposal_state_path(root)
    if not path.exists():
        return default_l3_proposal_state()
    document = load_json_document_strict(path)
    if not isinstance(document, dict):
        raise CorruptStateError(
            path=path,
            reason="L3 proposal state is not a JSON object",
        )
    proposals = document.get("proposals")
    if not isinstance(proposals, list):
        raise CorruptStateError(
            path=path,
            reason="L3 proposal state has non-list 'proposals' field",
        )
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


def _resolve_workspace_path(root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else root / path
    try:
        resolved.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("path must stay within the workspace.") from exc
    return resolved


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
    atomic_write_text(path, _render_l3_proposal_page(proposal))


def _unique_l3_action_id(root: Path, prefix: str, proposal_id: str) -> str:
    seed = f"{prefix}-{slugify(proposal_id)}"
    stem = next_available_stem(execution_receipt_path(root, seed).parent, seed, ".json")
    return stem


def _receipt_audit_metadata(root: Path) -> dict[str, str]:
    return {
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": relative_path(root, execution_receipt_history_path(root)),
    }


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


def preview_l3_proposal_generation(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be a positive integer.")
    resolved_path = _resolve_workspace_path(root, planner_log_path or Path(_PLANNER_LOG_REL_PATH))
    if not resolved_path.exists():
        return {
            "status": "ok",
            "generation_mode": "preview",
            "automatic_generation_enabled": True,
            "side_effects_allowed": False,
            "planner_log_path": relative_path(root, resolved_path),
            "candidate_count": 0,
            "blocked_count": 0,
            "returned_count": 0,
            "candidates": [],
            "limit": limit,
        }

    candidates: list[dict[str, Any]] = []
    matched_count = 0
    scanned_count = 0
    blocked_count = 0
    with resolved_path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            payload = raw_line.strip()
            if not payload:
                continue
            scanned_count += 1
            try:
                record = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid planner-log.jsonl JSON at line {line_no}: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"invalid planner-log.jsonl record at line {line_no}: expected object")
            if str(record.get("decision") or "") != "generate-proposal":
                continue
            reason_codes = [str(item) for item in record.get("reason_codes", []) if isinstance(item, str)]
            if "proposal_recommended" not in reason_codes:
                continue
            matched_count += 1
            target_file = "prompts/ask.md"
            target_exists = (root / target_file).is_file()
            mode = str(record.get("mode") or "")
            eligible = mode == "execute" and target_exists
            blockers: list[str] = []
            if mode != "execute":
                blockers.append("requires_execute_mode")
            if not target_exists:
                blockers.append("target_missing")
            if blockers:
                blocked_count += 1
            if len(candidates) >= limit:
                continue
            candidates.append(
                {
                    "signal_id": str(record.get("signal_id") or ""),
                    "trace_id": str(record.get("trace_id") or ""),
                    "dedupe_key": str(record.get("dedupe_key") or ""),
                    "mode": mode,
                    "decided_at": str(record.get("decided_at") or ""),
                    "reason_codes": reason_codes,
                    "eligible": eligible,
                    "proposal_kind": "prompt_proposal",
                    "proposal_id": _automatic_l3_proposal_id(str(record.get("signal_id") or "")),
                    "target_file": target_file,
                    "blockers": blockers,
                }
            )

    return {
        "status": "ok",
        "generation_mode": "preview",
        "automatic_generation_enabled": True,
        "side_effects_allowed": False,
        "planner_log_path": relative_path(root, resolved_path),
        "scanned_count": scanned_count,
        "candidate_count": matched_count,
        "blocked_count": blocked_count,
        "returned_count": len(candidates),
        "candidates": candidates,
        "limit": limit,
    }


@runtime_write_operation
def generate_l3_proposals_from_planner(
    root: Path,
    *,
    planner_log_path: Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    preview = preview_l3_proposal_generation(root, planner_log_path=planner_log_path, limit=limit)
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    existing_ids = {str(item.get("proposal_id") or "") for item in proposals}
    generated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in preview.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        proposal_id = str(candidate.get("proposal_id") or "")
        if not candidate.get("eligible"):
            skipped.append({"proposal_id": proposal_id, "reason": "not_eligible"})
            continue
        if proposal_id in existing_ids:
            skipped.append({"proposal_id": proposal_id, "reason": "already_exists"})
            continue
        kind = str(candidate.get("proposal_kind") or "prompt_proposal")
        target_file = str(candidate.get("target_file") or "")
        target = _target_path(root, kind, target_file)
        current_content = target.read_text(encoding="utf-8", errors="replace")
        signal_id = str(candidate.get("signal_id") or "")
        content = _automatic_l3_prompt_content(
            current_content,
            candidate=candidate,
            planner_log_path=str(preview.get("planner_log_path") or ""),
        )
        result = create_l3_proposal(
            root,
            kind=kind,
            proposal_id=proposal_id,
            target_file=target_file,
            content=content,
            rationale=f"Automatically generated from execute-mode planner decision {signal_id}. Manual accept is still required.",
            evidence_refs=[f"{preview.get('planner_log_path')}#{signal_id}"],
            signal_ids=[signal_id],
            pattern=_automatic_l3_pattern(candidate),
            patch_kind="metadata_only",
        )
        generated.append(result)
        existing_ids.add(proposal_id)

    return {
        **preview,
        "generation_mode": "apply",
        "side_effects_allowed": True,
        "generated_count": len(generated),
        "skipped_count": len(skipped),
        "generated": generated,
        "skipped": skipped,
    }


def _automatic_l3_proposal_id(signal_id: str) -> str:
    return slugify(f"auto-{signal_id or 'planner-signal'}")


def _automatic_l3_prompt_content(
    current_content: str,
    *,
    candidate: dict[str, Any],
    planner_log_path: str,
) -> str:
    signal_id = str(candidate.get("signal_id") or "") or "(unknown)"
    trace_id = str(candidate.get("trace_id") or "") or "(unknown)"
    decided_at = str(candidate.get("decided_at") or "") or "(unknown)"
    dedupe_key = str(candidate.get("dedupe_key") or "") or "(unknown)"
    reason_codes = [str(item) for item in (candidate.get("reason_codes") or []) if isinstance(item, str)]
    reason_codes_text = ", ".join(reason_codes) if reason_codes else "(none)"
    evidence_path = planner_log_path or "(unknown)"
    base = current_content.rstrip()
    section = "\n".join(
        [
            "",
            "<!-- aiwiki:auto-proposal:start -->",
            "",
            "## Auto-generated L3 proposal review",
            "",
            "This block was automatically produced from an execute-mode planner decision. Review the",
            "context below and decide whether to accept the change before applying.",
            "",
            "### Planner decision",
            "",
            f"- `signal_id`: {signal_id}",
            f"- `trace_id`: {trace_id}",
            f"- `decided_at`: {decided_at}",
            f"- `dedupe_key`: {dedupe_key}",
            f"- `reason_codes`: {reason_codes_text}",
            "",
            "### Evidence references",
            "",
            f"- `{evidence_path}#{signal_id}`",
            "",
            "<!-- aiwiki:auto-proposal:end -->",
        ]
    )
    return base + section + "\n"


def _automatic_l3_pattern(candidate: dict[str, Any]) -> str:
    reason_codes = [str(item) for item in candidate.get("reason_codes", []) if isinstance(item, str)]
    if "drift_observed" in reason_codes:
        return "drift"
    if "runtime_failure_observed" in reason_codes:
        return "contract_failure"
    if "learning_threshold_observed" in reason_codes:
        return "recurring_feedback"
    return "failure_cluster"


@runtime_write_operation
def reject_l3_proposal(root: Path, proposal_id: str, *, note: str | None = None) -> dict[str, Any]:
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    proposal = _find_l3_proposal(proposals, proposal_id)
    if str(proposal.get("state") or "") != "candidate":
        raise RuntimeError("Only candidate L3 proposals can be rejected.")
    rejected_at = utc_now()
    proposal["state"] = "rejected"
    proposal["rejected_at"] = rejected_at
    proposal["reject_note"] = note or ""
    save_l3_proposal_state(root, proposals)
    _persist_l3_proposal_page(root, proposal)
    append_runtime_history(
        root,
        {
            "event_type": "l3-proposal-reject",
            "occurred_at": rejected_at,
            "proposal_id": proposal_id,
            "kind": str(proposal.get("kind") or ""),
            "target_file": str(proposal.get("target_file") or ""),
            "proposal_path": str(proposal.get("proposal_path") or ""),
            "state": "rejected",
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "l3-proposal-reject",
        proposal_id,
        [
            f"kind: `{proposal.get('kind', '')}`",
            f"target: `{proposal.get('target_file', '')}`",
            "state: `rejected`",
        ],
    )
    return {
        "proposal_id": proposal_id,
        "kind": str(proposal.get("kind") or ""),
        "state": "rejected",
        "target_file": str(proposal.get("target_file") or ""),
        "proposal_path": str(proposal.get("proposal_path") or ""),
        "rejected_at": rejected_at,
    }


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
    patch_kind: str = "full_replace",
) -> dict[str, Any]:
    from aiwiki import autonomy_policy

    # M7.4b3 Kill Switch: l3 generate hook. disabled → no proposal write.
    reason = autonomy_policy.disabled_reason(root, "disable_l3_generate")
    if reason is not None:
        return {
            "status": "skipped",
            "flag": "disable_l3_generate",
            "reason": reason,
            "kind": kind,
            "target_file": target_file,
        }

    ensure_layout(root)
    if kind not in L3_PROPOSAL_KINDS:
        raise ValueError(f"Unsupported L3 proposal kind: {kind}")
    if pattern not in L3_TRIGGER_PATTERNS:
        raise ValueError(f"Unsupported L3 trigger pattern: {pattern}")
    if patch_kind not in {"full_replace", "metadata_only"}:
        raise ValueError(f"Unsupported L3 patch_kind: {patch_kind}")
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
            "kind": patch_kind,
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
    state_path = l3_proposal_state_path(root)
    runtime_path = runtime_history_path(root)
    audit_path = root / AUDIT_STREAM_PATH
    wiki_log_path = root / "wiki" / "indexes" / "log.md"
    snapshots: list[tuple[Path, bytes | None]] = [
        (state_path, _snapshot_file_bytes(state_path)),
        (proposal_path, _snapshot_file_bytes(proposal_path)),
        (runtime_path, _snapshot_file_bytes(runtime_path)),
        (audit_path, _snapshot_file_bytes(audit_path)),
        (wiki_log_path, _snapshot_file_bytes(wiki_log_path)),
    ]
    try:
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
    except Exception as tx_exc:
        try:
            for path, snapshot in reversed(snapshots):
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    _restore_file_bytes(path, snapshot)
        except Exception as rollback_exc:
            raise L3ProposalCreateHalfWriteError(
                f"l3 proposal create rollback failed for {normalized_id}: tx_error={tx_exc}; "
                f"rollback_error={rollback_exc}"
            ) from rollback_exc
        raise L3ProposalCreateError(
            f"l3 proposal create failed for {normalized_id}; mutation rolled back"
        ) from tx_exc
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
    original_proposal = copy.deepcopy(proposal)
    state = str(proposal.get("state") or "")
    if state != "candidate":
        raise RuntimeError("Only candidate L3 proposals can be applied.")
    kind = str(proposal.get("kind") or "")
    target = _target_path(root, kind, str(proposal.get("target_file") or ""))
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"L3 proposal target not found: {proposal.get('target_file')}")
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    patch_kind_value = str(patch.get("kind") or "full_replace")
    if patch_kind_value not in {"full_replace", "metadata_only"}:
        raise RuntimeError(
            "Only full_replace or metadata_only L3 proposals are supported in the manual baseline."
        )
    is_metadata_only = patch_kind_value == "metadata_only"
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

    snapshot = target.read_bytes() if target.exists() else None
    before_content = target.read_text(encoding="utf-8")
    # metadata_only: target file untouched; after == before for all hash/content fields.
    # Patch.content is preserved on the proposal page as review context, not written to target.
    after_content = before_content if is_metadata_only else str(patch.get("content") or "")
    before_hash_for_audit = hashlib.sha256(snapshot or b"").hexdigest()
    after_hash_for_audit = hashlib.sha256(after_content.encode("utf-8")).hexdigest()
    try:
        if not is_metadata_only:
            atomic_write_text(target, after_content)
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
            "patch_kind": patch_kind_value,
            "target_file": relative_path(root, target),
            "proposal_path": str(proposal.get("proposal_path") or ""),
            "before_hash": expected_before_hash,
            "after_hash": after_hash,
            "before_content": before_content,
            "after_content": after_content,
            "note": note or "",
            "revert_supported": True,
            "receipt_path": relative_path(root, receipt_path),
            **_receipt_audit_metadata(root),
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except Exception:
        if snapshot is not None:
            atomic_write_bytes(target, snapshot)
        else:
            target.unlink(missing_ok=True)
        raise

    history_jsonl_path = execution_receipt_history_path(root)
    audit_jsonl_path = root / AUDIT_STREAM_PATH
    runtime_history_jsonl_path = runtime_history_path(root)
    history_size_before = history_jsonl_path.stat().st_size if history_jsonl_path.exists() else 0
    audit_size_before = audit_jsonl_path.stat().st_size if audit_jsonl_path.exists() else 0
    runtime_history_size_before = (
        runtime_history_jsonl_path.stat().st_size if runtime_history_jsonl_path.exists() else 0
    )
    state_restore_steps = {
        "_persist_l3_proposal_page",
        "append_execution_receipt_history",
        "append_runtime_history",
        "append_wiki_log",
    }
    history_truncate_steps = {
        "append_execution_receipt_history",
        "append_runtime_history",
        "append_wiki_log",
    }

    def _raise_post_apply_audit_error(failed_step: str, exc: Exception) -> None:
        try:
            if snapshot is not None:
                atomic_write_bytes(target, snapshot)
            else:
                target.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)
            if failed_step in state_restore_steps:
                proposal.clear()
                proposal.update(original_proposal)
                save_l3_proposal_state(root, proposals)
                _persist_l3_proposal_page(root, original_proposal)
            if failed_step in history_truncate_steps:
                # Reversed write-order rollback (R96.8): audit mirror first,
                # then runtime-history primary, then execution-receipts primary.
                if audit_jsonl_path.exists():
                    _durable_truncate(audit_jsonl_path, audit_size_before)
                if runtime_history_jsonl_path.exists():
                    _durable_truncate(runtime_history_jsonl_path, runtime_history_size_before)
                if history_jsonl_path.exists():
                    _durable_truncate(history_jsonl_path, history_size_before)
        except Exception as revert_exc:
            raise L3RevertError(
                f"audit step '{failed_step}' failed and rollback also failed: "
                f"audit={exc!r}; revert={revert_exc!r}"
            ) from exc
        raise L3PostApplyAuditError(
            action_id,
            failed_step,
            target_file=relative_path(root, target),
            before_hash=before_hash_for_audit,
            after_hash=after_hash_for_audit,
            target_reverted=True,
            deleted_receipt_path=relative_path(root, receipt_path),
        ) from exc

    failed_step = "save_l3_proposal_state"
    try:
        proposal["state"] = "accepted"
        proposal["accepted_at"] = applied_at
        proposal["last_receipt_path"] = relative_path(root, receipt_path)
        proposal["after_hash"] = after_hash
        save_l3_proposal_state(root, proposals)
        failed_step = "_persist_l3_proposal_page"
        _persist_l3_proposal_page(root, proposal)
        failed_step = "append_execution_receipt_history"
        append_execution_receipt_history(root, receipt)
        failed_step = "append_runtime_history"
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
        failed_step = "append_wiki_log"
        append_wiki_log(
            root,
            "l3-proposal-apply",
            proposal_id,
            [
                f"target: `{relative_path(root, target)}`",
                f"receipt: `{relative_path(root, receipt_path)}`",
            ],
        )
    except Exception as exc:
        _raise_post_apply_audit_error(failed_step, exc)
    return {
        "proposal_id": proposal_id,
        "state": "accepted",
        "target_file": relative_path(root, target),
        "receipt_path": relative_path(root, receipt_path),
        "before_hash": expected_before_hash,
        "after_hash": after_hash,
        "audit_path": relative_path(root, execution_receipt_history_path(root)),
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
    receipt = load_json_document_strict(receipt_path)
    actionable_hint = (
        "Expected receipt JSON under output/control/execution-receipts/ with kind=execution-receipt "
        "and generated_by=aiwiki-l3-proposal. Try `aiwiki revert l3-proposal-apply-<proposal_id>`."
    )
    if not isinstance(receipt, dict) or str(receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError(f"L3 proposal receipt is not valid: {receipt_id}. {actionable_hint}")
    if str(receipt.get("generated_by") or "") != "aiwiki-l3-proposal" or str(receipt.get("operation") or "") != "apply":
        raise RuntimeError(f"Only L3 proposal apply receipts can be reverted: {receipt_id}. {actionable_hint}")
    proposal_id = str(receipt.get("subject_id") or "")
    proposals = [dict(item) for item in load_l3_proposal_state(root).get("proposals", []) if isinstance(item, dict)]
    proposal = _find_l3_proposal(proposals, proposal_id)
    target = _target_path(root, str(proposal.get("kind") or ""), str(receipt.get("target_file") or ""))
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"L3 proposal target not found: {receipt.get('target_file')}")
    # F-INV-23: receipt["after_hash"] in revert context is the *expected
    # pre-revert* hash (i.e. the apply-receipt's recorded post-apply hash).
    # It is NOT recomputed from disk here; treat it as the conflict-gate
    # reference. Compare against current_hash to detect drift since apply.
    expected_after_hash = str(receipt.get("after_hash") or "")
    current_hash = _hash_path(target)
    reverted_at = utc_now()
    receipt_patch_kind = str(receipt.get("patch_kind") or "full_replace")
    is_metadata_only_revert = receipt_patch_kind == "metadata_only"
    # metadata_only revert is a no-op file operation; target drift is not a
    # merge responsibility for this proposal, so skip the conflict gate.
    if not is_metadata_only_revert and current_hash != expected_after_hash:
        proposal["state"] = "revert_conflict"
        proposal["revert_conflict_at"] = reverted_at
        hint_path = l3_revert_hint_path(root, proposal)
        hint_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            hint_path,
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

    # R94.5: capture target's pre-revert bytes (the applied/candidate content)
    # so we can roll back if the critical section fails. Without this, a failed
    # state save would leave target=before_content but state=accepted, breaking
    # the receipt→state mapping and forcing human merge on retry.
    before_revert_bytes = target.read_bytes()
    action_id = _unique_l3_action_id(root, "l3-proposal-revert", proposal_id)
    revert_receipt_path = execution_receipt_path(root, action_id)
    wrote_target = False
    wrote_receipt = False
    try:
        if not is_metadata_only_revert:
            atomic_write_text(target, str(receipt.get("before_content") or ""))
            wrote_target = True
        restored_hash = _hash_path(target)
        # F-INV-23: revert receipt hash field semantics:
        # - `before_hash`: pre-apply hash (carried over from apply receipt;
        #   what target looked like before the original apply).
        # - `after_hash`: expected pre-revert hash (carried over from apply
        #   receipt's post-apply hash; conflict-gate reference, NOT recomputed).
        # - `restored_hash`: actual post-revert hash (computed from disk after
        #   atomic write-back; for metadata_only this equals current target hash
        #   without any write).
        # In no-drift full_replace: restored_hash == before_hash.
        # In no-drift metadata_only: restored_hash == after_hash (no file change).
        # Under drift (external modification between apply and revert),
        # restored_hash may differ from both before_hash and after_hash.
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
            "patch_kind": receipt_patch_kind,
            "target_file": relative_path(root, target),
            "before_hash": str(receipt.get("before_hash") or ""),
            "after_hash": expected_after_hash,
            "restored_hash": restored_hash,
            "note": note or "",
            "revert_supported": False,
            "receipt_path": relative_path(root, revert_receipt_path),
            **_receipt_audit_metadata(root),
        }
        revert_receipt_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(revert_receipt_path, json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        wrote_receipt = True
        proposal["state"] = "reverted"
        proposal["reverted_at"] = reverted_at
        proposal["last_revert_receipt_path"] = relative_path(root, revert_receipt_path)
        save_l3_proposal_state(root, proposals)
    except BaseException:
        # R94.5: critical-section failure after target overwrite — restore
        # original bytes via byte-level atomic write AND remove any orphan
        # revert-receipt file that was written before the failure (otherwise
        # we'd leave a false audit record claiming revert happened). Inner
        # except is BaseException so KeyboardInterrupt during rollback never
        # masks the original error; rollback failures are logged.
        if wrote_target:
            try:
                atomic_write_bytes(target, before_revert_bytes)
            except BaseException as rollback_exc:
                logger.warning(
                    "l3-proposal revert target rollback failed for %s: %s (%s)",
                    target,
                    rollback_exc,
                    type(rollback_exc).__name__,
                )
        if wrote_receipt:
            try:
                revert_receipt_path.unlink(missing_ok=True)
            except BaseException as rollback_exc:
                logger.warning(
                    "l3-proposal revert receipt unlink failed for %s: %s (%s)",
                    revert_receipt_path,
                    rollback_exc,
                    type(rollback_exc).__name__,
                )
        raise
    # Phase 2 (best-effort, fully isolated): audit history append, page render,
    # runtime history, wiki log. State is already SOT; replay/recompile fixes
    # any derived staleness. Failures here MUST NOT raise — caller would
    # naturally retry, but a retried revert would see current_hash != after_hash
    # and fall into revert_conflict, polluting an already-successful revert.
    # Each step is logged on failure so operators can re-index/replay.
    for step_name, step_fn in (
        ("append_execution_receipt_history", lambda: append_execution_receipt_history(root, revert_receipt)),
        ("_persist_l3_proposal_page", lambda: _persist_l3_proposal_page(root, proposal)),
        (
            "append_runtime_history",
            lambda: append_runtime_history(
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
            ),
        ),
        (
            "append_wiki_log",
            lambda: append_wiki_log(
                root,
                "l3-proposal-revert",
                proposal_id,
                [
                    f"target: `{relative_path(root, target)}`",
                    f"receipt: `{relative_path(root, revert_receipt_path)}`",
                ],
            ),
        ),
    ):
        try:
            step_fn()
        except Exception as phase2_exc:
            logger.warning(
                "l3-proposal revert phase 2 step %s failed for %s: %s (%s); state already saved",
                step_name,
                proposal_id,
                phase2_exc,
                type(phase2_exc).__name__,
            )
    return {
        "proposal_id": proposal_id,
        "state": "reverted",
        "target_file": relative_path(root, target),
        "source_receipt_path": relative_path(root, receipt_path),
        "receipt_path": relative_path(root, revert_receipt_path),
        "restored_hash": restored_hash,
        "audit_path": relative_path(root, execution_receipt_history_path(root)),
    }
