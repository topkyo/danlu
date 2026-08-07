"""Pure knowledge lifecycle selection, display, and summary helpers.

Also owns the knowledge-lifecycle *state* I/O (default / load / save / override /
active-overrides), extracted from the legacy app_state hub.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.concept_quality import build_concept_quality
from ..content.io import entry_ids_from_paths, entry_lookup_maps
from ..content.material import load_active_corpora_state
from ..corpus.link_state import load_concept_rewrite_state
from ..memory.state import load_machine_memory
from ..protocol.scaffold import ensure_layout
from ..state.collections import active_records_by_key, normalize_versioned_record_list_state
from ..state.constants import (
    DEFAULT_PROTOCOL,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
)
from ..state.io import load_json_document, save_json_document
from ..state.manifest import load_manifest
from ..utils.markdown import extract_provenance_paths, parse_frontmatter
from ..utils.path import relative_path
from .paths import (
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
)
from .status import collect_curated_pages


def default_knowledge_lifecycle_state() -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    return {
        "version": 1,
        "generated_at": "",
        "entries": [],
        "counts": {
            "total": 0,
            "by_state": dict(by_state),
            "by_kind": {kind: {"total": 0, "by_state": dict(by_state)} for kind in KNOWLEDGE_LIFECYCLE_KINDS},
            "invalidated": 0,
            "active_corpus_linked": 0,
        },
    }


def load_knowledge_lifecycle_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_state_path(root))
    if not isinstance(document, dict):
        return default_knowledge_lifecycle_state()
    entries = document.get("entries")
    if not isinstance(entries, list):
        return default_knowledge_lifecycle_state()
    counts = document.get("counts")
    if not isinstance(counts, dict):
        counts = default_knowledge_lifecycle_state()["counts"]
    return {
        "version": int(document.get("version", 1) or 1),
        "generated_at": str(document.get("generated_at") or ""),
        "entries": [entry for entry in entries if isinstance(entry, dict)],
        "counts": counts,
    }


def save_knowledge_lifecycle_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_state_path(root), document)


def default_knowledge_lifecycle_override_state() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    document = load_json_document(knowledge_lifecycle_override_state_path(root))
    return normalize_versioned_record_list_state(
        document,
        default_state=default_knowledge_lifecycle_override_state,
        list_key="entries",
    )


def save_knowledge_lifecycle_override_state(root: Path, document: dict[str, Any]) -> None:
    save_json_document(knowledge_lifecycle_override_state_path(root), document)


def ensure_knowledge_lifecycle_override_state(root: Path) -> dict[str, Any]:
    state = load_knowledge_lifecycle_override_state(root)
    path = knowledge_lifecycle_override_state_path(root)
    if not path.exists():
        save_knowledge_lifecycle_override_state(root, state)
    return state


def active_knowledge_lifecycle_overrides(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return active_records_by_key(document, list_key="entries", key="path")


def knowledge_lifecycle_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    by_kind = {
        kind: {"total": 0, "by_state": {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}}
        for kind in KNOWLEDGE_LIFECYCLE_KINDS
    }
    invalidated = 0
    active_corpus_linked = 0
    for entry in entries:
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        kind = str(entry.get("kind") or "")
        if lifecycle_state in by_state:
            by_state[lifecycle_state] += 1
        if kind in by_kind:
            by_kind[kind]["total"] += 1
            if lifecycle_state in by_kind[kind]["by_state"]:
                by_kind[kind]["by_state"][lifecycle_state] += 1
        if entry.get("invalidation_signals"):
            invalidated += 1
        if entry.get("active_corpus_ids"):
            active_corpus_linked += 1
    return {
        "total": len(entries),
        "by_state": by_state,
        "by_kind": by_kind,
        "invalidated": invalidated,
        "active_corpus_linked": active_corpus_linked,
    }


def display_knowledge_lifecycle_state(state: str) -> str:
    mapping = {
        "active": "活跃",
        "review": "待审",
        "deferred": "暂挂",
        "retired": "已退役",
        "revisit": "待回看",
    }
    return mapping.get(state, state or "unknown")


def display_judgment_lifecycle_state(state: str) -> str:
    mapping = {
        "formed": "已形成",
        "active": "活跃",
        "under-review": "复审中",
        "revised": "已修订",
        "retired": "已退役",
    }
    return mapping.get(state, state or "unknown")


def display_protocol_relevance_mode(mode: str) -> str:
    mapping = {
        "source-top1": "top1",
        "strong-top2": "strong-top2",
        "cross-protocol-bridge": "bridge-top2",
    }
    return mapping.get(mode, mode or "unknown")


def display_protocol_relevance_ambiguity(state: str) -> str:
    mapping = {
        "dominant": "dominant",
        "mixed": "mixed",
        "bridge": "bridge",
    }
    return mapping.get(state, state or "unknown")


def select_knowledge_lifecycle_entries(
    knowledge_lifecycle: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    states: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        if kinds is not None and kind not in kinds:
            continue
        if states is not None and lifecycle_state not in states:
            continue
        selected.append(dict(entry))
    return selected


def sort_knowledge_lifecycle_entries(
    entries: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    state_rank = {"revisit": 0, "review": 1, "active": 2, "deferred": 3, "retired": 4}
    return sorted(
        entries,
        key=lambda entry: (
            state_rank.get(str(entry.get("lifecycle_state") or ""), 9),
            0 if str(entry.get("protocol") or "") == active_protocol and active_protocol else 1,
            0 if bool(entry.get("override_active")) else 1,
            -len(entry.get("invalidation_signals", []) if isinstance(entry.get("invalidation_signals"), list) else []),
            -len(entry.get("active_corpus_ids", []) if isinstance(entry.get("active_corpus_ids"), list) else []),
            str(entry.get("title") or "").lower(),
        ),
    )


def render_knowledge_lifecycle_entry_summary(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("page_id") or "unknown")
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "knowledge")
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    parts = [
        f"kind `{kind}`",
        f"state `{display_knowledge_lifecycle_state(lifecycle_state)}`",
    ]
    judgment_lifecycle_state = str(entry.get("judgment_lifecycle_state") or "")
    if kind in {"decision", "judgment"} and judgment_lifecycle_state:
        parts.append(f"judgment_state `{display_judgment_lifecycle_state(judgment_lifecycle_state)}`")
    if bool(entry.get("override_active")):
        parts.append(f"override `{str(entry.get('override_state') or lifecycle_state or 'unknown')}`")
    invalidation_signals = entry.get("invalidation_signals", [])
    if isinstance(invalidation_signals, list) and invalidation_signals:
        parts.append(f"invalidation `{','.join(str(item) for item in invalidation_signals[:3])}`")
    active_corpus_ids = entry.get("active_corpus_ids", [])
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        parts.append(f"active_corpora `{len(active_corpus_ids)}`")
    review_signal_codes = entry.get("review_signal_codes", [])
    if isinstance(review_signal_codes, list) and review_signal_codes:
        parts.append(f"review_signals `{','.join(str(item) for item in review_signal_codes[:3])}`")
    reason_codes = entry.get("reason_codes", [])
    if isinstance(reason_codes, list) and reason_codes:
        parts.append(f"reasons `{','.join(str(item) for item in reason_codes[:3])}`")
    protocol_relevance_mode = str(entry.get("protocol_relevance_primary_mode") or "")
    if protocol_relevance_mode:
        parts.append(f"protocol_relevance `{display_protocol_relevance_mode(protocol_relevance_mode)}`")
    protocol_relevance_ambiguity = str(entry.get("protocol_relevance_ambiguity") or "")
    if protocol_relevance_ambiguity:
        parts.append(f"protocol_ambiguity `{display_protocol_relevance_ambiguity(protocol_relevance_ambiguity)}`")
    return f"- [{title}](../../{path}) | " + " | ".join(parts)


def judgment_lifecycle_profile(page: dict[str, Any]) -> tuple[str, list[str]]:
    kind = str(page.get("kind") or "")
    status = str(page.get("status") or "")
    terminal_statuses = {"superseded"} if kind == "decision" else {"rejected"}
    if status in terminal_statuses:
        return "retired", ["terminal-status", status]
    reasons: list[str] = []
    if status in {"tracking", "needs-revisit"}:
        reasons.append("explicit-review-status")
    if str(page.get("overdue_review") or "").lower() == "true" or page.get("overdue_review") is True:
        reasons.append("overdue-review")
    if str(page.get("escalation_candidate") or "").lower() == "true" or page.get("escalation_candidate") is True:
        reasons.append("escalation-candidate")
    if str(page.get("citation_drift") or "").lower() == "true" or page.get("citation_drift") is True:
        reasons.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or 0) > 0:
        reasons.append("citation-snapshot-gap")
    if reasons:
        return "under-review", reasons
    if int(page.get("review_history_entries", "0") or 0) > 1:
        return "revised", ["reviewed-multiple-times"]
    if str(page.get("last_reviewed") or page.get("reviewed_at") or "") or status in {"approved", "confirmed"}:
        return "active", ["reviewed-active"]
    return "formed", ["filed-back"]


def knowledge_lifecycle_invalidation_signals(page: dict[str, str]) -> list[str]:
    signals: list[str] = []
    if str(page.get("status") or "") == "needs-revisit":
        signals.append("explicit-needs-revisit")
    if page.get("citation_drift") == "true":
        signals.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        signals.append("citation-snapshot-gap")
    if page.get("overdue_review") == "true":
        signals.append("overdue-review")
    if page.get("escalation_candidate") == "true":
        signals.append("escalation-candidate")
    return signals


def knowledge_lifecycle_active_corpus_ids(
    source_ids: list[str],
    active_corpora: list[dict[str, Any]],
    *,
    concept_slug: str = "",
) -> list[str]:
    source_id_set = {source_id for source_id in source_ids if source_id}
    active_ids: list[str] = []
    for corpus in active_corpora:
        if str(corpus.get("status") or "") not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        if concept_slug:
            concept_slugs = {str(item) for item in corpus.get("concept_slugs", []) if isinstance(item, str)}
            if concept_slug in concept_slugs and corpus_id not in active_ids:
                active_ids.append(corpus_id)
                continue
        if not source_id_set:
            continue
        corpus_source_ids = {
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        }
        if source_id_set & corpus_source_ids:
            active_ids.append(corpus_id)
    return sorted(active_ids)


def knowledge_lifecycle_classification(
    *,
    status: str,
    pending_review: bool,
    invalidation_signals: list[str],
    active_corpus_ids: list[str],
) -> tuple[str, list[str]]:
    if status in {"superseded", "rejected"}:
        return "retired", ["terminal-status"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if pending_review:
        return "review", ["pending-review-status"]
    if active_corpus_ids and status in {"approved", "confirmed"}:
        return "active", ["active-corpus-linked"]
    return "deferred", ["reviewed-idle"]


def concept_lifecycle_invalidation_signals(quality_record: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if quality_record.get("conflict_signals"):
        signals.append("concept-conflict")
    if quality_record.get("gap_signals"):
        signals.append("concept-evidence-gap")
    return signals


def concept_lifecycle_review_signals(
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
    *,
    active_corpus_ids: list[str],
) -> list[str]:
    signals: list[str] = []
    proposal_status = str(rewrite_proposal.get("status") or "")
    if rewrite_proposal.get("active") and rewrite_proposal.get("pending_review") == "true":
        if proposal_status == "accepted":
            signals.append("rewrite-proposal-accepted")
        elif proposal_status == "deferred":
            signals.append("rewrite-proposal-deferred")
        else:
            signals.append("rewrite-proposal-proposed")
    if rewrite_proposal.get("apply_ready"):
        signals.append("rewrite-apply-ready")
    if active_corpus_ids and str(quality_record.get("quality_state") or "") != "stable":
        signals.append("active-quality-pressure")
    return signals


def concept_lifecycle_classification(
    *,
    source_ids: list[str],
    active_corpus_ids: list[str],
    invalidation_signals: list[str],
    review_signals: list[str],
) -> tuple[str, list[str]]:
    if not source_ids:
        return "retired", ["no-source-pages"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if review_signals:
        return "review", ["quality-review", *review_signals]
    if active_corpus_ids:
        return "active", ["active-corpus-linked"]
    return "deferred", ["compiled-idle"]


def build_knowledge_lifecycle_entry(
    root: Path,
    page: dict[str, str],
    *,
    expected_kind: str,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
    if not citations and content:
        citations = extract_provenance_paths(root, content)
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(source_ids, active_corpora)
    invalidation_signals = knowledge_lifecycle_invalidation_signals(page)
    lifecycle_state, reason_codes = knowledge_lifecycle_classification(
        status=str(page.get("status") or ""),
        pending_review=page.get("pending_review") == "true",
        invalidation_signals=invalidation_signals,
        active_corpus_ids=active_corpus_ids,
    )
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(page)
    return {
        "page_id": str(frontmatter.get("id") or Path(str(page.get("path") or "")).stem),
        "title": str(page.get("title") or frontmatter.get("title") or Path(str(page.get("path") or "")).stem),
        "path": str(page.get("path") or ""),
        "kind": expected_kind,
        "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        "status": str(page.get("status") or ""),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": page.get("pending_review") == "true",
        "overdue_review": page.get("overdue_review") == "true",
        "escalation_candidate": page.get("escalation_candidate") == "true",
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": int(page.get("citation_count", "0") or "0"),
        "citation_drift": page.get("citation_drift") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "confidence": str(page.get("confidence") or ""),
        "formed_at": str(page.get("formed_at") or ""),
        "last_reviewed": str(page.get("last_reviewed") or page.get("reviewed_at") or ""),
        "counter_evidence_count": int(page.get("counter_evidence_count", "0") or "0"),
        "next_signal_count": int(page.get("next_signal_count", "0") or "0"),
        "invalidation_rule": str(page.get("invalidation_rule") or ""),
        "judgment_lifecycle_state": judgment_lifecycle_state,
        "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
    }


def build_concept_lifecycle_entry(
    root: Path,
    path: Path,
    *,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    slug = path.stem
    source_pages = [str(item) for item in frontmatter.get("source_pages", []) if isinstance(item, str) and item.strip()]
    source_ids = entry_ids_from_paths(path_to_entry_id, source_pages)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(
        source_ids,
        active_corpora,
        concept_slug=slug,
    )
    invalidation_signals = concept_lifecycle_invalidation_signals(quality_record)
    review_signals = concept_lifecycle_review_signals(
        quality_record,
        rewrite_proposal,
        active_corpus_ids=active_corpus_ids,
    )
    lifecycle_state, reason_codes = concept_lifecycle_classification(
        source_ids=source_ids,
        active_corpus_ids=active_corpus_ids,
        invalidation_signals=invalidation_signals,
        review_signals=review_signals,
    )
    return {
        "page_id": str(frontmatter.get("id") or f"concept-{slug}"),
        "title": str(frontmatter.get("title") or path.stem),
        "path": relative_path(root, path),
        "kind": "concept",
        "protocol": "",
        "status": str(frontmatter.get("status") or "compiled"),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": "",
        "revisit_after": "",
        "escalate_after": "",
        "aging_state": "",
        "pending_review": bool(review_signals),
        "overdue_review": False,
        "escalation_candidate": False,
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": 0,
        "citation_drift": False,
        "citation_drift_count": 0,
        "citation_snapshot_gap_count": 0,
        "review_history_entries": 0,
        "asset_score": 0,
        "confidence": str(frontmatter.get("confidence") or ""),
        "source_pages": source_pages,
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "quality_state": str(quality_record.get("quality_state") or "stable"),
        "issues": list(quality_record.get("issues") or []),
        "rewrite_priority": str(quality_record.get("rewrite_priority") or "low"),
        "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
        "review_signal_codes": review_signals,
        "rewrite_proposal_status": str(rewrite_proposal.get("status") or ""),
        "rewrite_pending_review": rewrite_proposal.get("pending_review") == "true",
        "rewrite_apply_ready": bool(rewrite_proposal.get("apply_ready")),
        "source_count": int(quality_record.get("source_count") or len(source_pages)),
        "related_count": int(quality_record.get("related_count") or 0),
        "override_active": False,
        "override_state": "",
        "override_reason_codes": [],
        "override_note": "",
        "override_updated_at": "",
        "override_source": "",
    }


def apply_knowledge_lifecycle_override(
    entry: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(entry)
    if not override or not bool(override.get("active")):
        return normalized
    override_state = str(override.get("lifecycle_state") or "")
    if override_state not in KNOWLEDGE_LIFECYCLE_STATES:
        return normalized
    override_reason_codes = [
        str(reason) for reason in override.get("reason_codes", []) if isinstance(reason, str) and reason.strip()
    ]
    normalized["derived_lifecycle_state"] = str(entry.get("lifecycle_state") or "")
    normalized["derived_reason_codes"] = list(entry.get("reason_codes") or [])
    normalized["override_active"] = True
    normalized["override_state"] = override_state
    normalized["override_reason_codes"] = override_reason_codes
    normalized["override_note"] = str(override.get("note") or "")
    normalized["override_updated_at"] = str(override.get("updated_at") or override.get("applied_at") or "")
    normalized["override_source"] = str(override.get("operation") or "manual-runtime")
    normalized["lifecycle_state"] = override_state
    normalized["reason_codes"] = ["manual-override", *(override_reason_codes or [f"manual-{override_state}"])]
    if override_state == "retired":
        normalized["pending_review"] = False
        normalized["overdue_review"] = False
        normalized["escalation_candidate"] = False
    return normalized


def clear_stale_knowledge_lifecycle_overrides(
    root: Path,
    override_state: dict[str, Any],
    *,
    cleared_at: str,
) -> dict[str, Any]:
    current_concept_paths = {relative_path(root, path) for path in sorted((root / "wiki" / "concepts").glob("*.md"))}
    entries: list[dict[str, Any]] = []
    changed = False
    for raw_entry in override_state.get("entries", []):
        if not isinstance(raw_entry, dict):
            continue
        entry = dict(raw_entry)
        path = str(entry.get("path") or "")
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and path.startswith("wiki/concepts/")
            and path not in current_concept_paths
        ):
            entry["active"] = False
            entry["cleared_at"] = cleared_at
            entry["cleared_note"] = "Target concept page no longer exists; cleared by lifecycle refresh."
            entry["cleared_reason_codes"] = ["missing-target"]
            entry["updated_at"] = cleared_at
            changed = True
        entries.append(entry)
    if not changed:
        return override_state
    cleaned_state = {
        "version": int(override_state.get("version", 1) or 1),
        "entries": entries,
    }
    save_knowledge_lifecycle_override_state(root, cleaned_state)
    return cleaned_state


def knowledge_lifecycle_governance_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    concept_counts = knowledge_lifecycle.get("counts", {}).get("by_kind", {}).get("concept", {}).get("by_state", {})
    curated_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"decision", "judgment"},
        ),
        active_protocol=active_protocol,
    )
    formed_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "formed"
    ]
    active_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "active"
    ]
    under_review_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "under-review"
    ]
    revised_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "revised"
    ]
    retired_judgments = [
        entry for entry in curated_entries if str(entry.get("judgment_lifecycle_state") or "") == "retired"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "formed_judgments": formed_judgments,
        "active_judgments": active_judgments,
        "under_review_judgments": under_review_judgments,
        "revised_judgments": revised_judgments,
        "retired_judgments": retired_judgments,
        "counts": {
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": int(concept_counts.get("active", 0) or 0),
            "deferred_concepts": int(concept_counts.get("deferred", 0) or 0),
            "formed_judgments": len(formed_judgments),
            "active_judgments": len(active_judgments),
            "under_review_judgments": len(under_review_judgments),
            "revised_judgments": len(revised_judgments),
            "retired_judgments": len(retired_judgments),
        },
    }


def refresh_knowledge_lifecycle_state(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = build_knowledge_lifecycle_document(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=entries,
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    save_knowledge_lifecycle_state(root, document)
    return document


def build_knowledge_lifecycle_document(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_state = clear_stale_knowledge_lifecycle_overrides(
        root,
        override_state,
        cleared_at=generated_at,
    )
    active_overrides = active_knowledge_lifecycle_overrides(override_state)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    _entry_by_id, path_to_entry_id = entry_lookup_maps(manifest_entries)
    decision_pages = decisions if decisions is not None else collect_curated_pages(root, "decisions", "decision")
    judgment_pages = judgments if judgments is not None else collect_curated_pages(root, "judgments", "judgment")
    concept_memory = memory if memory is not None else load_machine_memory(root)
    concept_quality = (
        build_concept_quality(root, concept_memory)
        if concept_memory
        else {
            "weak_concepts": [],
            "stable_concepts": [],
        }
    )
    concept_quality_by_slug = {
        str(record.get("slug") or ""): dict(record)
        for record in (concept_quality.get("all_concepts", []) or [])
        if isinstance(record, dict) and record.get("slug")
    }
    concept_rewrite_by_slug = {
        str(proposal.get("slug") or ""): dict(proposal)
        for proposal in load_concept_rewrite_state(root).get("proposals", [])
        if isinstance(proposal, dict) and proposal.get("slug")
    }
    active_corpora = [
        dict(corpus)
        for corpus in (active_corpora_state or load_active_corpora_state(root)).get("corpora", [])
        if isinstance(corpus, dict)
    ]
    lifecycle_entries = [
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="decision",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in decision_pages
        ],
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="judgment",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in judgment_pages
        ],
        *[
            build_concept_lifecycle_entry(
                root,
                path,
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
                quality_record=concept_quality_by_slug.get(
                    path.stem,
                    {
                        "slug": path.stem,
                        "quality_state": "stable",
                        "issues": [],
                        "rewrite_priority": "low",
                        "rewrite_strategy": "",
                        "source_count": 0,
                        "related_count": 0,
                    },
                ),
                rewrite_proposal=concept_rewrite_by_slug.get(path.stem, {}),
            )
            for path in sorted((root / "wiki" / "concepts").glob("*.md"))
        ],
    ]
    lifecycle_entries = [
        apply_knowledge_lifecycle_override(entry, active_overrides.get(str(entry.get("path") or "")))
        if str(entry.get("kind") or "") == "concept"
        else entry
        for entry in lifecycle_entries
    ]
    document = {
        "version": 1,
        "generated_at": generated_at,
        "entries": lifecycle_entries,
        "counts": knowledge_lifecycle_counts(lifecycle_entries),
    }
    return document
