"""Autonomy domain classification for runtime-governed apply decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

DEFAULT_AUTONOMY_PROFILE = "agentic"
AUTONOMY_DOMAINS = {"maintenance", "governance", "non_core_semantic", "core", "external"}
EXECUTION_STRATEGIES = {"auto_apply", "llm_decide_apply", "proposal_only", "human_required"}

CORE_PATH_PREFIXES = (
    "src/",
    "scripts/",
    "schema/",
    "prompts/",
    "policy/",
    ".aiwiki/policy/",
    ".aiwiki/state/autonomy-policy.json",
)
RAW_PATH_PREFIXES = ("raw/",)
EXTERNAL_PATH_PREFIXES = (".env", ".envrc", ".envrc.", "credentials", ".secrets", "secrets/")

NON_CORE_ACTION_KINDS = {
    "add-source-concept-link",
    "split-overloaded-concept",
    "expand-singleton-concept",
    "connect-isolated-source",
    "monitor-bridge-concept",
}


@dataclass(frozen=True)
class AutonomyClassification:
    autonomy_domain: str
    execution_strategy: str
    llm_governed: bool
    reason: str
    revert_required: bool = False

    def as_receipt_fields(
        self,
        *,
        decision_confidence: str | float | None = None,
        evidence_refs: list[str] | None = None,
        counter_evidence_refs: list[str] | None = None,
        validator_status: str = "not-run",
        revert_supported: bool = False,
    ) -> dict[str, Any]:
        return {
            "autonomy_domain": self.autonomy_domain,
            "llm_governed": self.llm_governed,
            "decision_confidence": "" if decision_confidence is None else str(decision_confidence),
            "evidence_refs": _string_list(evidence_refs),
            "counter_evidence_refs": _string_list(counter_evidence_refs),
            "validator_status": validator_status,
            "revert_supported": bool(revert_supported),
        }


def classify_autonomy_domain(
    *,
    subject_kind: str,
    operation: str = "",
    payload: Mapping[str, Any] | None = None,
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE,
    revert_supported: bool = False,
    root: Path | str | None = None,
) -> AutonomyClassification:
    payload = payload or {}
    subject = subject_kind.strip().lower()
    op = operation.strip().lower()
    profile = autonomy_profile.strip().lower() or DEFAULT_AUTONOMY_PROFILE
    resolved_root = _payload_root(payload, root)

    domain, reason, revert_required = _domain_for_subject(subject, op, payload, root=resolved_root)
    strategy = _strategy_for_domain(domain, profile, revert_supported=revert_supported)
    llm_governed = profile == "agentic" and domain == "non_core_semantic" and strategy == "llm_decide_apply"
    return AutonomyClassification(
        autonomy_domain=domain,
        execution_strategy=strategy,
        llm_governed=llm_governed,
        reason=reason,
        revert_required=revert_required,
    )


def classify_l3_proposal(
    proposal: Mapping[str, Any],
    *,
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE,
    revert_supported: bool = True,
    root: Path | str | None = None,
) -> AutonomyClassification:
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), Mapping) else {}
    return classify_autonomy_domain(
        subject_kind="l3_proposal",
        operation="apply",
        payload={
            "patch_kind": str(patch.get("kind") or "full_replace"),
            "target_file": str(proposal.get("target_file") or ""),
            "proposal_kind": str(proposal.get("kind") or ""),
        },
        autonomy_profile=autonomy_profile,
        revert_supported=revert_supported,
        root=root,
    )


def classify_machine_memory_action(
    action: Mapping[str, Any],
    *,
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE,
    revert_supported: bool = False,
    root: Path | str | None = None,
) -> AutonomyClassification:
    return classify_autonomy_domain(
        subject_kind="machine_memory_action",
        operation="apply",
        payload={
            "kind": str(action.get("kind") or ""),
            "primary_path": str(action.get("primary_path") or ""),
            "secondary_path": str(action.get("secondary_path") or ""),
        },
        autonomy_profile=autonomy_profile,
        revert_supported=revert_supported,
        root=root,
    )


def classify_judgment_review(
    *,
    autonomy_profile: str = DEFAULT_AUTONOMY_PROFILE,
    revert_supported: bool,
) -> AutonomyClassification:
    return classify_autonomy_domain(
        subject_kind="judgment_review",
        operation="apply",
        payload={},
        autonomy_profile=autonomy_profile,
        revert_supported=revert_supported,
    )


def _domain_for_subject(
    subject_kind: str,
    operation: str,
    payload: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> tuple[str, str, bool]:
    path_values = [
        str(payload.get(key) or "")
        for key in ("target_file", "primary_path", "secondary_path", "path")
        if payload.get(key)
    ]
    if operation in {"push", "deploy", "release", "remote", "credential"} or any(
        _classify_path_surface(path, root=root) == "external" for path in path_values
    ):
        return "external", "external side effect or credential surface", False
    if any(_classify_path_surface(path, root=root) == "raw" for path in path_values):
        return "core", "raw facts are core source-of-truth", False
    if subject_kind == "l3_proposal":
        patch_kind = str(payload.get("patch_kind") or "full_replace")
        if patch_kind == "metadata_only":
            return "governance", "metadata-only L3 bookkeeping", False
        return "core", "meaning-changing L3 prompt/policy/schema proposal", False
    if any(_classify_path_surface(path, root=root) == "core" for path in path_values):
        return "core", "core runtime/schema/prompt/policy path", False
    if subject_kind == "judgment_review":
        return "non_core_semantic", "counter-evidence judgment review history", True
    if subject_kind == "concept_review":
        return "non_core_semantic", "concept review or revisit governance", False
    if subject_kind == "machine_memory_action":
        kind = str(payload.get("kind") or "")
        if kind in NON_CORE_ACTION_KINDS:
            return "non_core_semantic", f"non-core machine-memory action: {kind}", True
        return "governance", f"machine-memory governance action: {kind}", False
    if subject_kind in {"nightly", "compile", "lint", "maintenance"}:
        return "maintenance", "runtime maintenance primitive", False
    return "governance", f"default governance subject: {subject_kind}", False


def _strategy_for_domain(domain: str, profile: str, *, revert_supported: bool) -> str:
    if domain == "external":
        return "human_required"
    if domain == "core":
        return "proposal_only"
    if profile == "agentic":
        if domain == "non_core_semantic":
            return "llm_decide_apply" if revert_supported else "proposal_only"
        return "auto_apply"
    if domain == "non_core_semantic":
        return "auto_apply" if revert_supported else "proposal_only"
    return "auto_apply"


def _payload_root(payload: Mapping[str, Any], explicit_root: Path | str | None) -> Path | None:
    raw = explicit_root
    if raw is None:
        raw = payload.get("root") or payload.get("vault_root") or payload.get("repo_root")
    if raw is None:
        return None
    try:
        return Path(raw).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return None


def _classify_path_surface(path: str, *, root: Path | None = None) -> str:
    normalized = _normalize_rel(path, root=root)
    if normalized == "__external__":
        return "external"
    normalized_lower = normalized.lower()
    if any(
        normalized_lower == prefix.rstrip("/").lower() or normalized_lower.startswith(prefix.lower())
        for prefix in EXTERNAL_PATH_PREFIXES
    ):
        return "external"
    if any(
        normalized_lower == prefix.rstrip("/").lower() or normalized_lower.startswith(prefix.lower())
        for prefix in RAW_PATH_PREFIXES
    ):
        return "raw"
    if any(
        normalized_lower == prefix.rstrip("/").lower() or normalized_lower.startswith(prefix.lower())
        for prefix in CORE_PATH_PREFIXES
    ):
        return "core"
    return "non_core"


def _normalize_rel(path: str, *, root: Path | None = None) -> str:
    text = path.strip().replace("\\", "/")
    if not text:
        return ""
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        if root is None:
            return "__external__"
        try:
            resolved = candidate.resolve(strict=False)
            rel = resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return "__external__"
        text = rel.as_posix()
    pure = PurePosixPath(text)
    parts: list[str] = []
    for part in pure.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            return "__external__"
        parts.append(part)
    if root is not None and parts:
        try:
            resolved = (root / PurePosixPath(*parts).as_posix()).resolve(strict=False)
            rel = resolved.relative_to(root)
            parts = [part for part in rel.parts if part not in {"", "."}]
        except (OSError, RuntimeError, ValueError):
            return "__external__"
    return "/".join(parts)


def _string_list(values: list[str] | None) -> list[str]:
    return [str(item) for item in (values or []) if str(item).strip()]


__all__ = [
    "AUTONOMY_DOMAINS",
    "EXECUTION_STRATEGIES",
    "AutonomyClassification",
    "classify_autonomy_domain",
    "classify_judgment_review",
    "classify_l3_proposal",
    "classify_machine_memory_action",
]
