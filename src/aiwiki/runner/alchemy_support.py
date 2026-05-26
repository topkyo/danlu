"""Pure alchemy runner helpers extracted from the command hub."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from aiwiki.app_utils import parse_frontmatter, render_frontmatter, sha256_bytes, slugify, utc_now
from aiwiki.render.paths import execution_receipt_path

ALCHEMY_REVIEW_QUEUE_START = "<!-- aiwiki:alchemy-review-enqueue:start -->"
ALCHEMY_REVIEW_QUEUE_END = "<!-- aiwiki:alchemy-review-enqueue:end -->"
ALCHEMY_JUDGE_REFRESH_START = "<!-- aiwiki:alchemy-judge-refresh:start -->"
ALCHEMY_JUDGE_REFRESH_END = "<!-- aiwiki:alchemy-judge-refresh:end -->"
ALCHEMY_JUDGE_PROPOSAL_START = "<!-- aiwiki:alchemy-judge-proposal:start -->"
ALCHEMY_JUDGE_PROPOSAL_END = "<!-- aiwiki:alchemy-judge-proposal:end -->"
ALCHEMY_JUDGE_ACCEPTED_REFRESH_START = "<!-- aiwiki:accepted-judge-refresh:start -->"
ALCHEMY_JUDGE_ACCEPTED_REFRESH_END = "<!-- aiwiki:accepted-judge-refresh:end -->"
ALCHEMY_JUDGE_ACCEPTED_TARGET_START = "<!-- aiwiki:alchemy-accepted-judge-refresh:start -->"
ALCHEMY_JUDGE_ACCEPTED_TARGET_END = "<!-- aiwiki:alchemy-accepted-judge-refresh:end -->"


def string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def markdown_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")


def replace_marker_section(existing: str, section: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker in existing and end_marker in existing:
        before, rest = existing.split(start_marker, 1)
        _, after = rest.split(end_marker, 1)
        return before.rstrip() + "\n\n" + section + after.lstrip()
    if existing.strip():
        return existing.rstrip() + "\n\n" + section
    return section


def extract_marker_section(existing: str, *, start_marker: str, end_marker: str) -> str:
    if start_marker not in existing or end_marker not in existing:
        return ""
    _, rest = existing.split(start_marker, 1)
    body, _ = rest.split(end_marker, 1)
    return body.strip()


def replace_review_queue_section(existing: str, section: str) -> str:
    return replace_marker_section(
        existing,
        section,
        start_marker=ALCHEMY_REVIEW_QUEUE_START,
        end_marker=ALCHEMY_REVIEW_QUEUE_END,
    ) if existing.strip() else "# Review Queue\n\n" + section


def render_alchemy_judge_refresh_section(*, preview: dict[str, Any], candidate: dict[str, Any]) -> str:
    lines = [
        ALCHEMY_JUDGE_REFRESH_START,
        "## Alchemy Judge Refresh",
        "",
        f"- candidate_id: `{markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- target_ref: `{markdown_cell(str(candidate.get('target_ref') or ''))}`",
        f"- signal_ids: `{markdown_cell(', '.join(string_values(candidate.get('signal_ids'))) or 'none')}`",
        f"- trace_ids: `{markdown_cell(', '.join(string_values(candidate.get('trace_ids'))) or 'none')}`",
        f"- source_ids: `{markdown_cell(', '.join(string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{markdown_cell(', '.join(string_values(candidate.get('concept_slugs'))) or 'none')}`",
        "",
        "This marker records a scoped judge refresh opportunity. It does not rewrite the judgment conclusion.",
        ALCHEMY_JUDGE_REFRESH_END,
        "",
    ]
    return "\n".join(lines)


def render_alchemy_judge_proposal_page(
    *,
    preview: dict[str, Any],
    candidate: dict[str, Any],
    target_ref: str,
    proposal_id: str,
    target_kind: str,
    before_hash: str,
) -> str:
    trace_ids = string_values(candidate.get("trace_ids"))
    signal_ids = string_values(candidate.get("signal_ids"))
    frontmatter = {
        "kind": "alchemy-judge-proposal",
        "proposal_id": proposal_id,
        "state": "candidate",
        "target_file": target_ref,
        "target_kind": target_kind,
        "before_hash": before_hash,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "created_at": utc_now(),
        "llm_invoked": "false",
        "semantic_content_generated": "false",
        "human_accept_required": "true",
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# Judge Proposal: {proposal_id}",
        "",
        ALCHEMY_JUDGE_PROPOSAL_START,
        "## Target",
        "",
        f"- target_file: `{markdown_cell(target_ref)}`",
        f"- target_kind: `{markdown_cell(target_kind)}`",
        f"- before_hash: `{markdown_cell(before_hash)}`",
        "",
        "## Provenance",
        "",
        f"- candidate_id: `{markdown_cell(str(candidate.get('candidate_id') or ''))}`",
        f"- signal_ids: `{markdown_cell(', '.join(signal_ids) or 'none')}`",
        f"- trace_ids: `{markdown_cell(', '.join(trace_ids) or 'none')}`",
        f"- source_ids: `{markdown_cell(', '.join(string_values(candidate.get('source_ids'))) or 'none')}`",
        f"- concept_slugs: `{markdown_cell(', '.join(string_values(candidate.get('concept_slugs'))) or 'none')}`",
        f"- scope: `{markdown_cell(str(preview.get('scope') or ''))}`",
        "",
        "## Semantic Refresh Contract",
        "",
        "- llm_invoked: `false`",
        "- semantic_content_generated: `false`",
        "- human_accept_required: `true`",
        "- target_page_mutation: `false`",
        "- next_step: `fill this proposal through an explicit human/model contract, then apply in a separate accepted-proposal milestone`",
        "",
        "## Proposed Change Preview",
        "",
        "No judgment conclusion has been generated in this baseline. This artifact reserves a reviewable proposal slot and records the exact target hash that a future accepted semantic refresh must validate before applying.",
        "",
        "## Candidate Prompt Package",
        "",
        "```text",
        "Review the target judgment or decision page against the scoped evidence.",
        "Return a proposed semantic refresh as a separate proposal diff.",
        "Do not apply changes directly to the target page.",
        f"Target: {target_ref}",
        f"Before hash: {before_hash}",
        f"Signals: {', '.join(signal_ids) or 'none'}",
        f"Traces: {', '.join(trace_ids) or 'none'}",
        "```",
        ALCHEMY_JUDGE_PROPOSAL_END,
        "",
    ]
    return "\n".join(lines)


def render_alchemy_judge_accepted_target_section(*, proposal_id: str, proposal_path: str, accepted_body: str) -> str:
    lines = [
        ALCHEMY_JUDGE_ACCEPTED_TARGET_START,
        "## Accepted Judge Refresh",
        "",
        f"- proposal_id: `{markdown_cell(proposal_id)}`",
        f"- proposal_path: `{markdown_cell(proposal_path)}`",
        "",
        accepted_body.strip(),
        ALCHEMY_JUDGE_ACCEPTED_TARGET_END,
        "",
    ]
    return "\n".join(lines)


def render_alchemy_review_queue_section(*, preview: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    scope = str(preview.get("scope") or "")
    trace_ids = preview_trace_ids(preview)
    lines = [
        ALCHEMY_REVIEW_QUEUE_START,
        "## Alchemy scoped review enqueue",
        "",
        f"- scope: `{markdown_cell(scope)}`",
        f"- candidate_count: `{len(candidates)}`",
        f"- trace_ids: `{', '.join(trace_ids)}`",
        "",
        "| Candidate | Kind | Protocol | Target | Signals |",
        "| --- | --- | --- | --- | --- |",
    ]
    for candidate in candidates:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_cell(str(candidate.get("candidate_id") or "")),
                    markdown_cell(str(candidate.get("kind") or "")),
                    markdown_cell(str(candidate.get("protocol") or "")),
                    markdown_cell(str(candidate.get("target_ref") or "")),
                    markdown_cell(", ".join(string_values(candidate.get("signal_ids")))),
                ]
            )
            + " |"
        )
    lines.extend(["", ALCHEMY_REVIEW_QUEUE_END, ""])
    return "\n".join(lines)


def preview_trace_ids(preview: dict[str, Any]) -> list[str]:
    scope_preview = preview.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    return string_values(scope_preview.get("trace_ids"))


def first_preview_protocol(preview: dict[str, Any]) -> str:
    scope_preview = preview.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = string_values(scope_preview.get("protocols"))
        if protocols:
            return protocols[0]
    candidates = preview.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("protocol"):
                return str(candidate.get("protocol") or "")
    return ""


def normalize_preview_lock_status(value: Any) -> Any:
    """Rewrite preview lock status reported under a reentrant writer lock.

    Only subtrees reached through a ``lock`` key are normalized. Other dicts with
    the same shape are user data and must remain untouched.
    """
    return walk_preview_lock_status(value, in_lock_subtree=False)


def apply_preview_candidates(
    preview: dict[str, Any],
    *,
    status_error_template: str,
    empty_error_message: str,
    kind: str | None = None,
    require_apply_supported: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = normalize_preview_lock_status(preview)
    status = str(normalized.get("status") or "")
    if status != "ok":
        raise RuntimeError(status_error_template.format(status=status))
    candidates = []
    for item in normalized.get("candidates", []):
        if not isinstance(item, dict):
            continue
        if require_apply_supported and item.get("apply_supported") is not True:
            continue
        if kind is not None and item.get("kind") != kind:
            continue
        candidates.append(item)
    if not candidates:
        raise RuntimeError(empty_error_message)
    return normalized, candidates


def walk_preview_lock_status(value: Any, *, in_lock_subtree: bool) -> Any:
    if isinstance(value, dict):
        if (
            in_lock_subtree
            and "status" in value
            and "would_acquire" in value
            and value.get("status") == "held_by_current_process"
        ):
            normalized = dict(value)
            normalized["status"] = "available"
            normalized["would_acquire"] = True
            return {
                k: walk_preview_lock_status(v, in_lock_subtree=(k == "lock"))
                for k, v in normalized.items()
            }
        return {
            k: walk_preview_lock_status(v, in_lock_subtree=(k == "lock"))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [walk_preview_lock_status(item, in_lock_subtree=in_lock_subtree) for item in value]
    return value


def preview_receipt_summary(
    preview: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "status": str(preview.get("status") or ""),
        "scope": str(preview.get("scope") or ""),
        "selected_count": int(preview.get("selected_count") or 0),
        "candidate_count": len(candidates),
        "candidate_ids": [str(item.get("candidate_id") or "") for item in candidates if item.get("candidate_id")],
        "scope_preview": preview.get("scope_preview") if isinstance(preview.get("scope_preview"), dict) else {},
        "apply_contract": preview.get("apply_contract") if isinstance(preview.get("apply_contract"), dict) else {},
    }
    if extra:
        summary.update(extra)
    return summary


def review_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return preview_receipt_summary(preview, candidates)


def propose_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return preview_receipt_summary(preview, candidates, extra={"human_accept_required_after_apply": True})


def distill_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return preview_receipt_summary(
        preview,
        candidates,
        extra={"direct_apply_only": False, "lane_apply_supported": True},
    )


def judge_preview_receipt_summary(preview: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return preview_receipt_summary(
        preview,
        candidates,
        extra={"semantic_rewrite": False, "lane_apply_supported": False},
    )


def alchemy_idempotency_key(
    prefix: str,
    *,
    primitive: str,
    scope: str,
    candidate_ids: list[str],
    trace_ids: list[str],
    extra: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "primitive": primitive,
        "scope": scope,
        "candidate_ids": sorted(candidate_ids),
        "trace_ids": sorted(trace_ids),
    }
    if extra:
        payload.update(extra)
    digest = sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return f"{prefix}:{digest}"


def alchemy_review_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    return alchemy_idempotency_key(
        "alchemy-review",
        primitive="review",
        scope=scope,
        candidate_ids=candidate_ids,
        trace_ids=trace_ids,
    )


def alchemy_propose_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    return alchemy_idempotency_key(
        "alchemy-propose",
        primitive="propose",
        scope=scope,
        candidate_ids=candidate_ids,
        trace_ids=trace_ids,
    )


def alchemy_distill_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    return alchemy_idempotency_key(
        "alchemy-distill",
        primitive="distill",
        scope=scope,
        candidate_ids=candidate_ids,
        trace_ids=trace_ids,
        extra={"question_template": "scoped_elixir_candidate_refresh"},
    )


def alchemy_judge_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    return alchemy_idempotency_key(
        "alchemy-judge",
        primitive="judge",
        scope=scope,
        candidate_ids=candidate_ids,
        trace_ids=trace_ids,
        extra={"marker": "scoped_judge_refresh_marker"},
    )


def alchemy_judge_proposal_idempotency_key(*, scope: str, candidate_ids: list[str], trace_ids: list[str]) -> str:
    return alchemy_idempotency_key(
        "alchemy-judge-proposal",
        primitive="judge",
        scope=scope,
        candidate_ids=candidate_ids,
        trace_ids=trace_ids,
        extra={"mode": "proposal_preview"},
    )


def unique_alchemy_action_id(root: Path, *, prefix: str, applied_at: str) -> str:
    timestamp = re.sub(r"[^0-9]", "", applied_at)[:14] or str(int(time.time()))
    base = slugify(f"{prefix}-{timestamp}")
    candidate = base
    n = 2
    while execution_receipt_path(root, candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def alchemy_distill_target_id(target_ref: str) -> str:
    normalized = target_ref.strip()
    if not normalized:
        return ""
    return Path(normalized).stem


def alchemy_distill_question(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("candidate_id") or "distill")
    target_ref = str(candidate.get("target_ref") or "")
    signal_ids = ",".join(string_values(candidate.get("signal_ids"))) or "none"
    return f"Alchemy scoped distill refresh for {candidate_id} ({target_ref}); signals={signal_ids}"


def alchemy_distill_history_questions(path: Path) -> set[str]:
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    raw = frontmatter.get("distill_history_json")
    if not isinstance(raw, str) or not raw.strip():
        return set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(decoded, list):
        return set()
    questions: set[str] = set()
    for item in decoded:
        if isinstance(item, dict) and isinstance(item.get("question"), str):
            questions.add(str(item["question"]))
    return questions


def alchemy_propose_prompt_content(root: Path, *, target_file: str, candidate: dict[str, Any], scope: str) -> str:
    target = root / target_file
    current = target.read_text(encoding="utf-8", errors="replace")
    signal_ids = ", ".join(string_values(candidate.get("signal_ids"))) or "none"
    candidate_id = str(candidate.get("candidate_id") or "")
    target_ref = str(candidate.get("target_ref") or "")
    block = "\n".join(
        [
            "",
            "<!-- aiwiki:alchemy-propose:start -->",
            f"<!-- scope: {scope} -->",
            f"<!-- candidate_id: {candidate_id} -->",
            f"<!-- target_ref: {target_ref} -->",
            f"<!-- signal_ids: {signal_ids} -->",
            "<!-- Manual review is required before accepting this proposal. -->",
            "<!-- aiwiki:alchemy-propose:end -->",
        ]
    )
    return current.rstrip() + block + "\n"


def unique_alchemy_propose_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-propose", applied_at=applied_at)


def unique_alchemy_distill_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-distill", applied_at=applied_at)


def unique_alchemy_judge_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-judge", applied_at=applied_at)


def unique_alchemy_judge_proposal_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-judge-proposal", applied_at=applied_at)


def unique_alchemy_judge_proposal_apply_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-judge-proposal-apply", applied_at=applied_at)


def unique_alchemy_review_action_id(root: Path, *, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix="alchemy-review", applied_at=applied_at)


def unique_lane_primitive_action_id(root: Path, *, lane: str, primitive: str, applied_at: str) -> str:
    return unique_alchemy_action_id(root, prefix=f"alchemy-{lane}-{primitive}", applied_at=applied_at)


def lane_primitive_plan_step(plan: dict[str, Any], primitive: str) -> dict[str, Any] | None:
    for item in plan.get("primitive_plan", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("primitive") or "") == primitive:
            return item
    return None


def normalize_auto_lanes(lanes: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in lanes:
        lane = item.strip().lower()
        if lane not in {"heavy", "light"}:
            raise ValueError(f"unsupported alchemy auto lane: {item}")
        if lane in seen:
            continue
        seen.add(lane)
        normalized.append(lane)
    if not normalized:
        raise ValueError("alchemy auto requires at least one lane")
    return normalized


def normalize_lane_primitives(primitives: list[str]) -> list[str]:
    allowed = {"compile", "distill", "lint", "nightly", "review", "propose"}
    normalized: list[str] = []
    seen: set[str] = set()
    for item in primitives:
        primitive = item.strip().lower()
        if not primitive:
            continue
        if primitive not in allowed:
            raise ValueError(f"unsupported alchemy lane primitive: {item}")
        if primitive in seen:
            continue
        seen.add(primitive)
        normalized.append(primitive)
    return normalized


def auto_primitives_for_lane(
    lane: str,
    plan: dict[str, Any],
    *,
    requested_primitives: list[str],
) -> list[str]:
    defaults = {"heavy": ["compile", "lint"], "light": ["compile", "lint", "nightly"]}[lane]
    wanted = requested_primitives or defaults
    auto_supported_primitives = {"compile", "lint", "nightly"}
    if requested_primitives and lane == "heavy":
        auto_supported_primitives.add("distill")
        auto_supported_primitives.add("review")
        auto_supported_primitives.add("propose")
    supported = {
        str(item.get("primitive") or "")
        for item in plan.get("primitive_plan", [])
        if (
            isinstance(item, dict)
            and item.get("apply_supported") is True
            and str(item.get("primitive") or "") in auto_supported_primitives
        )
    }
    return [primitive for primitive in wanted if primitive in supported]


def auto_skip_reason(plan: dict[str, Any], selected_primitives: list[str]) -> str:
    status = str(plan.get("status") or "")
    if status != "ok":
        return f"plan_{status or 'unknown'}"
    if int(plan.get("selected_count") or 0) <= 0:
        return "empty_execute_plan"
    if not selected_primitives:
        return "no_apply_supported_primitives"
    return ""


def first_plan_protocol(plan: dict[str, Any]) -> str:
    scope_preview = plan.get("scope_preview")
    if isinstance(scope_preview, dict):
        protocols = scope_preview.get("protocols")
        if isinstance(protocols, list) and protocols:
            return str(protocols[0])
    return ""


def lane_receipt_trace_ids(plan: dict[str, Any]) -> list[str]:
    scope_preview = plan.get("scope_preview")
    if not isinstance(scope_preview, dict):
        return []
    return string_values(scope_preview.get("trace_ids"))


def primary_result_path(result: dict[str, Any]) -> str:
    for key in ("state_path", "path", "semantic_report"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    repair_backlog = result.get("repair_backlog")
    if isinstance(repair_backlog, str) and repair_backlog:
        return repair_backlog
    return ""


def lane_primitive_scope(
    *,
    primitive: str,
    scope: str,
) -> dict[str, str]:
    requested_scope = scope
    effective_scope = scope
    scope_downgraded_from = ""
    if primitive in {"compile", "lint", "nightly"} and scope != "all":
        effective_scope = "all"
        scope_downgraded_from = scope
    return {
        "requested_scope": requested_scope,
        "effective_scope": effective_scope,
        "scope_downgraded_from": scope_downgraded_from,
    }


def lane_receipt_plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": str(plan.get("lane") or ""),
        "scope": str(plan.get("scope") or ""),
        "selected_count": int(plan.get("selected_count") or 0),
        "scope_preview": plan.get("scope_preview") if isinstance(plan.get("scope_preview"), dict) else {},
        "primitive_plan": list(plan.get("primitive_plan") or []),
    }


def lane_receipt_result_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("state_path", "repair_backlog", "semantic_report", "llm_used"):
        if key in result:
            summary[key] = result[key]
    if "updated_source_pages" in result:
        summary["updated_source_pages_count"] = len(result.get("updated_source_pages") or [])
    if "updated_concept_pages" in result:
        summary["updated_concept_pages_count"] = len(result.get("updated_concept_pages") or [])
    if "counts" in result and isinstance(result.get("counts"), dict):
        summary["counts"] = result["counts"]
    return summary


def lane_primitive_receipt_payload(
    *,
    lane: str,
    primitive: str,
    plan: dict[str, Any],
    result: dict[str, Any],
    action_id: str,
    applied_at: str,
    receipt_path: str,
    audit_path: str,
    note: str,
    requested_scope: str,
    effective_scope: str,
    scope_downgraded_from: str,
) -> dict[str, Any]:
    trace_ids = lane_receipt_trace_ids(plan)
    trace_id = trace_ids[0] if trace_ids else ""
    plan_scope_preview = plan.get("scope_preview")
    scope_declared = plan_scope_preview if isinstance(plan_scope_preview, dict) else {}
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-alchemy-lane",
        "applied_at": applied_at,
        "operation": "alchemy-lane-primitive",
        "action_id": action_id,
        "trace_id": trace_id,
        "trace_ids": trace_ids,
        "title": f"Alchemy {lane} {primitive}",
        "status": "applied",
        "protocol": first_plan_protocol(plan),
        "subject_kind": "alchemy_lane_primitive",
        "subject_id": f"{lane}:{effective_scope}:{primitive}",
        "apply_mode": f"alchemy-{lane}-{primitive}",
        "note": note,
        "primary_path": primary_result_path(result),
        "secondary_path": "",
        "receipt_path": receipt_path,
        "lane": lane,
        "scope": effective_scope,
        "scope_requested": requested_scope,
        "scope_downgraded_from": scope_downgraded_from,
        "scope_declared": scope_declared,
        "scope_enforced": True,
        "scope_enforcement_reason": (
            "primitive_global_only:downgraded_to_global"
            if scope_downgraded_from
            else "primitive_global_only:executed_globally"
        ),
        "primitive": primitive,
        "revert_supported": False,
        "audit_stream": "execution_receipts",
        "audit_event": "execution_receipt_history_append",
        "audit_path": audit_path,
        "source_plan": lane_receipt_plan_summary(plan),
        "result_summary": lane_receipt_result_summary(result),
    }


def alchemy_auto_runtime_event_payload(
    *,
    scope: str,
    lanes: list[str],
    primitives: list[str],
    lane_results: list[dict[str, Any]],
    applied_results: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    recorded_at: str,
) -> dict[str, Any]:
    trace_ids: set[str] = set()
    for lane_result in lane_results:
        plan = lane_result.get("plan")
        if isinstance(plan, dict):
            trace_ids.update(lane_receipt_trace_ids(plan))
    sorted_trace_ids = sorted(trace_ids)
    return {
        "event_type": "alchemy-auto-scheduler",
        "recorded_at": recorded_at,
        "status": "completed",
        "scope": scope,
        "lanes": lanes,
        "requested_primitives": primitives,
        "applied_count": len(applied_results),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "trace_id": sorted_trace_ids[0] if sorted_trace_ids else "",
        "trace_ids": sorted_trace_ids,
        "subject_kind": "alchemy_auto_scheduler",
        "subject_id": scope,
    }


def alchemy_lane_runtime_event_payload(
    *,
    event_type: str,
    lane: str,
    scope: str,
    action_ids: list[str],
    primitives: list[str],
    plan: dict[str, Any],
    status: str,
    recorded_at: str,
    primitive_results: list[dict[str, Any]] | None = None,
    apply_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace_ids = lane_receipt_trace_ids(plan)
    event: dict[str, Any] = {
        "event_type": event_type,
        "recorded_at": recorded_at,
        "status": status,
        "lane": lane,
        "scope": scope,
        "action_ids": action_ids,
        "primitives": primitives,
        "selected_count": int(plan.get("selected_count") or 0),
        "trace_id": trace_ids[0] if trace_ids else "",
        "trace_ids": trace_ids,
        "subject_kind": "alchemy_lane",
        "subject_id": f"{lane}:{scope}",
    }
    if primitive_results is not None:
        event["primitive_count"] = len(primitive_results)
        event["primitive_receipts"] = [
            str(item.get("receipt_path") or "")
            for item in primitive_results
            if isinstance(item, dict) and item.get("receipt_path")
        ]
    if apply_result is not None:
        event["action_batch_receipt"] = str(
            apply_result.get("receipt_path") or apply_result.get("batch_receipt_path") or ""
        )
    return event
