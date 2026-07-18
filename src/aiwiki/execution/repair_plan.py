"""Repair-plan domain logic (EP-017C step 4a).

Split out of ``aiwiki.content.memory``: machine-memory repair-plan builder,
rewrite-candidate validation / currency / apply-ready checks, proposal
rollback / impact / dependency helpers, planner-state assembler, and the
``repair_execution_proposals`` strategy entry point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_protocol import DEFAULT_PROTOCOL, action_focus_score
from ..app_state_paths import planner_state_path
from ..memory.action_core import (
    action_priority_rank,
    action_status_rank,
    describe_machine_memory_action,
    safe_apply_preview,
)
from ..planner.state import load_planner_state
from ..render.paths import execution_bundle_path, execution_proposal_path
from ..utils.markdown import parse_frontmatter
from ..utils.path import relative_path
from ..utils.time import utc_now
from .patch_plan import build_page_patch_plan


def build_machine_memory_repair_plan(
    root: Path,
    health: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    active_actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    for action in active_actions + inactive_actions:
        action["focus_score"] = action_focus_score(active_protocol, action)
        action.update(describe_machine_memory_action(action, root=root))
    ready_actions = [action for action in active_actions if action.get("status") == "accepted"]
    triage_actions = [action for action in active_actions if action.get("status") == "proposed"]
    deferred_actions = [action for action in active_actions if action.get("status") == "deferred"]
    escalated_ids = {action["id"] for action in health.get("escalated_actions", []) if action.get("id")}
    overdue_ids = {action["id"] for action in health.get("overdue_actions", []) if action.get("id")}

    batches: dict[str, dict[str, Any]] = {}
    for action in ready_actions:
        batch_key = str(action.get("component_id") or action.get("primary_path") or action.get("id"))
        label = (
            f"component `{action['component_id']}`"
            if action.get("component_id")
            else f"page `{action['primary_path']}`"
        )
        batch = batches.setdefault(
            batch_key,
            {
                "id": batch_key,
                "label": label,
                "component_id": action.get("component_id", ""),
                "primary_paths": set(),
                "secondary_paths": set(),
                "action_ids": [],
                "actions": [],
                "priority_rank": 9,
                "escalated": False,
                "overdue": False,
            },
        )
        batch["primary_paths"].add(str(action.get("primary_path") or ""))
        if action.get("secondary_path"):
            batch["secondary_paths"].add(str(action.get("secondary_path") or ""))
        batch["action_ids"].append(action["id"])
        batch["actions"].append(action)
        batch["priority_rank"] = min(batch["priority_rank"], action_priority_rank(str(action.get("priority") or "")))
        batch["escalated"] = batch["escalated"] or action["id"] in escalated_ids
        batch["overdue"] = batch["overdue"] or action["id"] in overdue_ids

    execution_batches = sorted(
        [
            {
                **batch,
                "primary_paths": sorted(path for path in batch["primary_paths"] if path),
                "secondary_paths": sorted(path for path in batch["secondary_paths"] if path),
                "actions": sorted(
                    batch["actions"],
                    key=lambda item: (
                        -int(item.get("focus_score", 0)),
                        action_priority_rank(str(item.get("priority") or "")),
                        -int(item.get("occurrences", 0)),
                        str(item.get("title", "")).lower(),
                    ),
                ),
            }
            for batch in batches.values()
        ],
        key=lambda item: (
            0 if item["escalated"] else 1,
            0 if item["overdue"] else 1,
            -max((int(action.get("focus_score", 0)) for action in item["actions"]), default=0),
            item["priority_rank"],
            item["label"],
        ),
    )
    execution_proposals: list[dict[str, Any]] = []
    previous_planner = load_planner_state(root)
    planner_state = {
        **previous_planner,
        "pending_proposals": [],
        "priority_queue": [],
        "counts": {
            **(previous_planner.get("counts") if isinstance(previous_planner.get("counts"), dict) else {}),
            "pending_proposals": 0,
            "blocked": 0,
            "unblocked": 0,
        },
    }

    return {
        "ready_actions": ready_actions,
        "triage_actions": triage_actions,
        "deferred_actions": deferred_actions,
        "inactive_actions": inactive_actions[:12],
        "execution_batches": execution_batches[:10],
        "execution_proposals": execution_proposals,
        "planner_state": planner_state,
        "counts": {
            "ready": len(ready_actions),
            "triage": len(triage_actions),
            "deferred": len(deferred_actions),
            "inactive": len(inactive_actions),
            "batches": len(execution_batches),
            "proposals": len(execution_proposals),
            "patch_steps": sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals),
            "blocked_proposals": int(planner_state.get("counts", {}).get("blocked", 0) or 0),
        },
    }


def _validate_rewrite_candidate_markdown(
    candidate_markdown: str,
    slug: str,
    source_signature: str,
    source_pages: list[str],
) -> None:
    frontmatter = parse_frontmatter(candidate_markdown)
    if str(frontmatter.get("id") or "") != f"concept-{slug}":
        raise RuntimeError("Rewrite candidate must preserve the concept id.")
    if str(frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Rewrite candidate must preserve `kind: concept`.")
    if str(frontmatter.get("source_signature") or "") != source_signature:
        raise RuntimeError("Rewrite candidate source_signature no longer matches the target concept.")
    candidate_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(candidate_source_pages, list):
        raise RuntimeError("Rewrite candidate must preserve source_pages.")
    normalized_candidate_sources = [str(item) for item in candidate_source_pages if isinstance(item, str)]
    if normalized_candidate_sources != source_pages:
        raise RuntimeError("Rewrite candidate source_pages no longer match the target concept.")


def rewrite_proposal_candidate_is_current(root: Path, proposal: dict[str, Any]) -> bool:
    slug = str(proposal.get("slug") or "")
    candidate_markdown = str(proposal.get("candidate_markdown") or "")
    if not slug or not candidate_markdown:
        return False
    concept_path = root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        return False
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(proposal.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        return False
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        return False
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    try:
        _validate_rewrite_candidate_markdown(
            candidate_markdown,
            slug,
            expected_source_signature,
            normalized_source_pages,
        )
    except RuntimeError:
        return False
    return True


def rewrite_proposal_is_apply_ready(root: Path, proposal: dict[str, Any]) -> bool:
    return str(proposal.get("status") or "") == "accepted" and rewrite_proposal_candidate_is_current(root, proposal)


def proposal_rollback_summary(proposal: dict[str, Any]) -> str:
    preview = proposal.get("safe_apply_preview")
    if isinstance(preview, dict):
        apply_mode = str(preview.get("apply_mode") or "")
        if apply_mode == "manual-link-state":
            return "禁用对应的 manual-link state 条目并重跑 compile。"
        if apply_mode == "citation-snapshot-refresh":
            return "恢复之前的 citation_snapshots metadata 并重跑 compile。"
    return "回滚时需要人工恢复目标页，然后重跑 compile。"


def proposal_impact_score(action: dict[str, Any], proposal: dict[str, Any]) -> int:
    priority_base = {"high": 55, "medium": 35, "low": 20}.get(
        str(action.get("priority") or proposal.get("priority") or "medium"), 20
    )
    focus_bonus = min(24, int(action.get("focus_score", 0) or 0) * 3)
    occurrence_bonus = min(12, int(action.get("occurrences", 0) or 0) * 2)
    accepted_bonus = 10 if str(action.get("status") or proposal.get("status") or "") == "accepted" else 0
    escalation_bonus = 8 if str(action.get("escalation_candidate") or "") == "true" else 0
    overdue_bonus = 6 if str(action.get("overdue_review") or "") == "true" else 0
    policy_bonus = 6 if str(action.get("policy_decision") or proposal.get("policy_decision") or "") == "allow" else 0
    return min(
        100,
        priority_base
        + focus_bonus
        + occurrence_bonus
        + accepted_bonus
        + escalation_bonus
        + overdue_bonus
        + policy_bonus,
    )


def proposal_dependency_weight(proposal: dict[str, Any]) -> tuple[int, int]:
    kind_rank = {
        "split-concept": 5,
        "expand-concept": 4,
        "connect-source": 3,
        "cross-link": 2,
        "refresh-snapshots": 1,
        "monitor-bridge": 1,
        "manual-repair": 0,
    }
    return (
        kind_rank.get(str(proposal.get("proposal_kind") or "manual-repair"), 0),
        int(proposal.get("impact_score", 0) or 0),
    )


def proposals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_targets = {str(path) for path in left.get("target_paths", []) if isinstance(path, str) and path}
    right_targets = {str(path) for path in right.get("target_paths", []) if isinstance(path, str) and path}
    if left_targets and right_targets and left_targets.intersection(right_targets):
        return True
    left_sources = {str(item) for item in left.get("source_ids", []) if isinstance(item, str) and item}
    right_sources = {str(item) for item in right.get("source_ids", []) if isinstance(item, str) and item}
    left_concepts = {str(item) for item in left.get("concept_slugs", []) if isinstance(item, str) and item}
    right_concepts = {str(item) for item in right.get("concept_slugs", []) if isinstance(item, str) and item}
    if left_sources and right_sources and left_sources.intersection(right_sources):
        return True
    if left_concepts and right_concepts and left_concepts.intersection(right_concepts):
        return True
    component_id = str(left.get("component_id") or "")
    return bool(component_id) and component_id == str(right.get("component_id") or "")


def derive_proposal_dependencies(proposals: list[dict[str, Any]]) -> None:
    for proposal in proposals:
        current_weight = proposal_dependency_weight(proposal)
        depends_on: list[str] = []
        for candidate in proposals:
            if candidate is proposal:
                continue
            candidate_action_id = str(candidate.get("action_id") or "")
            if not candidate_action_id or not proposals_overlap(proposal, candidate):
                continue
            if proposal_dependency_weight(candidate) <= current_weight:
                continue
            if candidate_action_id not in depends_on:
                depends_on.append(candidate_action_id)
        proposal["depends_on"] = depends_on


def build_planner_state(
    root: Path,
    proposals: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_planner_state(root)
    executed_actions = [dict(item) for item in previous_state.get("executed_actions", []) if isinstance(item, dict)]
    proposal_records: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for proposal in proposals:
        action_id = str(proposal.get("action_id") or "")
        depends_on = [str(item) for item in proposal.get("depends_on", []) if isinstance(item, str) and item]
        blocked = bool(depends_on)
        status = str(proposal.get("status") or "proposed")
        is_low_risk = str(proposal.get("risk") or "medium") == "low"
        auto_bundle_candidate = is_low_risk and status == "accepted" and not blocked
        human_required = bool(blocked or not auto_bundle_candidate)
        proposal_record = {
            **proposal,
            "status": status,
            "blocked": blocked,
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        proposal_records.append(proposal_record)
        queue_item = {
            "item_id": f"proposal:{action_id}",
            "item_kind": "execution-proposal",
            "action_id": action_id,
            "title": str(proposal.get("title") or action_id),
            "priority": str(proposal.get("priority") or "medium"),
            "status": status,
            "protocol": str(proposal.get("protocol") or active_protocol),
            "impact_score": int(proposal.get("impact_score", 0) or 0),
            "priority_score": int(proposal.get("priority_score", 0) or 0),
            "blocked": blocked,
            "depends_on": depends_on,
            "target_paths": list(proposal.get("target_paths", []) or []),
            "command_hint": str(proposal.get("command_hint") or ""),
            "next_step": str(proposal.get("next_step") or ""),
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        queue.append(queue_item)
        nodes.append(
            {
                "action_id": action_id,
                "title": queue_item["title"],
                "priority_score": queue_item["priority_score"],
                "impact_score": queue_item["impact_score"],
                "blocked": blocked,
            }
        )
        edges.extend({"from": action_id, "to": dependency} for dependency in depends_on)
    queue.sort(
        key=lambda item: (
            0 if not item.get("blocked") else 1,
            -int(item.get("priority_score", 0) or 0),
            action_priority_rank(str(item.get("priority") or "medium")),
            str(item.get("title") or "").lower(),
        )
    )
    next_action = queue[0] if queue else {}
    return {
        "version": 1,
        "generated_at": utc_now(),
        "state_path": relative_path(root, planner_state_path(root)),
        "active_protocol": active_protocol,
        "pending_proposals": proposal_records,
        "priority_queue": queue[:12],
        "dependency_graph": {
            "nodes": nodes[:16],
            "edges": edges[:24],
        },
        "next_action": next_action,
        "executed_actions": executed_actions[:16],
        "counts": {
            "pending_proposals": len(proposal_records),
            "blocked": sum(1 for item in queue if item.get("blocked")),
            "unblocked": sum(1 for item in queue if not item.get("blocked")),
            "executed_actions": len(executed_actions),
        },
    }


def repair_execution_proposals(
    root: Path,
    actions: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    strategy_map = {
        "add-source-concept-link": {
            "kind": "cross-link",
            "risk": "low",
            "summary": "补 source/concept 双向链接，并检查概念摘要是否需要吸收新证据。",
            "edits": [
                "在 source page 里补 concept 引用或相关链接。",
                "在 concept page 的 Related Sources 里加入该 source page。",
                "如果来源提供新证据，重写 concept 摘要并保持 provenance。",
            ],
        },
        "connect-isolated-source": {
            "kind": "connect-source",
            "risk": "medium",
            "summary": "把孤立来源接入至少一个稳定概念，并显式记录依据。",
            "edits": [
                "先从 source page 抽出候选概念。",
                "优先补到现有稳定概念；必要时再新建概念页。",
                "保持 source page 对 raw evidence 的回指。",
            ],
        },
        "expand-singleton-concept": {
            "kind": "expand-concept",
            "risk": "medium",
            "summary": "扩展单节点概念的来源覆盖或相关概念边界。",
            "edits": [
                "补更多来源或相关概念反链。",
                "重写摘要时强调当前证据仍然有限。",
                "如果概念过窄，考虑降级为 source-specific note。",
            ],
        },
        "split-overloaded-concept": {
            "kind": "split-concept",
            "risk": "high",
            "summary": "拆分过载概念，明确子概念边界和来源分流。",
            "edits": [
                "先定义更窄的子概念名称和边界。",
                "把 source pages 重新分流到更具体的概念页。",
                "在原概念页保留拆分说明和跳转链接。",
            ],
        },
        "monitor-bridge-concept": {
            "kind": "monitor-bridge",
            "risk": "low",
            "summary": "记录桥接概念仍然必要的原因，避免误删跨簇连接。",
            "edits": [
                "在 concept page 里补一段 bridge maintenance note。",
                "确认相关概念链接仍然成立。",
                "如果桥接已经失效，再把动作转成 merge 或 split。 ",
            ],
        },
        "refresh-citation-snapshots": {
            "kind": "refresh-snapshots",
            "risk": "low",
            "summary": "刷新 judgment citation snapshot metadata，让 drift / review surface 收敛。",
            "edits": [
                "重建 citation_snapshots metadata，不改正文结论。",
                "确认 provenance 仍指向现有 citation 列表。",
                "执行后重跑 compile，验证 judgment drift 与 review window 是否收敛。",
            ],
        },
    }
    protocol_hints = {
        "general": {
            "summary_suffix": "",
            "edits": [],
        },
    }
    proposals: list[dict[str, Any]] = []
    for action in actions:
        template = strategy_map.get(str(action.get("kind") or ""), {})
        action_id = str(action.get("id") or "")
        proposal_protocol = str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        hint = protocol_hints.get(proposal_protocol, protocol_hints[DEFAULT_PROTOCOL])
        target_paths = [
            path
            for path in (
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            )
            if path
        ]
        proposal = {
            "id": f"proposal-{action_id}",
            "action_id": action_id,
            "title": str(action.get("title") or ""),
            "priority": str(action.get("priority") or "medium"),
            "status": str(action.get("status") or "proposed"),
            "execution_policy": str(action.get("execution_policy") or "triage"),
            "execution_band": str(action.get("execution_band") or "review-first"),
            "policy_decision": str(action.get("policy_decision") or ""),
            "policy_rule_id": str(action.get("policy_rule_id") or ""),
            "proposal_kind": str(template.get("kind") or "manual-repair"),
            "risk": str(template.get("risk") or "medium"),
            "summary": (
                str(template.get("summary") or action.get("reason") or "") + str(hint.get("summary_suffix") or "")
            ).strip(),
            "target_paths": target_paths,
            "suggested_edits": list(
                template.get("edits") or [str(action.get("reason") or "检查相关页面并补修复说明。")]
            )
            + list(hint.get("edits") or []),
            "command_hint": str(action.get("command_hint") or ""),
            "next_step": str(action.get("next_step") or ""),
            "protocol": proposal_protocol,
            "focus_score": int(action.get("focus_score", 0)),
            "component_id": str(action.get("component_id") or ""),
            "source_ids": [str(item) for item in action.get("source_ids", []) if isinstance(item, str) and item],
            "concept_slugs": [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str) and item],
            "apply_ready": str(action.get("apply_ready") or "false"),
        }
        proposal["page_patch_plan"] = build_page_patch_plan(root, action, active_protocol=proposal_protocol)
        proposal["proposal_path"] = relative_path(root, execution_proposal_path(root, action_id))
        proposal["bundle_path"] = relative_path(root, execution_bundle_path(root, action_id))
        proposal["safe_apply_preview"] = safe_apply_preview(root, action)
        proposal["rollback_summary"] = proposal_rollback_summary(proposal)
        proposal["impact_score"] = proposal_impact_score(action, proposal)
        proposal["priority_score"] = min(
            120,
            int(proposal["impact_score"])
            + {"accepted": 16, "proposed": 8, "deferred": 2}.get(proposal["status"], 0)
            + {"allow": 8, "review": 0, "history": -10}.get(proposal["policy_decision"], 0)
            + {"bundle-safe-apply": 6, "review-first": 0, "manual-repair": -4, "deferred": -8}.get(
                proposal["execution_band"],
                0,
            ),
        )
        proposals.append(proposal)
    derive_proposal_dependencies(proposals)
    for proposal in proposals:
        proposal["priority_score"] = max(
            0,
            int(proposal.get("priority_score", 0) or 0) - (4 * len(proposal.get("depends_on", []))),
        )
    proposals.sort(
        key=lambda item: (
            0 if not item.get("depends_on") else 1,
            action_status_rank(item["status"]),
            -int(item.get("priority_score", 0)),
            -int(item.get("impact_score", 0)),
            action_priority_rank(item["priority"]),
            item["proposal_kind"],
            item["title"].lower(),
        )
    )
    return proposals[:16]
