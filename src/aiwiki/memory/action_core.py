"""Machine-memory action domain logic (EP-017C step 4a).

Split out of ``aiwiki.content.memory``: machine-memory action collection,
signatures, low-risk apply preview / validation, action description, and
stale execution-proposal / bundle cleanup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..content.concepts import (
    concept_source_pages,
    normalize_concept_hardness,
    parse_causal_links,
)
from ..content.io import (
    source_summary_or_preview,
    sync_manifest_with_raw,
)
from ..content.memory import concept_summary_is_placeholder
from ..execution.policy import execution_band_label, execution_policy_profile
from ..protocol.focus_scoring import action_focus_score
from ..protocol.runtime_config import LOW_RISK_APPLYABLE_ACTION_KINDS, RESOLVABLE_MONITOR_ACTION_KINDS
from ..protocol.state import load_protocol_state
from ..render.paths import (
    execution_bundle_path,
    execution_bundles_dir,
    execution_proposal_path,
    execution_proposals_dir,
)
from ..utils.hash import sha256_bytes
from ..utils.markdown import build_citation_snapshots, parse_frontmatter
from ..utils.path import relative_path
from ..utils.text import slugify
from .action_state import load_machine_memory_action_state
from .paths import manual_link_state_path


def machine_memory_source_input_signature(
    root: Path,
    entry: dict[str, Any],
    preview: str,
    concepts: list[str],
) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "kind": str(entry.get("kind") or ""),
        "stored_path": str(entry.get("stored_path") or ""),
        "original_path": str(entry.get("original_path") or ""),
        "sha256": str(entry.get("sha256") or ""),
        "summary": source_summary_or_preview(root, entry, preview),
        "concepts": sorted(str(label) for label in concepts if str(label)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def machine_memory_concept_input_signature(root: Path, record: dict[str, Any]) -> str:
    page = root / "wiki" / "concepts" / f"{record.get('slug', '')}.md"
    frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace")) if page.exists() else {}
    causal_links = parse_causal_links(frontmatter)
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "source_pages": concept_source_pages(record),
        "related_slugs": sorted(str(slug) for slug in record.get("related_slugs", []) if str(slug)),
        "confidence": str(frontmatter.get("confidence") or ""),
        "hardness": normalize_concept_hardness(frontmatter.get("hardness"), default="soft"),
        "causal_links": sorted(
            [{"target": link["target"], "relation": link["relation"]} for link in causal_links],
            key=lambda item: (item["target"], item["relation"]),
        ),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def collect_machine_memory_actions(root: Path) -> list[dict[str, Any]]:
    from ..lifecycle.aging import evaluate_page_aging
    from ..lifecycle.status import action_needs_review

    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    now = datetime.now(timezone.utc)
    active_protocol = load_protocol_state(root)["active_protocol"]
    for action in actions:
        action.setdefault("status", "proposed")
        action.setdefault("active", True)
        action.setdefault("priority", "medium")
        action.setdefault("review_note", "")
        action.setdefault("first_seen_at", "")
        action.setdefault("last_seen_at", "")
        action.setdefault("inactive_since", "")
        action.setdefault("occurrences", 0)
        action.setdefault("pending_review", "true" if action_needs_review(str(action.get("status"))) else "false")
        action.update(evaluate_page_aging(action, now=now))
        action["focus_score"] = action_focus_score(active_protocol, action)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}
    return sorted(
        actions,
        key=lambda item: (
            0 if item.get("active") else 1,
            status_order.get(str(item.get("status")), 9),
            0 if item.get("escalation_candidate") == "true" else 1,
            0 if item.get("overdue_review") == "true" else 1,
            -int(item.get("focus_score", 0)),
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("occurrences", 0)),
            str(item.get("title", "")).lower(),
        ),
    )


def collect_machine_memory_action_aging(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    active_actions = [action for action in actions if action.get("active")]
    overdue = [action for action in active_actions if action.get("overdue_review") == "true"]
    escalated = [action for action in active_actions if action.get("escalation_candidate") == "true"]
    scheduled = [action for action in active_actions if action.get("aging_state") == "scheduled"]
    inactive = [action for action in actions if not action.get("active")]
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
        "inactive": inactive,
    }


def action_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 9)


def action_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}.get(status, 9)


def action_supports_low_risk_apply(action: dict[str, Any]) -> bool:
    if not bool(action.get("active", True)) or str(action.get("status") or "") != "accepted":
        return False
    kind = str(action.get("kind") or "")
    decision = str(action.get("policy_decision") or "")
    if decision:
        return decision == "allow" and kind in LOW_RISK_APPLYABLE_ACTION_KINDS
    return kind in LOW_RISK_APPLYABLE_ACTION_KINDS


def safe_apply_preview(root: Path, action: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(action.get("kind") or "")
    if kind == "refresh-citation-snapshots":
        page_path = str(action.get("primary_path") or "")
        if not page_path:
            return None
        absolute = root / page_path
        if not absolute.exists():
            return None
        content = absolute.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        if not citations:
            return None
        return {
            "apply_mode": "citation-snapshot-refresh",
            "page_path": page_path,
            "previous_citation_snapshots": list(frontmatter.get("citation_snapshots", []) or []),
            "updated_citation_snapshots": build_citation_snapshots(root, citations),
            "affected_paths": [page_path],
            "follow_up": "执行后会重跑 compile，让 judgment drift / review surface 重新收敛。",
        }
    if kind in RESOLVABLE_MONITOR_ACTION_KINDS:
        primary_path = str(action.get("primary_path") or "")
        return {
            "apply_mode": "resolve-monitor",
            "action_kind": kind,
            "action_id": str(action.get("id") or ""),
            "primary_path": primary_path,
            "affected_paths": [p for p in (primary_path,) if p],
            "follow_up": "标记为已确认并关闭；后续 compile 会刷新 repair plan。",
        }
    if kind not in LOW_RISK_APPLYABLE_ACTION_KINDS:
        return None
    try:
        source_id, concept_slug = validate_low_risk_action_targets(root, action)
    except RuntimeError:
        return None
    primary_path = str(action.get("primary_path") or "")
    secondary_path = str(action.get("secondary_path") or "")
    return {
        "apply_mode": "manual-link-state",
        "state_path": relative_path(root, manual_link_state_path(root)),
        "entry": {
            "source_id": source_id,
            "concept_slug": concept_slug,
            "origin_action_id": str(action.get("id") or ""),
            "active": True,
        },
        "affected_paths": [
            path for path in (primary_path, secondary_path, "wiki/indexes/machine-memory-repair-plan.md") if path
        ],
        "follow_up": "执行后会重跑 compile，让 source/concept/index 层按 manual link state 收敛。",
    }


def validate_low_risk_action_targets(root: Path, action: dict[str, Any]) -> tuple[str, str]:
    if not bool(action.get("active", True)):
        raise RuntimeError("Machine-memory action is no longer active.")
    source_ids = [str(item) for item in action.get("source_ids", []) if isinstance(item, str)]
    concept_slugs = [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)]
    if not source_ids or not concept_slugs:
        raise RuntimeError("Low-risk link action is missing source_ids or concept_slugs.")
    source_id = source_ids[0]
    concept_slug = concept_slugs[0]
    manifest = sync_manifest_with_raw(root)
    known_source_ids = {str(entry.get("id") or "") for entry in manifest.get("entries", []) if isinstance(entry, dict)}
    if source_id not in known_source_ids:
        raise RuntimeError("Low-risk link action references a source that is no longer in the manifest.")
    primary_path = root / str(action.get("primary_path") or "")
    secondary_path = root / str(action.get("secondary_path") or "")
    if not primary_path.is_file() or primary_path.stem != source_id:
        raise RuntimeError("Low-risk link action primary source page is missing or no longer matches the source id.")
    if not secondary_path.is_file() or secondary_path.stem != concept_slug:
        raise RuntimeError(
            "Low-risk link action secondary concept page is missing or no longer matches the concept slug."
        )
    primary_frontmatter = parse_frontmatter(primary_path.read_text(encoding="utf-8", errors="replace"))
    secondary_frontmatter = parse_frontmatter(secondary_path.read_text(encoding="utf-8", errors="replace"))
    if str(primary_frontmatter.get("kind") or "") != "source":
        raise RuntimeError("Low-risk link action primary path is not a source page anymore.")
    if str(secondary_frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Low-risk link action secondary path is not a concept page anymore.")
    return source_id, concept_slug


def describe_machine_memory_action(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    from ..protocol.runtime_config import PENDING_ACTION_STATUSES

    kind = str(action.get("kind") or "")
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    review_prefix = "PYTHONPATH=src python3 -m aiwiki.cli --root . review-queue --bucket mm_actions --json"
    kind_steps = {
        "add-source-concept-link": "检查来源页与概念页是否应补引用或反链。",
        "connect-isolated-source": "把孤立来源接入至少一个稳定概念。",
        "expand-singleton-concept": "扩展单节点概念的相关来源或相关概念。",
        "split-overloaded-concept": "把过载概念拆成更窄的概念页或子主题。",
        "monitor-bridge-concept": "确认桥接概念仍然必要，并记录观察结论。",
        "refresh-citation-snapshots": "刷新 citation snapshot metadata，让 drift / review surface 收敛。",
    }
    next_step = kind_steps.get(kind, "检查这个 machine-memory 动作对应的页面。")
    command_hint = ""
    profile = execution_policy_profile(action, root=root)
    execution_policy = str(profile.get("execution_policy") or "triage")
    execution_band = str(profile.get("execution_band") or "review-first")
    policy_decision = str(profile.get("policy_decision") or "")
    policy_rule_id = str(profile.get("policy_rule_id") or "")
    capabilities = [str(item) for item in profile.get("capabilities", []) if isinstance(item, str) and item]
    action_with_policy = {**action, **profile}
    if not active:
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = review_prefix
    elif status == "proposed":
        command_hint = review_prefix
    elif status == "accepted":
        if action_supports_low_risk_apply(action_with_policy):
            next_step = "这是低风险动作；可以直接通过 safe execution layer 应用，再让 compile 收敛状态。"
            command_hint = review_prefix
        else:
            next_step = f"{next_step} 完成后将动作标为 resolved。"
            command_hint = review_prefix
    elif status == "deferred":
        next_step = "已确认但暂缓处理；准备恢复时改回 accepted。"
        command_hint = review_prefix
    elif status in {"resolved", "rejected"}:
        next_step = "保持关闭，除非修复策略改变。"
    return {
        "execution_policy": execution_policy,
        "execution_band": execution_band,
        "policy_decision": policy_decision,
        "policy_rule_id": policy_rule_id,
        "execution_capabilities": ", ".join(capabilities) if capabilities else "none",
        "execution_capability_list": capabilities,
        "policy_summary": str(profile.get("policy_summary") or ""),
        "next_step": next_step,
        "command_hint": command_hint,
        "apply_ready": "true" if action_supports_low_risk_apply(action_with_policy) else "false",
    }


def placeholder_concept_slugs(root: Path) -> list[str]:
    slugs: list[str] = []
    for page in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if concept_summary_is_placeholder(content):
            slugs.append(page.stem)
    return slugs


def remove_stale_generated_execution_proposal_pages(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_proposals_dir(root)
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if str(frontmatter.get("kind") or "") != "execution-proposal":
            continue
        action_id = str(frontmatter.get("action_id") or "")
        if action_id and action_id in active_action_ids:
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_execution_bundle_files(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_bundles_dir(root)
    if not directory.exists():
        return 0
    active_slugs = {slugify(action_id) for action_id in active_action_ids if action_id}
    for path in sorted(directory.glob("*.json")):
        if path.stem.endswith("-dry-run"):
            continue
        if path.stem in active_slugs:
            continue
        if (directory / f"{path.stem}-dry-run.json").exists():
            continue
        path.unlink()
        removed += 1
    from ..execution.receipts import rotate_execution_dry_runs

    rotate_execution_dry_runs(directory)
    return removed
