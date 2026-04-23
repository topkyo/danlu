"""Output-pack helpers, builders, index renderer, and protocol pack rows.

Extracted from aiwiki.app_render (EP-017A step 2). Owns:

- compact_section_lines / workspace_link / pack_workspace_link
- load_workspace_markdown / workspace_file_signature
- output_pack_* candidate + signature + reuse helpers
- build_output_pack_review_packs / build_output_pack_decision_memos /
  build_output_pack_sop_drafts
- output_pack_version_history_lines
- decision_memo_section_lines / decision_memo_recommendation_lines
- sop_pattern_key / extract_sop_pattern_frequencies
- build_output_packs / build_output_packs_incremental
- render_output_packs_index
- protocol_output_pack_rows

External callers should keep importing via aiwiki.app_render facade to
preserve the B2/B5/B6/B7 true-origin convention; direct imports from
aiwiki.render.packs are also valid for new code.

Lazy import discipline (EP-017A step 0 root-cause fix for the
``app_render <-> app_content`` module-load cycle): the three symbols
``preserved_section`` / ``action_supports_low_risk_apply`` /
``execution_band_label`` come from aiwiki.app_content, which itself
mass re-exports from aiwiki.app_render. They are imported lazily inside
the call sites to keep this module's import footprint cycle-free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_lifecycle import (
    display_action_status,
    display_curated_status,
    frontmatter_string_list,
    knowledge_lifecycle_governance_summary,
    render_knowledge_lifecycle_entry_summary,
    sort_curated_pages,
)
from ..app_protocol import PROTOCOL_LIBRARY, page_focus_score, protocol_title
from ..app_state import DEFAULT_PROTOCOL, load_output_pack_build_state
from ..app_utils import (
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    sha256_bytes,
    sha256_file,
)
from .paths import (
    decision_memo_path,
    execution_bundle_path,
    review_pack_path,
    sop_draft_path,
)


def compact_section_lines(markdown: str, heading: str, *, fallback: str, limit: int = 5) -> list[str]:
    from ..app_content import preserved_section

    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return [fallback]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return [fallback]
    if len(lines) > limit:
        return [*lines[:limit], "- ..."]
    return lines


def workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../{target})"


def pack_workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../../{target})"


def load_workspace_markdown(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = root / relative
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_frontmatter(content), content


def workspace_file_signature(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists() or not path.is_file():
        return ""
    return sha256_file(path)


def output_pack_review_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str,
) -> list[dict[str, str]]:
    pages = decisions + judgments
    return sorted(
        [
            page
            for page in pages
            if page.get("pending_review") == "true"
            or page.get("citation_drift") == "true"
            or page.get("overdue_review") == "true"
            or page.get("escalation_candidate") == "true"
        ],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            0 if page.get("citation_drift") == "true" else 1,
            0 if page.get("pending_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )


def output_pack_reviewed_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> list[dict[str, str]]:
    return sort_curated_pages([page for page in decisions + judgments if page.get("reviewed_at") and page.get("pending_review") != "true"])


def output_pack_repair_plan_candidates(memory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action for action in repair_plan.get("ready_actions", []) if isinstance(action, dict) and action.get("active")
    ]
    execution_proposals = [
        proposal for proposal in repair_plan.get("execution_proposals", []) if isinstance(proposal, dict)
    ]
    return ready_actions, execution_proposals


def output_pack_state_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in record.items() if key != "content"} for record in records if isinstance(record, dict)]


def output_pack_group_is_reusable(root: Path, records: list[dict[str, Any]]) -> bool:
    for record in records:
        path = str(record.get("path") or "")
        if not path:
            return False
        if not (root / path).exists():
            return False
    return True


def output_pack_lifecycle_summary_input_signature(lifecycle_summary: dict[str, Any], *, active_protocol: str) -> str:
    payload = {
        "active_protocol": active_protocol,
        "lifecycle_summary": lifecycle_summary,
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_review_group_input_signature(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "review_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "citation_drift": str(page.get("citation_drift") or ""),
                "citation_snapshot_gap_count": str(page.get("citation_snapshot_gap_count", "") or ""),
                "revisit_after": str(page.get("revisit_after") or ""),
                "escalate_after": str(page.get("escalate_after") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in review_candidates
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_decision_memo_group_input_signature(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "reviewed_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
                "confidence": str(page.get("confidence") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in reviewed_candidates
        ],
        "recent_outputs": [
            {
                "path": str(artifact.get("path") or ""),
                "title": str(artifact.get("title") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or ""),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs[:5]
            if isinstance(artifact, dict)
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_sop_group_input_signature(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
) -> str:
    from ..app_content import action_supports_low_risk_apply

    payload = {
        "active_protocol": active_protocol,
        "execution_proposals": [
            {
                "action_id": str(proposal.get("action_id") or ""),
                "title": str(proposal.get("title") or ""),
                "risk": str(proposal.get("risk") or ""),
                "proposal_kind": str(proposal.get("proposal_kind") or ""),
                "protocol": str(proposal.get("protocol") or ""),
                "summary": str(proposal.get("summary") or ""),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "bundle_path": str(proposal.get("bundle_path") or ""),
                "target_paths": list(proposal.get("target_paths", []) or []),
                "page_patch_plan": list(proposal.get("page_patch_plan", []) or []),
                "suggested_edits": list(proposal.get("suggested_edits", []) or []),
            }
            for proposal in execution_proposals
        ],
        "ready_actions": [
            {
                "id": str(action.get("id") or ""),
                "title": str(action.get("title") or ""),
                "status": str(action.get("status") or ""),
                "priority": str(action.get("priority") or ""),
                "protocol": str(action.get("protocol") or ""),
                "execution_band": str(action.get("execution_band") or ""),
                "primary_path": str(action.get("primary_path") or ""),
                "secondary_path": str(action.get("secondary_path") or ""),
                "reason": str(action.get("reason") or ""),
                "next_step": str(action.get("next_step") or ""),
                "command_hint": str(action.get("command_hint") or ""),
                "active": bool(action.get("active")),
                "bundle_exists": execution_bundle_path(root, str(action.get("id") or "")).exists(),
                "low_risk_apply": action_supports_low_risk_apply(action),
            }
            for action in ready_actions
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_output_pack_review_packs(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    review_packs: list[dict[str, Any]] = []
    for page in review_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        reasons: list[str] = []
        if page.get("pending_review") == "true":
            reasons.append("pending review")
        if page.get("overdue_review") == "true":
            reasons.append("overdue review")
        if page.get("escalation_candidate") == "true":
            reasons.append("escalation candidate")
        if page.get("citation_drift") == "true":
            reasons.append("citation drift")
        if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
            reasons.append("citation snapshot gap")
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = review_pack_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"review-pack-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "review-pack",
                "title": f"Review Pack · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# Review Pack · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Kind: `{kind}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Review reasons: `{', '.join(reasons) or 'manual review'}`",
            f"- Revisit / Escalate: `{page.get('revisit_after', '') or 'none'}` / `{page.get('escalate_after', '') or 'none'}`",
            "",
            f"## Current {section_name}",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。"),
            "",
            f"## {evidence_section} Snapshot",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据快照。"),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence."),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions."),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet."),
            "",
            "## Review Checklist",
            *[f"- {line}" for line in PROTOCOL_LIBRARY.get(protocol, {}).get("review", [])],
            "",
            "## Commands",
            f"- `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page['path']} --status "
            f"{'approved' if kind == 'decision' else 'confirmed'} --note \"Review pack follow-up.\"`",
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [审阅队列](../../../wiki/indexes/review-queue.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
            ]
        )
        review_packs.append(
            {
                "title": f"Review Pack · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reasons": ", ".join(reasons) or "manual review",
            }
        )
    return review_packs


def output_pack_version_history_lines(
    root: Path,
    destination: Path,
    *,
    compiled_at: str,
    entry_summary: str,
    limit: int = 5,
) -> list[str]:
    history_lines = [f"- `{compiled_at}` | {entry_summary}"]
    relative = relative_path(root, destination)
    if destination.exists():
        _, existing_content = load_workspace_markdown(root, relative)
        for line in compact_section_lines(existing_content, "Version History", fallback="", limit=limit):
            normalized = str(line).strip()
            if not normalized or normalized == "- ...":
                continue
            if normalized not in history_lines:
                history_lines.append(normalized)
    return history_lines[:limit]


def decision_memo_section_lines(
    content: str,
    frontmatter: dict[str, Any],
    heading: str,
    *,
    structured_values: list[str] | None = None,
    structured_scalar: str = "",
    fallback: str,
    limit: int = 5,
) -> list[str]:
    section_lines = compact_section_lines(content, heading, fallback="", limit=limit)
    normalized = [line for line in section_lines if str(line).strip()]
    if normalized and normalized != [fallback]:
        return normalized
    if structured_values:
        return [f"- {value}" for value in structured_values[:limit]]
    if structured_scalar:
        return [f"- {structured_scalar}"]
    return [fallback]


def decision_memo_recommendation_lines(page: dict[str, str], frontmatter: dict[str, Any]) -> list[str]:
    status = str(page.get("status") or frontmatter.get("status") or "")
    confidence = str(frontmatter.get("confidence") or page.get("confidence") or "unknown")
    counter_evidence = frontmatter_string_list(frontmatter, "counter_evidence")
    next_signals = frontmatter_string_list(frontmatter, "next_signals")
    if status in {"approved", "confirmed"} and confidence == "high" and not counter_evidence:
        lines = ["- 当前可以把这份 memo 当作工作基线，进入执行或持续跟踪。"]
    elif counter_evidence or status in {"tracking", "needs-revisit"}:
        lines = ["- 当前应保持谨慎，把它视为待复核立场，而不是最终结论。"]
    else:
        lines = ["- 当前可以作为候选立场流转，但执行前还应补一次人工复核。"]
    if next_signals:
        lines.append(f"- 下一次优先验证：`{next_signals[0]}`。")
    return lines


def build_output_pack_decision_memos(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    decision_memos: list[dict[str, Any]] = []
    for page in reviewed_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        memo_label = "Decision Memo" if kind == "decision" else "Judgment Memo"
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = decision_memo_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        counter_evidence_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Counter Evidence",
            structured_values=frontmatter_string_list(frontmatter, "counter_evidence"),
            fallback="- Pending counter evidence.",
            limit=5,
        )
        invalidation_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Invalidation",
            structured_scalar=str(frontmatter.get("invalidation_rule") or "").strip(),
            fallback="- Pending invalidation conditions.",
            limit=5,
        )
        next_signal_lines = decision_memo_section_lines(
            content,
            frontmatter,
            "Next Signals",
            structured_values=frontmatter_string_list(frontmatter, "next_signals"),
            fallback="- Pending next signals.",
            limit=5,
        )
        recommendation_lines = decision_memo_recommendation_lines(page, frontmatter)
        frontmatter_text = render_frontmatter(
            {
                "id": f"decision-memo-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "decision-memo",
                "title": f"{memo_label} · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"], *citations],
                "citations": citations,
                "judgment_asset_path": page["path"],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# {memo_label} · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Reviewed at: `{page.get('reviewed_at', '') or 'unknown'}`",
            f"- Confidence: `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            "",
            "## Executive Summary",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。", limit=6),
            "",
            f"## {evidence_section}",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据。", limit=6),
            "",
            "## Recommendation",
            *recommendation_lines,
            "",
            "## Counter Evidence",
            *counter_evidence_lines,
            "",
            "## Invalidation",
            *invalidation_lines,
            "",
            "## Next Signals",
            *next_signal_lines,
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet.", limit=6),
            "",
            "## Version History",
            *output_pack_version_history_lines(
                root,
                destination,
                compiled_at=compiled_at,
                entry_summary=f"status `{page.get('status', 'unknown')}` | confidence `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            ),
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        if recent_outputs:
            lines.extend(["", "## Nearby Recent Outputs"])
            for artifact in recent_outputs[:5]:
                lines.append(
                    f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                    f" | format `{artifact['format'] or 'unknown'}`"
                    f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                )
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [判断资产](../../../wiki/indexes/judgment-assets.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
            ]
        )
        decision_memos.append(
            {
                "title": f"{memo_label} · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reviewed_at": page.get("reviewed_at", "") or "",
            }
        )
    return decision_memos


def sop_pattern_key(record: dict[str, Any]) -> str:
    proposal_kind = str(record.get("proposal_kind") or record.get("kind") or "manual-repair")
    risk = str(record.get("risk") or "")
    protocol = str(record.get("protocol") or DEFAULT_PROTOCOL)
    return "|".join(part for part in (proposal_kind, risk, protocol) if part)


def extract_sop_pattern_frequencies(
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
) -> dict[str, int]:
    pattern_counts: dict[str, int] = {}
    for proposal in execution_proposals:
        key = sop_pattern_key(proposal)
        if key:
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    for action in ready_actions:
        key = sop_pattern_key(action)
        if key:
            pattern_counts[key] = pattern_counts.get(key, 0) + 1
    return pattern_counts


def build_output_pack_sop_drafts(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> tuple[list[dict[str, Any]], int]:
    from ..app_content import action_supports_low_risk_apply, execution_band_label

    sop_drafts: list[dict[str, Any]] = []
    proposal_by_action = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in execution_proposals
        if proposal.get("action_id")
    }
    pattern_frequencies = extract_sop_pattern_frequencies(ready_actions, execution_proposals)
    proposal_count = 0
    for proposal in execution_proposals:
        action_id = str(proposal.get("action_id") or "").strip()
        if not action_id:
            continue
        destination = sop_draft_path(root, action_id)
        protocol = str(proposal.get("protocol") or active_protocol)
        pattern_key = sop_pattern_key(proposal)
        pattern_frequency = int(pattern_frequencies.get(pattern_key, 0))
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "protocol": protocol,
                "action_id": action_id,
                "source_files": [str(proposal.get("proposal_path") or "")],
                "pattern_key": pattern_key,
                "pattern_frequency": pattern_frequency,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        patch_plan = proposal.get("page_patch_plan", [])
        bundle_path = str(proposal.get("bundle_path") or "")
        safe_preview = proposal.get("safe_apply_preview") if isinstance(proposal.get("safe_apply_preview"), dict) else {}
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {proposal.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Risk: `{proposal.get('risk', 'medium')}`",
            f"- Proposal kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
            f"- Bundle: `{bundle_path or 'none'}`",
            f"- Pattern frequency: `{pattern_frequency}`",
            "",
            "## Strategy",
            f"- {proposal.get('summary', '检查目标页面并确认是否执行。')}",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.append(
                f"2. 如果 dry-run 结果符合预期，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。"
            )
        else:
            lines.append("2. 当前没有 bundle，先回到 execution proposal 页面确认执行边界。")
        lines.append(
            f"3. 如需回滚，执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}`。"
        )
        lines.extend(["", "## Page-Level Patch Plan"])
        if not patch_plan:
            lines.append("- 当前没有页级 patch step。")
        else:
            for patch in patch_plan:
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
        lines.extend(["", "## Suggested Edits"])
        edits = proposal.get("suggested_edits", [])
        if not edits:
            lines.append("- 当前没有额外建议。")
        else:
            lines.extend(f"- {edit}" for edit in edits[:8])
        lines.extend(["", "## Dry Run Preview"])
        if not safe_preview:
            lines.append("- 当前没有额外 dry-run preview。")
        else:
            lines.append(f"- Apply mode: `{safe_preview.get('apply_mode', 'dry-run')}`")
            lines.append(f"- Bundle path: `{safe_preview.get('bundle_path', '') or 'none'}`")
            lines.extend(
                f"- {step}"
                for step in safe_preview.get("steps", [])[:6]
                if isinstance(step, str) and step.strip()
            )
        lines.extend(
            [
                "",
                "## Version History",
                *output_pack_version_history_lines(
                    root,
                    destination,
                    compiled_at=compiled_at,
                    entry_summary=f"pattern `{pattern_key or 'manual-repair'}` | frequency `{pattern_frequency}`",
                ),
                "",
                "## Related Links",
                f"- {pack_workspace_link(str(proposal.get('proposal_path') or ''), 'Execution Proposal')}" if proposal.get("proposal_path") else "- Execution Proposal: none",
                f"- {pack_workspace_link(bundle_path, 'Execution Bundle')}" if bundle_path else "- Execution Bundle: none",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆修复计划](../../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": protocol,
                "risk": str(proposal.get("risk") or "medium"),
            }
        )
        proposal_count += 1

    for action in ready_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in proposal_by_action:
            continue
        destination = sop_draft_path(root, action_id)
        band = str(action.get("execution_band") or "review-first")
        action_protocol = str(action.get("protocol") or active_protocol)
        pattern_key = sop_pattern_key(action)
        pattern_frequency = int(pattern_frequencies.get(pattern_key, 0))
        bundle_absolute = execution_bundle_path(root, action_id)
        bundle_relative = relative_path(root, bundle_absolute)
        bundle_path = bundle_relative if bundle_absolute.exists() else ""
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "protocol": action_protocol,
                "action_id": action_id,
                "source_files": [str(action.get("primary_path") or "")],
                "pattern_key": pattern_key,
                "pattern_frequency": pattern_frequency,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {action.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Status: `{display_action_status(str(action.get('status') or 'proposed'))}`",
            f"- Priority: `{action.get('priority', 'medium')}`",
            f"- Protocol: `{action_protocol}` ({protocol_title(action_protocol)})",
            f"- Execution band: `{band}` ({execution_band_label(band)})",
            f"- Primary / Secondary: `{action.get('primary_path', '')}` / `{action.get('secondary_path', '') or 'none'}`",
            f"- Pattern frequency: `{pattern_frequency}`",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.extend(
                [
                    f"2. 如果执行 band 仍允许，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。",
                    f"3. 必要时用 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}` 回滚。",
                ]
            )
            bundle_link = f"- [Execution Bundle](../../../{bundle_path})"
        else:
            lines.extend(
                [
                    "2. 当前还没有稳定 bundle；先停在 dry-run，或回到 execution proposal 层生成 bundle。",
                    "3. 生成 bundle 后再执行真实 apply。",
                ]
            )
            bundle_link = "- Execution Bundle: none"
        lines.extend(
            [
                "",
                "## Action Notes",
                f"- Reason: {action.get('reason', 'n/a')}",
                f"- Next step: {action.get('next_step', 'n/a')}",
                f"- Command hint: `{action.get('command_hint', '') or 'none'}`",
                "",
                "## Version History",
                *output_pack_version_history_lines(
                    root,
                    destination,
                    compiled_at=compiled_at,
                    entry_summary=f"pattern `{pattern_key or band}` | frequency `{pattern_frequency}`",
                ),
                "",
                "## Related Links",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆动作队列](../../../wiki/indexes/machine-memory-actions.md)",
                bundle_link,
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": action_protocol,
                "risk": "low" if action_supports_low_risk_apply(action) else "medium",
            }
        )
    return sop_drafts, proposal_count


def build_output_packs(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    review_packs = build_output_pack_review_packs(
        root,
        review_candidates,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    decision_memos = build_output_pack_decision_memos(
        root,
        reviewed_candidates,
        recent_outputs,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    sop_drafts, proposal_count = build_output_pack_sop_drafts(
        root,
        ready_actions,
        execution_proposals,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }


def build_output_packs_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    previous_state = load_output_pack_build_state(root)
    previous_group_records = previous_state.get("group_records", {})
    signatures = {
        "lifecycle_summary": output_pack_lifecycle_summary_input_signature(
            lifecycle_summary,
            active_protocol=active_protocol,
        ),
        "review_packs": output_pack_review_group_input_signature(
            root,
            review_candidates,
            active_protocol=active_protocol,
        ),
        "decision_memos": output_pack_decision_memo_group_input_signature(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
        ),
        "sop_drafts": output_pack_sop_group_input_signature(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
        ),
    }
    dirty_groups: list[str] = []
    clean_groups: list[str] = []
    review_packs: list[dict[str, Any]]
    decision_memos: list[dict[str, Any]]
    sop_drafts: list[dict[str, Any]]

    lifecycle_reusable = (
        isinstance(previous_group_records.get("lifecycle_summary"), dict)
        and str(previous_group_records["lifecycle_summary"].get("input_signature") or "") == signatures["lifecycle_summary"]
    )
    if lifecycle_reusable:
        clean_groups.append("lifecycle_summary")
    else:
        dirty_groups.append("lifecycle_summary")

    previous_review_packs = previous_state.get("review_packs", [])
    review_reusable = (
        isinstance(previous_group_records.get("review_packs"), dict)
        and str(previous_group_records["review_packs"].get("input_signature") or "") == signatures["review_packs"]
        and output_pack_group_is_reusable(root, previous_review_packs)
    )
    if review_reusable:
        review_packs = [dict(record) for record in previous_review_packs]
        clean_groups.append("review_packs")
    else:
        review_packs = build_output_pack_review_packs(
            root,
            review_candidates,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("review_packs")

    previous_decision_memos = previous_state.get("decision_memos", [])
    memo_reusable = (
        isinstance(previous_group_records.get("decision_memos"), dict)
        and str(previous_group_records["decision_memos"].get("input_signature") or "") == signatures["decision_memos"]
        and output_pack_group_is_reusable(root, previous_decision_memos)
    )
    if memo_reusable:
        decision_memos = [dict(record) for record in previous_decision_memos]
        clean_groups.append("decision_memos")
    else:
        decision_memos = build_output_pack_decision_memos(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("decision_memos")

    previous_sop_drafts = previous_state.get("sop_drafts", [])
    sop_reusable = (
        isinstance(previous_group_records.get("sop_drafts"), dict)
        and str(previous_group_records["sop_drafts"].get("input_signature") or "") == signatures["sop_drafts"]
        and output_pack_group_is_reusable(root, previous_sop_drafts)
    )
    if sop_reusable:
        sop_drafts = [dict(record) for record in previous_sop_drafts]
        clean_groups.append("sop_drafts")
        proposal_count = int(previous_state.get("counts", {}).get("execution_proposal_sops", 0) or 0)
    else:
        sop_drafts, proposal_count = build_output_pack_sop_drafts(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("sop_drafts")

    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    output_packs = {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }
    state_document = {
        "version": 1,
        "generated_at": compiled_at,
        "active_protocol": active_protocol,
        "group_records": {
            group: {"input_signature": signature}
            for group, signature in signatures.items()
        },
        "lifecycle_summary": lifecycle_summary,
        "review_packs": output_pack_state_records(review_packs),
        "decision_memos": output_pack_state_records(decision_memos),
        "sop_drafts": output_pack_state_records(sop_drafts),
        "counts": counts,
    }
    return {
        "output_packs": output_packs,
        "state_document": state_document,
        "dirty_groups": dirty_groups,
        "clean_groups": clean_groups,
    }


def render_output_packs_index(output_packs: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    review_packs = output_packs.get("review_packs", [])
    decision_memos = output_packs.get("decision_memos", [])
    sop_drafts = output_packs.get("sop_drafts", [])
    lifecycle_summary = output_packs.get("lifecycle_summary", {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    counts = output_packs.get("counts", {})
    lines = [
        "# 输出 Pack 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Review packs：`{counts.get('review_packs', len(review_packs))}`",
        f"- Decision memos：`{counts.get('decision_memos', len(decision_memos))}`",
        f"- SOP drafts：`{counts.get('sop_drafts', len(sop_drafts))}`",
        f"- lifecycle concept backlog：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## Pack 目录",
        "- `output/packs/review/`：待审 / 漂移 / aging 页面",
        "- `output/packs/decision-memos/`：已审 decision / judgment",
        "- `output/packs/sop-drafts/`：ready action / execution proposal",
        "",
        "## Lifecycle Governance Summary",
        f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
        "",
        "## Lifecycle Concept Backlog",
    ]
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
        "## Review Packs",
        ]
    )
    if not review_packs:
        lines.append("- 当前没有 review packs。")
    else:
        for pack in review_packs[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reasons `{pack.get('reasons', 'manual review')}`"
            )
    lines.extend(["", "## Decision Memos"])
    if not decision_memos:
        lines.append("- 当前没有 decision memos。")
    else:
        for pack in decision_memos[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reviewed `{pack.get('reviewed_at', '') or 'unknown'}`"
            )
    lines.extend(["", "## SOP Drafts"])
    if not sop_drafts:
        lines.append("- 当前没有 SOP drafts。")
    else:
        for pack in sop_drafts[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | action `{pack.get('action_id', '')}`"
                f" | risk `{pack.get('risk', 'medium')}`"
            )
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [判断资产](./judgment-assets.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def protocol_output_pack_rows(output_packs: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pack in output_packs.get("review_packs", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Review Pack",
                "title": str(pack.get("title") or "Review Pack"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reasons") or "manual review"),
            }
        )
    for pack in output_packs.get("decision_memos", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Decision Memo",
                "title": str(pack.get("title") or "Decision Memo"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reviewed_at") or "reviewed"),
            }
        )
    for pack in output_packs.get("sop_drafts", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "SOP Draft",
                "title": str(pack.get("title") or "SOP Draft"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("risk") or "medium"),
            }
        )
    rows.sort(key=lambda item: (item["kind"], item["title"].lower()))
    return rows[:limit]
