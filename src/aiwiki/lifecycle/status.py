"""Pure lifecycle status and transition helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..content.io import curated_asset_section_snapshot, review_history_entries
from ..protocol.focus_scoring import page_focus_score
from ..protocol.review_windows import schedule_review_windows
from ..protocol.runtime_config import (
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
    PENDING_ACTION_STATUSES,
    PENDING_DECISION_REVIEW_STATUSES,
    PENDING_JUDGMENT_REVIEW_STATUSES,
)
from ..protocol.templates import CURATED_ASSET_SECTION_ORDER
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.markdown import analyze_citation_snapshots, frontmatter_string_list, parse_frontmatter
from ..utils.path import relative_path
from ..utils.time import utc_now
from .aging import evaluate_page_aging
from .types import JudgmentAsset

THIN_REVIEW_TRANSITIONS = ("pending-review", "confirmed", "discarded")

_PENDING_CURATED_STATUSES = frozenset({"proposed", "needs-revisit", "tentative", "tracking"})
_CONFIRMED_CURATED_STATUSES = frozenset({"approved", "confirmed"})
_DISCARDED_CURATED_STATUSES = frozenset({"superseded", "rejected"})


def default_curated_status(kind: str) -> str:
    if kind == "decision":
        return "proposed"
    if kind == "judgment":
        return "tentative"
    return "filed"


def valid_curated_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return DECISION_STATUSES
    if kind == "judgment":
        return JUDGMENT_STATUSES
    return ()


def page_needs_review(kind: str, status: str) -> bool:
    if kind == "decision":
        return status in PENDING_DECISION_REVIEW_STATUSES
    if kind == "judgment":
        return status in PENDING_JUDGMENT_REVIEW_STATUSES
    return False


def thin_curated_status_group(status: str) -> str:
    normalized = str(status or "").strip()
    if normalized in _PENDING_CURATED_STATUSES:
        return "pending-review"
    if normalized in _CONFIRMED_CURATED_STATUSES:
        return "confirmed"
    if normalized in _DISCARDED_CURATED_STATUSES:
        return "discarded"
    return normalized


def display_curated_status(status: str) -> str:
    thin = thin_curated_status_group(status)
    mapping = {
        "pending-review": "待审",
        "confirmed": "已确认",
        "discarded": "废弃",
        "filed": "已归档",
    }
    if thin in mapping:
        return mapping[thin]
    return status or "unknown"


def resolve_thin_review_transition(kind: str, current_status: str, transition: str) -> str:
    """Map thin review transition tokens (or legacy canonical statuses) to curated status."""
    normalized_kind = str(kind or "").strip()
    normalized_transition = str(transition or "").strip()
    normalized_current = str(current_status or "").strip()
    valid_statuses = valid_curated_statuses(normalized_kind)
    if normalized_transition in valid_statuses:
        return normalized_transition
    if normalized_kind == "decision":
        resolved = {
            "pending-review": "needs-revisit",
            "confirmed": "approved",
            "discarded": "superseded",
        }.get(normalized_transition)
    elif normalized_kind == "judgment":
        resolved = {
            "pending-review": "tracking",
            "confirmed": "confirmed",
            "discarded": "rejected",
        }.get(normalized_transition)
    else:
        resolved = None
    if not resolved or resolved not in valid_statuses:
        thin_hint = ", ".join(THIN_REVIEW_TRANSITIONS)
        canonical_hint = ", ".join(valid_statuses)
        raise ValueError(
            f"Unsupported review transition for {normalized_kind}: {normalized_transition!r}; "
            f"expected one of: ({thin_hint}) or canonical ({canonical_hint}) "
            f"from current status {normalized_current!r}"
        )
    allowed = curated_page_transition_profile(normalized_kind, normalized_current).get("allowed_transitions", [])
    thin_token = normalized_transition if normalized_transition in THIN_REVIEW_TRANSITIONS else None
    if thin_token and thin_token not in allowed:
        raise ValueError(
            f"Review transition {normalized_transition!r} is not allowed from current status "
            f"{normalized_current!r} for {normalized_kind} pages."
        )
    return resolved


def action_needs_review(status: str) -> bool:
    return status in PENDING_ACTION_STATUSES


def display_action_status(status: str) -> str:
    mapping = {
        "proposed": "待处理",
        "accepted": "已接受",
        "deferred": "暂缓",
        "resolved": "已解决",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def transition_profile(
    allowed_transitions: list[str],
    *,
    preferred_transitions: list[str] | None = None,
    default_transition: str = "",
) -> dict[str, Any]:
    allowed = [str(item).strip() for item in allowed_transitions if str(item).strip()]
    preferred = [str(item).strip() for item in (preferred_transitions or []) if str(item).strip() in allowed]
    default_value = str(default_transition or "").strip()
    if default_value not in allowed:
        default_value = preferred[0] if preferred else (allowed[0] if allowed else "")
    return {
        "allowed_transitions": allowed,
        "preferred_transitions": preferred,
        "default_transition": default_value,
    }


def curated_page_transition_profile(kind: str, status: str) -> dict[str, Any]:
    normalized_kind = str(kind or "").strip()
    normalized_status = str(status or "").strip()
    if normalized_kind not in {"decision", "judgment"}:
        return transition_profile([])

    confirmed_status = "approved" if normalized_kind == "decision" else "confirmed"
    discarded_status = "superseded" if normalized_kind == "decision" else "rejected"
    pending_statuses = {"proposed", "needs-revisit"} if normalized_kind == "decision" else {"tentative", "tracking"}

    if normalized_status == discarded_status:
        return transition_profile([])

    allowed: list[str] = []
    preferred: list[str] = []
    default_transition = ""

    if normalized_status != confirmed_status:
        allowed.append("confirmed")
        preferred.append("confirmed")
        default_transition = "confirmed"

    allowed.append("discarded")

    if normalized_status not in pending_statuses:
        allowed.append("pending-review")
        if not default_transition:
            default_transition = "pending-review"

    return transition_profile(
        allowed,
        preferred_transitions=preferred,
        default_transition=default_transition,
    )


def action_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["resolved", "deferred", "rejected"],
            preferred_transitions=["resolved", "deferred"],
            default_transition="resolved",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "resolved", "rejected"],
            preferred_transitions=["accepted", "resolved"],
            default_transition="accepted",
        )
    return transition_profile([])


def archive_transition_profile(*, can_apply: bool, can_revert: bool) -> dict[str, Any]:
    if can_apply:
        return transition_profile(["apply"], preferred_transitions=["apply"], default_transition="apply")
    if can_revert:
        return transition_profile(["revert"], preferred_transitions=["revert"], default_transition="revert")
    return transition_profile([])


def sort_curated_pages(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(page: dict[str, str]) -> tuple[str, str]:
        return (page.get("reviewed_at", "") or page.get("updated_at", ""), page["title"].lower())

    return sorted(pages, key=sort_key, reverse=True)


def judgment_asset_frontmatter(
    *,
    frontmatter: dict[str, Any],
    page_id: str,
    title: str,
    path: str,
    kind: str,
    status: str,
    protocol: str,
    citations: list[str],
    revisit_after: str,
    escalate_after: str,
    content: str = "",
    root: Path | None = None,
) -> JudgmentAsset:
    from .templates import curated_body_structured_fields

    body_fields = (
        curated_body_structured_fields(root=root, content=content, frontmatter=frontmatter) if content else {}
    )
    counter_evidence = frontmatter_string_list(frontmatter, "counter_evidence") or list(
        body_fields.get("counter_evidence") or []
    )
    invalidation_rule = str(frontmatter.get("invalidation_rule") or body_fields.get("invalidation_rule") or "").strip()
    next_signals = frontmatter_string_list(frontmatter, "next_signals") or list(body_fields.get("next_signals") or [])
    return {
        "page_id": page_id,
        "title": title,
        "path": path,
        "kind": kind,
        "status": status,
        "protocol": protocol,
        "citations": citations,
        "confidence": str(frontmatter.get("confidence") or ""),
        "counter_evidence": counter_evidence,
        "invalidation_rule": invalidation_rule,
        "next_signals": next_signals,
        "revisit_after": revisit_after,
        "escalate_after": escalate_after,
        "formed_at": str(frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or ""),
        "last_reviewed": str(frontmatter.get("last_reviewed") or frontmatter.get("reviewed_at") or ""),
    }


def collect_curated_pages(root: Path, folder: str, expected_kind: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        status = str(frontmatter.get("status") or default_curated_status(expected_kind))
        reviewed_at = str(frontmatter.get("reviewed_at") or "")
        updated_at = str(frontmatter.get("last_compiled_at") or "")
        protocol = str(frontmatter.get("protocol") or DEFAULT_PROTOCOL)
        revisit_after = str(frontmatter.get("revisit_after") or "")
        escalate_after = str(frontmatter.get("escalate_after") or "")
        if not revisit_after and not escalate_after:
            base_timestamp = reviewed_at or updated_at or utc_now()
            revisit_after, escalate_after = schedule_review_windows(
                expected_kind,
                status,
                base_timestamp,
                protocol=protocol,
                root=root,
            )
        asset_snapshots = {
            heading: curated_asset_section_snapshot(
                content,
                heading,
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            )
            for heading in CURATED_ASSET_SECTION_ORDER
        }
        citations = [str(path) for path in frontmatter.get("citations", []) if isinstance(path, str) and path.strip()]
        asset_frontmatter = judgment_asset_frontmatter(
            frontmatter=frontmatter,
            page_id=str(frontmatter.get("id") or path.stem),
            title=str(frontmatter.get("title") or path.stem),
            path=relative_path(root, path),
            kind=str(frontmatter.get("kind") or ""),
            status=status,
            protocol=protocol,
            citations=citations,
            revisit_after=revisit_after,
            escalate_after=escalate_after,
            content=content,
            root=root,
        )
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        review_entries = review_history_entries(content)
        asset_score = sum(1 for snapshot in asset_snapshots.values() if snapshot.get("meaningful"))
        pages.append(
            {
                "page_id": str(frontmatter.get("id") or path.stem),
                "title": str(frontmatter.get("title") or path.stem),
                "path": relative_path(root, path),
                "kind": str(frontmatter.get("kind") or ""),
                "status": status,
                "protocol": protocol,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "updated_at": updated_at,
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
                "matches_expected_kind": str(frontmatter.get("kind") or "") == expected_kind,
                "pending_review": "true" if page_needs_review(expected_kind, status) else "false",
                "asset_score": str(asset_score),
                "has_counter_evidence": "true" if asset_snapshots["Counter Evidence"]["meaningful"] else "false",
                "has_invalidation": "true" if asset_snapshots["Invalidation"]["meaningful"] else "false",
                "has_next_signals": "true" if asset_snapshots["Next Signals"]["meaningful"] else "false",
                "has_review_history": "true" if asset_snapshots["Review History"]["meaningful"] else "false",
                "review_history_entries": str(asset_snapshots["Review History"]["review_history_entries"]),
                "latest_review_history_entry": review_entries[0] if review_entries else "",
                "citation_count": str(len(citations)),
                "citation_snapshot_count": str(len(citation_snapshot_state["recorded"])),
                "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
                "citation_drift_count": str(len(citation_snapshot_state["drifted"])),
                "citation_snapshot_gap_count": str(
                    len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
                ),
                "formed_at": str(asset_frontmatter.get("formed_at") or ""),
                "last_reviewed": str(asset_frontmatter.get("last_reviewed") or ""),
                "counter_evidence_count": str(len(asset_frontmatter.get("counter_evidence", []))),
                "next_signal_count": str(len(asset_frontmatter.get("next_signals", []))),
                "invalidation_rule": str(asset_frontmatter.get("invalidation_rule") or ""),
                "has_counter_evidence_metadata": "true" if "counter_evidence" in frontmatter else "false",
                "has_invalidation_rule_metadata": "true" if "invalidation_rule" in frontmatter else "false",
                "has_next_signals_metadata": "true" if "next_signals" in frontmatter else "false",
                "has_formed_at_metadata": "true" if "formed_at" in frontmatter else "false",
                "has_last_reviewed_metadata": "true" if "last_reviewed" in frontmatter else "false",
                "has_structured_counter_evidence": "true" if asset_frontmatter.get("counter_evidence") else "false",
                "has_structured_invalidation_rule": "true"
                if str(asset_frontmatter.get("invalidation_rule") or "").strip()
                else "false",
                "has_structured_next_signals": "true" if asset_frontmatter.get("next_signals") else "false",
            }
        )
    enriched: list[dict[str, str]] = []
    for page in pages:
        enriched_page = dict(page)
        enriched_page.update(evaluate_page_aging(enriched_page, now=now))
        enriched.append(enriched_page)
    return sort_curated_pages(enriched)


def review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pending_decisions = sorted(
        [page for page in decisions if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    pending_judgments = sorted(
        [page for page in judgments if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    reviewed = [
        page for page in decisions + judgments if page.get("reviewed_at") and page.get("pending_review") != "true"
    ]
    reviewed = sorted(reviewed, key=lambda page: (page.get("reviewed_at", ""), page["title"].lower()), reverse=True)
    return {
        "pending_decisions": pending_decisions,
        "pending_judgments": pending_judgments,
        "recently_reviewed": reviewed,
    }
