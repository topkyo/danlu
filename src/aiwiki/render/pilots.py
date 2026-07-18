"""Domain-pilot scorecard helpers extracted from app_render.

Symbols:
- domain_pilots_index_path / pilot_scorecards_dir / pilot_scorecard_path
- pilot_stage / domain_pilot_state_scorecard / domain_pilot_scorecard_is_reusable
- domain_pilot_protocol_inputs / domain_pilot_protocol_input_signature
- build_domain_pilot_scorecard
- build_domain_pilots / build_domain_pilots_incremental
- protocol_scorecard
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..app_lifecycle import (
    protocol_related_concept_lifecycle_summary,
    render_knowledge_lifecycle_entry_summary,
)
from ..app_protocol import PROTOCOL_LIBRARY, protocol_title
from ..app_state import (
    DEFAULT_PROTOCOL,
    load_domain_pilot_build_state,
    load_knowledge_lifecycle_state,
    load_material_routing_state,
)
from ..app_utils import relative_path, render_frontmatter, sha256_bytes, slugify
from .packs import pack_workspace_link


def domain_pilots_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def pilot_scorecards_dir(root: Path) -> Path:
    return root / ".aiwiki" / "derived" / "pilots"


def pilot_scorecard_path(root: Path, protocol: str) -> Path:
    return pilot_scorecards_dir(root) / f"{slugify(protocol)}.md"


def pilot_stage(metrics: dict[str, int]) -> tuple[str, str]:
    curated = metrics["decisions"] + metrics["judgments"]
    reviewed = metrics["reviewed"]
    outputs = metrics["outputs"]
    receipts = metrics["receipts"]
    packs = metrics["review_packs"] + metrics["decision_memos"] + metrics["sop_drafts"]
    if curated == 0 and outputs == 0:
        return ("seed", "尚未形成该协议的稳定判断资产。")
    if curated < 2 or reviewed == 0:
        return ("warming-up", "已经开始沉淀，但 reviewed judgment / decision 还偏少。")
    if reviewed < 3 or outputs < 3:
        return ("building", "协议已经起量，但还没进入明显复利。")
    if packs < 2 or receipts == 0:
        return ("active", "判断和 pack 已形成，但执行闭环还不够密。")
    return ("compounding", "已经出现判断、pack、执行和复审的复利迹象。")


def domain_pilot_state_scorecard(scorecard: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in scorecard.items() if key != "content"}


def domain_pilot_scorecard_is_reusable(root: Path, scorecard: dict[str, Any]) -> bool:
    path = str(scorecard.get("path") or "")
    return bool(path) and (root / path).exists()


def domain_pilot_protocol_inputs(
    protocol: str,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    memory: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any],
    material_routing: dict[str, Any],
    active_protocol: str,
) -> dict[str, Any]:
    lifecycle_summary = protocol_related_concept_lifecycle_summary(
        knowledge_lifecycle,
        material_routing,
        protocol=protocol,
    )
    receipt_counts = {
        str(row.get("protocol") or DEFAULT_PROTOCOL): int(row.get("count") or 0)
        for row in execution_audit.get("protocols", [])
        if isinstance(row, dict)
    }
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    execution_proposals = [
        {
            "action_id": str(proposal.get("action_id") or ""),
            "title": str(proposal.get("title") or ""),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "proposal_kind": str(proposal.get("proposal_kind") or ""),
            "summary": str(proposal.get("summary") or ""),
        }
        for proposal in repair_plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == protocol
    ]
    return {
        "protocol": protocol,
        "active_protocol": active_protocol,
        "decisions": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in decisions
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "judgments": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in judgments
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "all_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in all_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "recent_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ][:5],
        "review_packs": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("review_packs", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "decision_memos": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("decision_memos", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "sop_drafts": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
                "risk": str(pack.get("risk") or "medium"),
            }
            for pack in output_packs.get("sop_drafts", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "receipt_count": receipt_counts.get(protocol, 0),
        "execution_proposals": execution_proposals,
        "lifecycle_summary": lifecycle_summary,
    }


def domain_pilot_protocol_input_signature(protocol_inputs: dict[str, Any]) -> str:
    return sha256_bytes(json.dumps(protocol_inputs, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_domain_pilot_scorecard(
    root: Path,
    protocol_inputs: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    protocol = str(protocol_inputs.get("protocol") or DEFAULT_PROTOCOL)
    active_protocol = str(protocol_inputs.get("active_protocol") or DEFAULT_PROTOCOL)
    protocol_decisions = list(protocol_inputs.get("decisions", []) or [])
    protocol_judgments = list(protocol_inputs.get("judgments", []) or [])
    protocol_outputs = list(protocol_inputs.get("all_outputs", []) or [])
    protocol_recent_outputs = list(protocol_inputs.get("recent_outputs", []) or [])
    lifecycle_summary = dict(protocol_inputs.get("lifecycle_summary", {}) or {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    metrics = {
        "decisions": len(protocol_decisions),
        "judgments": len(protocol_judgments),
        "reviewed": sum(
            1
            for page in [*protocol_decisions, *protocol_judgments]
            if str(page.get("reviewed_at") or "") and str(page.get("pending_review") or "") != "true"
        ),
        "pending": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("pending_review") == "true"),
        "overdue": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("overdue_review") == "true"),
        "escalation": sum(
            1 for page in [*protocol_decisions, *protocol_judgments] if page.get("escalation_candidate") == "true"
        ),
        "outputs": len(protocol_outputs),
        "review_packs": len(list(protocol_inputs.get("review_packs", []) or [])),
        "decision_memos": len(list(protocol_inputs.get("decision_memos", []) or [])),
        "sop_drafts": len(list(protocol_inputs.get("sop_drafts", []) or [])),
        "receipts": int(protocol_inputs.get("receipt_count", 0) or 0),
        "execution_proposals": len(list(protocol_inputs.get("execution_proposals", []) or [])),
        "lifecycle_concept_backlog": int(lifecycle_counts.get("concept_backlog", 0) or 0),
        "lifecycle_retired_concepts": int(lifecycle_counts.get("retired_concepts", 0) or 0),
        "lifecycle_dominant_concepts": int(lifecycle_counts.get("dominant_related_concepts", 0) or 0),
        "lifecycle_mixed_concepts": int(lifecycle_counts.get("mixed_related_concepts", 0) or 0),
        "lifecycle_bridge_concepts": int(lifecycle_counts.get("ambiguity_bridge_concepts", 0) or 0),
    }
    stage, stage_summary = pilot_stage(metrics)
    gaps: list[str] = []
    if lifecycle_counts.get("concept_backlog", 0):
        gaps.append(
            f"有 `{lifecycle_counts.get('concept_backlog', 0)}` 个 protocol-related lifecycle concept backlog 尚未收敛。"
        )
    ambiguity_count = int(lifecycle_counts.get("mixed_related_concepts", 0)) + int(
        lifecycle_counts.get("ambiguity_bridge_concepts", 0)
    )
    if ambiguity_count:
        gaps.append(f"有 `{ambiguity_count}` 个 protocol-related concept 仍处于 mixed / bridge ambiguity，需要人工校准归属。")
    if metrics["decisions"] + metrics["judgments"] == 0:
        gaps.append("还没有该协议的 `decision / judgment` 资产。")
    if metrics["reviewed"] == 0:
        gaps.append("还没有 reviewed judgment / decision。")
    if metrics["outputs"] < 2:
        gaps.append("可回流 outputs 还不够密。")
    if metrics["pending"] > metrics["reviewed"]:
        gaps.append("待审页面多于已审资产。")
    if metrics["review_packs"] == 0 and metrics["pending"] > 0:
        gaps.append("需要先把 pending review 炼成 review packs。")
    if metrics["decision_memos"] == 0 and metrics["reviewed"] > 0:
        gaps.append("已审判断还没有形成 decision memos。")
    if metrics["sop_drafts"] == 0 and metrics["execution_proposals"] > 0:
        gaps.append("执行提案还没有形成 SOP drafts。")
    if metrics["receipts"] == 0 and metrics["sop_drafts"] > 0:
        gaps.append("还没有 execution receipt，可先从 dry-run / low-risk apply 开始。")
    next_moves = [
        PROTOCOL_LIBRARY[protocol]["focus"][0],
        PROTOCOL_LIBRARY[protocol]["review"][0],
        PROTOCOL_LIBRARY[protocol]["nightly"][0],
    ]
    if gaps:
        next_moves.insert(0, gaps[0])
    destination = pilot_scorecard_path(root, protocol)
    frontmatter_text = render_frontmatter(
        {
            "id": f"pilot-scorecard-{slugify(protocol)}",
            "kind": "pilot-scorecard",
            "title": f"{protocol_title(protocol)} Pilot Scorecard",
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter_text,
        "",
        f"# {protocol_title(protocol)} Pilot Scorecard",
        "",
        "## Overview",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Stage: `{stage}`",
        f"- Summary: {stage_summary}",
        f"- 当前协议是否 active：`{'yes' if protocol == active_protocol else 'no'}`",
        "",
        "## Density Snapshot",
        f"- Decisions / Judgments: `{metrics['decisions']}` / `{metrics['judgments']}`",
        f"- Reviewed / Pending: `{metrics['reviewed']}` / `{metrics['pending']}`",
        f"- Overdue / Escalation: `{metrics['overdue']}` / `{metrics['escalation']}`",
        f"- Outputs: `{metrics['outputs']}`",
        f"- Review packs / Decision memos / SOP drafts: `{metrics['review_packs']}` / `{metrics['decision_memos']}` / `{metrics['sop_drafts']}`",
        f"- Execution proposals / Receipts: `{metrics['execution_proposals']}` / `{metrics['receipts']}`",
        f"- Protocol-related lifecycle backlog / retired concepts: `{metrics['lifecycle_concept_backlog']}` / `{metrics['lifecycle_retired_concepts']}`",
        "",
        "## Protocol Focus",
        *[f"- {line}" for line in PROTOCOL_LIBRARY[protocol]["focus"]],
        "",
        "## Gaps",
    ]
    if not gaps:
        lines.append("- 当前没有明显结构性缺口。")
    else:
        lines.extend(f"- {gap}" for gap in gaps)
    lines.extend(
        [
            "",
            "## Lifecycle Governance",
            "- 以下 concept lifecycle 摘要优先统计 supporting sources 的 `material-routing top_protocols` 首位命中；若来源在当前协议仍是 `warm/hot evidence`，或属于 `cross_protocol_bridge` 且当前协议仍位于 top2，也会保守纳入。",
            f"- Inference mode: `{lifecycle_summary.get('inference_mode', 'unknown')}`",
            f"- Ambiguity mode: `{lifecycle_summary.get('ambiguity_mode', 'unknown')}`",
            f"- Related direct / secondary / bridge concepts: `{lifecycle_counts.get('direct_related_concepts', 0)}` / `{lifecycle_counts.get('secondary_related_concepts', 0)}` / `{lifecycle_counts.get('bridge_related_concepts', 0)}`",
            f"- Related dominant / mixed / bridge concepts: `{lifecycle_counts.get('dominant_related_concepts', 0)}` / `{lifecycle_counts.get('mixed_related_concepts', 0)}` / `{lifecycle_counts.get('ambiguity_bridge_concepts', 0)}`",
            f"- Related review concepts: `{lifecycle_counts.get('review_concepts', 0)}`",
            f"- Related revisit concepts: `{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- Related retired concepts: `{lifecycle_counts.get('retired_concepts', 0)}`",
            f"- Related active concepts: `{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Protocol Ambiguity Watchlist",
        ]
    )
    if not lifecycle_summary.get("ambiguity_watchlist"):
        lines.append("- 当前没有 mixed / bridge ambiguity concept。")
    else:
        lines.append("- 以下概念仍需要人工判断是当前协议主归属、混合归属，还是桥接归属。")
        for entry in lifecycle_summary.get("ambiguity_watchlist", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Lifecycle Concept Backlog"])
    if not lifecycle_summary.get("concept_backlog"):
        lines.append("- 当前没有 protocol-related lifecycle concept backlog。")
    else:
        for entry in lifecycle_summary.get("concept_backlog", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Retired Concepts"])
    if not lifecycle_summary.get("retired_concepts"):
        lines.append("- 当前没有 protocol-related retired concept。")
    else:
        for entry in lifecycle_summary.get("retired_concepts", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Next Moves"])
    lines.extend(f"- {item}" for item in next_moves[:5])
    lines.extend(["", "## Recent Outputs"])
    if not protocol_recent_outputs:
        lines.append("- 当前没有最近 output。")
    else:
        for artifact in protocol_recent_outputs:
            lines.append(
                f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )
    lines.extend(
        [
            "",
            "## Related Links",
            f"- {pack_workspace_link(f'schema/protocols/{protocol}/index.md', f'{protocol_title(protocol)} 协议规则')}",
            "- [协议总览](../../../wiki/indexes/protocols.md)",
            "- [输出 Pack 总览](../../../wiki/indexes/output-packs.md)",
            "- [审阅中心](../../../wiki/indexes/review-center.md)",
        ]
    )
    return {
        "protocol": protocol,
        "title": f"{protocol_title(protocol)} Pilot Scorecard",
        "path": relative_path(root, destination),
        "content": "\n".join(lines) + "\n",
        "stage": stage,
        "summary": stage_summary,
        "metrics": metrics,
        "lifecycle_summary": lifecycle_summary,
    }


def build_domain_pilots(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = (
        root,
        decisions,
        judgments,
        memory,
        recent_outputs,
        all_outputs,
        output_packs,
        execution_audit,
        knowledge_lifecycle,
        material_routing,
    )
    active_protocol = str(protocol_state.get("active_protocol") or DEFAULT_PROTOCOL)
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "scorecards": [],
    }


def build_domain_pilots_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ = (
        root,
        decisions,
        judgments,
        memory,
        recent_outputs,
        all_outputs,
        output_packs,
        execution_audit,
        knowledge_lifecycle,
        material_routing,
    )
    active_protocol = str(protocol_state.get("active_protocol") or DEFAULT_PROTOCOL)
    return {
        "domain_pilots": {
            "compiled_at": compiled_at,
            "active_protocol": active_protocol,
            "scorecards": [],
        },
        "state_document": {
            "version": 1,
            "generated_at": compiled_at,
            "active_protocol": active_protocol,
            "protocol_records": {},
            "scorecards": [],
        },
        "dirty_protocols": [],
        "clean_protocols": [],
        "removed_protocols": [],
    }


def protocol_scorecard(domain_pilots: dict[str, Any], protocol: str) -> dict[str, Any]:
    for scorecard in domain_pilots.get("scorecards", []):
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "") == protocol:
            return scorecard
    return {}
