"""Machine-memory action domain logic (EP-017C step 4a).

Split out of ``aiwiki.content.memory``: machine-memory action collection,
signatures, action description, and stale execution-proposal / bundle cleanup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..corpus.parse import concept_source_pages, normalize_concept_hardness, parse_causal_links
from ..corpus.ranks import action_priority_rank, action_status_rank  # noqa: F401  # re-export compat seam
from ..corpus.snapshots import source_summary_or_preview
from ..protocol.focus_scoring import action_focus_score
from ..protocol.state import load_protocol_state
from ..render.paths import (
    execution_bundles_dir,
    execution_proposals_dir,
)
from ..utils.hash import sha256_bytes
from ..utils.markdown import parse_frontmatter
from ..utils.text import slugify
from .action_policy import execution_policy_profile
from .action_state import load_machine_memory_action_state

_EXECUTION_DRY_RUN_KEEP = 20


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


def describe_machine_memory_action(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    from ..protocol.runtime_config import PENDING_ACTION_STATUSES

    kind = str(action.get("kind") or "")
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    review_prefix = "PYTHONPATH=src python3 -m aiwiki.cli --root . advanced review-queue --bucket machine_memory_actions --json"
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
    if not active:
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = review_prefix
    elif status == "proposed":
        command_hint = review_prefix
    elif status == "accepted":
        next_step = f"{next_step} 在 advanced review-queue 查看；完成后将动作标为 resolved。"
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
    }


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
        path.unlink()
        removed += 1
    dry_runs = sorted(directory.glob("*-dry-run.json"))
    if len(dry_runs) > _EXECUTION_DRY_RUN_KEEP:
        for old in dry_runs[: len(dry_runs) - _EXECUTION_DRY_RUN_KEEP]:
            old.unlink(missing_ok=True)
    return removed
