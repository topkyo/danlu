"""Machine-memory action, execution policy, patch plan, and repair-plan logic (EP-017C step 4a)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_protocol import (
    DEFAULT_PROTOCOL,
    EXECUTION_BAND_LABELS,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    action_focus_score,
    load_protocol_state,
    protocol_execution_policy_rule,
)
from ..app_state import execution_policy_log_path, execution_receipt_history_path, load_machine_memory_action_state
from ..app_utils import (
    build_citation_snapshots,
    parse_frontmatter,
    relative_path,
    runtime_write_operation,
    sha256_bytes,
    slugify,
)
from .concepts import concept_source_pages, normalize_concept_hardness, parse_causal_links
from .io import source_summary_or_preview


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
    from .. import app_content as _facade
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
        action.setdefault("pending_review", "true" if _facade.action_needs_review(str(action.get("status"))) else "false")
        action.update(_facade.evaluate_page_aging(action, now=now))
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
    decision = str(action.get("policy_decision") or "")
    if decision:
        return decision == "allow"
    kind = str(action.get("kind") or "")
    return kind in LOW_RISK_APPLYABLE_ACTION_KINDS or kind in RESOLVABLE_MONITOR_ACTION_KINDS


def execution_policy_profile(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    if not active:
        return {
            "execution_policy": "inactive-history",
            "execution_band": "history-only",
            "policy_decision": "history",
            "policy_rule_id": "inactive-history",
            "capabilities": ["history"],
            "policy_summary": "信号已消失，只保留历史与审计价值。",
        }
    if status == "proposed":
        return {
            "execution_policy": "triage",
            "execution_band": "review-first",
            "policy_decision": "review",
            "policy_rule_id": "proposed-triage",
            "capabilities": ["review"],
            "policy_summary": "先 review / triage，再决定是否进入 accepted。",
        }
    if status == "accepted":
        if root is not None:
            protocol = str(action.get("protocol") or DEFAULT_PROTOCOL)
            kind = str(action.get("kind") or "")
            rule = protocol_execution_policy_rule(root, protocol, kind)
            if rule:
                return {
                    "execution_policy": str(rule.get("execution_policy") or "manual-repair"),
                    "execution_band": str(rule.get("execution_band") or "manual-repair"),
                    "policy_decision": str(rule.get("decision") or "review"),
                    "policy_rule_id": f"{protocol}:{kind}",
                    "capabilities": [str(item) for item in rule.get("capabilities", []) if isinstance(item, str) and item],
                    "policy_summary": str(rule.get("policy_summary") or ""),
                }
        if action_supports_low_risk_apply(action):
            return {
                "execution_policy": "semi-auto-apply",
                "execution_band": "bundle-safe-apply",
                "policy_decision": "allow",
                "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
                "capabilities": ["dry-run", "bundle-apply", "revert-safe", "history"],
                "policy_summary": "支持 dry-run、bundle-driven apply 和 receipt 驱动回滚。",
            }
        return {
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "policy_decision": "review",
            "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
            "capabilities": ["manual-edit", "review"],
            "policy_summary": "只能走人工修复与 review，不开放 safe apply。",
        }
    if status == "deferred":
        return {
            "execution_policy": "parked",
            "execution_band": "deferred",
            "policy_decision": "history",
            "policy_rule_id": "deferred-parked",
            "capabilities": ["resume-review", "history"],
            "policy_summary": "动作已暂缓，保留复查与恢复入口。",
        }
    return {
        "execution_policy": "closed",
        "execution_band": "closed",
        "policy_decision": "history",
        "policy_rule_id": "closed-history",
        "capabilities": ["history"],
        "policy_summary": "动作已关闭，仅保留审计与历史记录。",
    }


def execution_band_label(band: str) -> str:
    return EXECUTION_BAND_LABELS.get(band, band or "unknown")


PATCH_ROLE_LABELS = {
    "source": "来源页",
    "concept": "概念页",
    "index": "索引页",
    "state": "状态文件",
    "output": "输出页",
    "other": "页面",
}


PATCH_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "add-source-concept-link": {
        "summary": "补 source/concept 双向链接，并把新证据吸收到概念页摘要里。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Related Concepts", "Summary", "Citations"),
                "summary": "在来源页补 concept 引用，并保留 raw/source provenance。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary", "Related Concepts"),
                "summary": "把来源页纳入概念页，并更新 grounded synthesis。",
            },
            "state": {
                "mode": "semi-auto-apply",
                "sections": ("source_to_concept",),
                "summary": "通过 manual-link state 注入低风险补链，让 compile 收敛页面链接。",
            },
        },
    },
    "connect-isolated-source": {
        "summary": "把孤立来源接回稳定概念层，并明确为什么要接入。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Summary", "Related Concepts", "Citations"),
                "summary": "从来源页抽出候选概念并补引用。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary"),
                "summary": "优先把来源接到已有稳定概念，而不是盲目新建概念。",
            },
            "index": {
                "mode": "review",
                "sections": ("Concept Coverage", "Open Questions"),
                "summary": "在索引层确认是否还缺概念覆盖或需要新概念。",
            },
        },
    },
    "expand-singleton-concept": {
        "summary": "扩展单节点概念的来源覆盖，并收紧其适用边界。",
        "roles": {
            "concept": {
                "mode": "update",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "补来源覆盖、显式有限证据，并更新相关概念边界。",
            },
            "index": {
                "mode": "review",
                "sections": ("Rewrite Priority", "Open Questions"),
                "summary": "在概念质量和索引层确认是否需要持续重写或补料。",
            },
        },
    },
    "split-overloaded-concept": {
        "summary": "把过载概念拆成更窄的主题，并把来源重新分流。",
        "roles": {
            "concept": {
                "mode": "rewrite",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "缩窄概念边界、保留拆分说明，并给出后续子概念方向。",
            },
            "index": {
                "mode": "review",
                "sections": ("Merge Candidates", "Rewrite Priority"),
                "summary": "在概念质量层复核拆分理由和后续子概念候选。",
            },
        },
    },
    "monitor-bridge-concept": {
        "summary": "确认桥接概念仍有必要，并记录跨簇连接的理由。",
        "roles": {
            "concept": {
                "mode": "review",
                "sections": ("Summary", "Related Concepts", "Related Sources"),
                "summary": "补 bridge maintenance note，明确为什么这个桥接概念还成立。",
            },
            "index": {
                "mode": "review",
                "sections": ("Bridge Concepts", "Repair Signals"),
                "summary": "在图谱健康层确认桥接信号是否稳定，避免误删关键连接。",
            },
        },
    },
    "refresh-citation-snapshots": {
        "summary": "刷新判断页的 citation snapshot metadata，不改正文结论。",
        "roles": {
            "other": {
                "mode": "semi-auto-apply",
                "sections": ("frontmatter", "Citations"),
                "summary": "重建 citation_snapshots，让 review / drift 检测重新收敛。",
            },
        },
    },
}


PATCH_PLAN_AUXILIARY_PATHS: dict[str, tuple[str, ...]] = {
    "connect-isolated-source": ("wiki/indexes/concepts.md",),
    "expand-singleton-concept": ("wiki/indexes/concept-quality.md",),
    "split-overloaded-concept": ("wiki/indexes/concept-quality.md", "wiki/indexes/rewrite-proposals.md"),
    "monitor-bridge-concept": ("wiki/indexes/graph-health.md",),
}


PROTOCOL_PATCH_HINTS: dict[str, tuple[str, ...]] = {
    "general": (),
    "investing": (
        "同步检查 thesis、risk、catalyst 和 invalidation 页面是否要一起更新。",
    ),
    "research": (
        "同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。",
    ),
    "product": (
        "同步检查 user problem、metric、launch risk 和 validation gap 是否要一起更新。",
    ),
    "ops": (
        "同步检查 incident timeline、blast radius、mitigation 和 follow-up 是否要一起更新。",
    ),
}


def patch_role_for_path(path: str) -> str:
    if path.startswith("wiki/sources/"):
        return "source"
    if path.startswith("wiki/concepts/"):
        return "concept"
    if path.startswith("wiki/indexes/"):
        return "index"
    if path.startswith(".aiwiki/state/"):
        return "state"
    if path.startswith("output/"):
        return "output"
    return "other"


def patch_sections_for_action(kind: str, role: str) -> tuple[str, ...]:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return tuple(roles[role].get("sections", ()))
    fallback = {
        "source": ("Summary", "Citations"),
        "concept": ("Summary", "Related Sources", "Related Concepts"),
        "index": ("Status", "Open Questions"),
        "state": ("state",),
        "output": ("Summary",),
        "other": ("Summary",),
    }
    return fallback.get(role, ("Summary",))


def patch_summary_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("summary") or "")
    return str(template.get("summary") or "检查相关页面并补充修复说明。")


def patch_mode_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("mode") or "update")
    return "update"


def build_page_patch_plan(root: Path, action: dict[str, Any], *, active_protocol: str = DEFAULT_PROTOCOL) -> list[dict[str, Any]]:
    from .. import app_content as _facade
    kind = str(action.get("kind") or "")
    seen_paths: set[str] = set()
    ordered_paths: list[str] = []
    for raw_path in (
        str(action.get("primary_path") or ""),
        str(action.get("secondary_path") or ""),
        *PATCH_PLAN_AUXILIARY_PATHS.get(kind, ()),
    ):
        path = raw_path.strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        ordered_paths.append(path)
    if action_supports_low_risk_apply(action):
        preview = safe_apply_preview(root, action)
        state_path = str(preview.get("state_path") or "") if isinstance(preview, dict) else ""
        if state_path and state_path not in seen_paths:
            seen_paths.add(state_path)
            ordered_paths.append(state_path)

    plan: list[dict[str, Any]] = []
    for path in ordered_paths:
        role = patch_role_for_path(path)
        absolute = root / path
        title = absolute.stem
        if absolute.is_file() and role != "state":
            frontmatter = parse_frontmatter(absolute.read_text(encoding="utf-8", errors="replace"))
            title = str(frontmatter.get("title") or title)
        summary = patch_summary_for_action(kind, role)
        protocol_hints = PROTOCOL_PATCH_HINTS.get(active_protocol, ())
        if protocol_hints and role in {"source", "concept", "index"}:
            summary = f"{summary} {protocol_hints[0]}".strip()
        plan.append(
            {
                "path": path,
                "title": title,
                "role": role,
                "role_label": PATCH_ROLE_LABELS.get(role, role),
                "exists": absolute.is_file(),
                "mode": patch_mode_for_action(kind, role),
                "sections": list(patch_sections_for_action(kind, role)),
                "summary": summary,
                "command_hint": str(action.get("command_hint") or ""),
            }
        )
    return plan


def safe_apply_preview(root: Path, action: dict[str, Any]) -> dict[str, Any] | None:
    from .. import app_content as _facade
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
        source_id, concept_slug = _facade.validate_low_risk_action_targets(root, action)
    except RuntimeError:
        return None
    primary_path = str(action.get("primary_path") or "")
    secondary_path = str(action.get("secondary_path") or "")
    return {
        "apply_mode": "manual-link-state",
        "state_path": relative_path(root, _facade.manual_link_state_path(root)),
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


def execution_policy_decision_record(
    action: dict[str, Any],
    *,
    occurred_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "execution-policy-decision",
        "occurred_at": occurred_at,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or action.get("id") or ""),
        "action_kind": str(action.get("kind") or ""),
        "status": str(action.get("status") or "proposed"),
        "protocol": str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
        "policy_decision": str(action.get("policy_decision") or ""),
        "policy_rule_id": str(action.get("policy_rule_id") or ""),
        "execution_policy": str(action.get("execution_policy") or ""),
        "execution_band": str(action.get("execution_band") or ""),
        "apply_ready": str(action.get("apply_ready") or "false"),
        "active": bool(action.get("active", True)),
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "component_id": str(action.get("component_id") or ""),
    }


def load_execution_policy_decision_history(root: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    path = execution_policy_log_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    records.reverse()
    if limit is None:
        return records
    return records[:limit]


@runtime_write_operation
def append_execution_policy_decisions(root: Path, decisions: list[dict[str, Any]]) -> None:
    if not decisions:
        return
    path = execution_policy_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")


def load_execution_receipt_history(root: Path) -> list[dict[str, Any]]:
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("kind") or "") == "execution-receipt":
            records.append(payload)
    return list(reversed(records))


def remove_stale_generated_execution_proposal_pages(root: Path, active_action_ids: set[str]) -> int:
    from .. import app_content as _facade

    removed = 0
    directory = _facade.execution_proposals_dir(root)
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
    from .. import app_content as _facade

    removed = 0
    directory = _facade.execution_bundles_dir(root)
    if not directory.exists():
        return 0
    active_slugs = {slugify(action_id) for action_id in active_action_ids if action_id}
    for path in sorted(directory.glob("*.json")):
        if path.stem in active_slugs or path.stem.endswith("-dry-run"):
            continue
        if (directory / f"{path.stem}-dry-run.json").exists():
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_markdown_files(directory: Path, active_stems: set[str]) -> int:
    removed = 0
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        if path.stem in active_stems:
            continue
        path.unlink()
        removed += 1
    return removed


def describe_machine_memory_action(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    from .. import app_content as _facade
    action_id = str(action.get("id") or "")
    kind = str(action.get("kind") or "")
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    review_prefix = f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id}"
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
        if status in _facade.PENDING_ACTION_STATUSES:
            command_hint = f'{review_prefix} --status resolved --note "Signal disappeared after compile."'
    elif status == "proposed":
        command_hint = f'{review_prefix} --status accepted --note "Accepted for manual repair."'
    elif status == "accepted":
        if action_supports_low_risk_apply(action_with_policy):
            next_step = "这是低风险动作；可以直接通过 safe execution layer 应用，再让 compile 收敛状态。"
            command_hint = (
                f'PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id}'
                ' --note "Applied accepted low-risk repair."'
            )
        else:
            next_step = f"{next_step} 完成后将动作标为 resolved。"
            command_hint = f'{review_prefix} --status resolved --note "Repair completed."'
    elif status == "deferred":
        next_step = "已确认但暂缓处理；准备恢复时改回 accepted。"
        command_hint = f'{review_prefix} --status accepted --note "Resume deferred repair."'
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


def build_machine_memory_repair_plan(
    root: Path,
    health: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    from .. import app_content as _facade
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
            f"component `{action['component_id']}`" if action.get("component_id") else f"page `{action['primary_path']}`"
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
    execution_proposals = _facade.repair_execution_proposals(
        root,
        ready_actions + triage_actions + deferred_actions,
        active_protocol=active_protocol,
    )
    planner_state = _facade.build_planner_state(root, execution_proposals, active_protocol=active_protocol)

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
