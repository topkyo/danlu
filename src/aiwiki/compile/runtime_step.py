"""Compile runtime step owner."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..app_compile_ops import render_protocols_dashboard
from ..app_content import (
    append_execution_policy_decisions,
    build_concept_quality,
    build_knowledge_lifecycle_document,
    collect_aging_signals,
    entry_ids_from_paths,
    entry_lookup_maps,
    execution_policy_decision_record,
)
from ..app_content import (
    build_machine_memory_repair_plan as build_machine_memory_repair_plan_memory,
)
from ..app_memory import (
    append_machine_memory_history,
    attach_judgment_assets_to_machine_memory,
    build_execution_audit_snapshot,
    build_machine_memory_graph,
    build_machine_memory_health,
    build_material_state_documents,
    machine_memory_digest,
    machine_memory_snapshot_is_reusable,
    plan_machine_memory_build,
    reconcile_concept_rewrite_proposals,
    reconcile_machine_memory_actions,
    reuse_machine_memory_core,
    summarize_machine_memory_transition,
)
from ..app_protocol import DEFAULT_DASHBOARD_FILES, MANAGED_DASHBOARD_TEMPLATE_FILES
from ..app_state import (
    DEFAULT_PROTOCOL,
    append_runtime_history,
    archive_candidates_state_path,
    default_machine_memory_build_state,
    default_ranking_build_state,
    knowledge_lifecycle_state_path,
    machine_memory_actions_path,
    machine_memory_build_state_path,
    machine_memory_graph_html_path,
    machine_memory_graph_path,
    machine_memory_history_path,
    machine_memory_repair_plan_path,
    machine_memory_state_path,
    machine_memory_topology_path,
    material_routing_state_path,
    material_state_path,
    planner_state_path,
    query_route_telemetry_path,
    ranking_build_state_path,
)
from ..app_utils import (
    parse_frontmatter,
    parse_iso_datetime,
    relative_path,
    strip_frontmatter,
    tokenize,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..memory.execution_surfaces import (
    render_execution_audit,
    render_execution_center,
)
from ..memory.graph import collect_report_anchors, render_machine_memory_graph_html
from ..memory.status import (
    render_drift_report,
    render_graph_health,
    render_machine_memory_actions,
    render_machine_memory_index,
    render_machine_memory_repair_plan,
)
from ..memory.topology import render_machine_memory_topology
from .context import CompileContext

logger = logging.getLogger(__name__)


def _curated_page_scan_record(root: Path, page: dict[str, str]) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [
        str(path)
        for path in frontmatter.get("citations", [])
        if isinstance(path, str) and path.strip()
    ]
    tokens = set(tokenize(f"{page.get('title', '')}\n{strip_frontmatter(content)}"))
    return {
        "citations": citations,
        "frontmatter": frontmatter,
        "tokens": tokens,
    }


def _candidate_is_covered_by_review(
    scan_record: dict[str, Any],
    source_entry: dict[str, Any],
) -> bool:
    frontmatter = scan_record.get("frontmatter", {})
    if not isinstance(frontmatter, dict):
        return False
    status = str(frontmatter.get("status") or "")
    if status not in {"approved", "confirmed"}:
        return False
    reviewed_at = parse_iso_datetime(
        str(frontmatter.get("last_reviewed") or frontmatter.get("reviewed_at") or "")
    )
    source_updated_at = parse_iso_datetime(
        str(source_entry.get("updated_at") or source_entry.get("imported_at") or "")
    )
    if reviewed_at is None or source_updated_at is None:
        return False
    return reviewed_at > source_updated_at


def _counter_evidence_scan_phase(context: CompileContext) -> dict[str, Any]:
    entry_by_id = {str(entry["id"]): entry for entry in context.entries}
    source_ids = [source_id for source_id in context.dirty_source_ids if source_id in entry_by_id]
    if not source_ids:
        previous_scan = context.previous_memory.get("health", {}).get("counter_evidence_scan", {})
        if isinstance(previous_scan, dict):
            source_ids = [
                str(candidate.get("source_id") or "")
                for candidate in previous_scan.get("candidates", [])
                if isinstance(candidate, dict) and str(candidate.get("source_id") or "") in entry_by_id
            ]
            source_ids = list(dict.fromkeys(source_ids))
    if not source_ids:
        return {"generated_at": context.compiled_at, "candidate_count": 0, "candidates": [], "pages": []}
    path_to_entry_id = entry_lookup_maps(context.manifest.get("entries", []))[1]
    candidates: list[dict[str, Any]] = []
    page_summaries: list[dict[str, Any]] = []
    for page in context.decision_pages + context.judgment_pages:
        scan_record = _curated_page_scan_record(context.root, page)
        cited_source_ids = set(entry_ids_from_paths(path_to_entry_id, scan_record["citations"]))
        page_candidates: list[dict[str, Any]] = []
        for source_id in source_ids:
            if source_id in cited_source_ids:
                continue
            source_entry = entry_by_id.get(source_id, {})
            if _candidate_is_covered_by_review(scan_record, source_entry):
                continue
            source_terms = {
                token
                for label in context.entry_terms.get(source_id, [])
                for token in tokenize(label)
            }
            source_terms.update(tokenize(f"{source_entry.get('title', '')}\n{context.previews.get(source_id, '')}"))
            overlap = sorted(source_terms & scan_record["tokens"])
            if len(overlap) < 2:
                continue
            candidate = {
                "candidate_id": f"{page.get('page_id', '')}:{source_id}",
                "page_id": str(page.get("page_id") or ""),
                "page_path": str(page.get("path") or ""),
                "page_title": str(page.get("title") or ""),
                "page_kind": str(page.get("kind") or ""),
                "page_status": str(page.get("status") or ""),
                "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                "source_id": source_id,
                "source_title": str(source_entry.get("title") or source_id),
                "source_page": f"wiki/sources/{source_id}.md",
                "shared_terms": overlap[:8],
                "shared_term_count": len(overlap),
                "reason_code": "counter-evidence-candidate",
            }
            page_candidates.append(candidate)
            candidates.append(candidate)
        if page_candidates:
            page_summaries.append(
                {
                    "page_id": str(page.get("page_id") or ""),
                    "page_path": str(page.get("path") or ""),
                    "page_title": str(page.get("title") or ""),
                    "page_kind": str(page.get("kind") or ""),
                    "page_status": str(page.get("status") or ""),
                    "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                    "candidate_count": len(page_candidates),
                    "source_ids": [candidate["source_id"] for candidate in page_candidates],
                    "source_pages": [candidate["source_page"] for candidate in page_candidates],
                    "shared_terms": sorted(
                        {
                            term
                            for candidate in page_candidates
                            for term in candidate.get("shared_terms", [])
                        }
                    )[:10],
                }
            )
    candidates.sort(
        key=lambda item: (
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("shared_term_count", 0)),
            str(item.get("page_title") or "").lower(),
            str(item.get("source_title") or "").lower(),
        )
    )
    page_summaries.sort(
        key=lambda item: (
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("candidate_count", 0)),
            str(item.get("page_title") or "").lower(),
        )
    )
    return {
        "generated_at": context.compiled_at,
        "candidate_count": len(candidates),
        "candidates": candidates[:32],
        "pages": page_summaries[:16],
    }


def _append_counter_evidence_runtime_history(context: CompileContext, counter_evidence_scan: dict[str, Any]) -> None:
    dirty_source_ids = {source_id for source_id in context.dirty_source_ids if isinstance(source_id, str) and source_id}
    if not dirty_source_ids:
        return

    candidates = counter_evidence_scan.get("candidates")
    if not isinstance(candidates, list):
        return

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_id = candidate.get("source_id")
        candidate_id = candidate.get("candidate_id")
        protocol = candidate.get("protocol")
        if not isinstance(source_id, str) or source_id not in dirty_source_ids:
            continue
        if not isinstance(candidate_id, str) or not candidate_id:
            continue
        if not isinstance(protocol, str) or not protocol:
            continue
        append_runtime_history(
            context.root,
            {
                "event_type": "counter-evidence",
                "occurred_at": context.compiled_at,
                "protocol": protocol,
                "candidate_id": candidate_id,
                "page_id": candidate.get("page_id"),
                "page_path": candidate.get("page_path"),
                "page_kind": candidate.get("page_kind"),
                "page_status": candidate.get("page_status"),
                "source_ids": [source_id],
                "source_page": candidate.get("source_page"),
                "shared_terms": candidate.get("shared_terms"),
                "shared_term_count": candidate.get("shared_term_count"),
                "reason_code": candidate.get("reason_code"),
                "emitted_by": "compile",
            },
        )


def _build_judgment_review_actions(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    aging: dict[str, list[dict[str, str]]],
    counter_evidence_scan: dict[str, Any],
) -> list[dict[str, Any]]:
    from ..app_content import curated_page_transition_profile
    from ..app_utils import slugify

    page_by_path = {
        str(page.get("path") or ""): page
        for page in decisions + judgments
        if str(page.get("path") or "")
    }
    action_by_path: dict[str, dict[str, Any]] = {}
    priority_rank = {"high": 0, "medium": 1, "low": 2}

    def add_action(page: dict[str, str], reason_code: str, *, priority: str, candidate_count: int = 0) -> None:
        page_path = str(page.get("path") or "")
        if not page_path:
            return
        current = action_by_path.get(page_path)
        if current is None:
            profile = curated_page_transition_profile(
                str(page.get("kind") or ""),
                str(page.get("status") or ""),
            )
            default_transition = str(profile.get("default_transition") or page.get("status") or "")
            current = {
                "id": f"review-{slugify(str(page.get('page_id') or Path(page_path).stem))}",
                "title": f"Review {str(page.get('title') or Path(page_path).stem)}",
                "page_id": str(page.get("page_id") or Path(page_path).stem),
                "page_path": page_path,
                "page_kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or DEFAULT_PROTOCOL),
                "status": "open",
                "priority": priority,
                "reason_codes": [],
                "candidate_count": 0,
                "review_command": (
                    f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page_path} --status {default_transition}"
                    if default_transition
                    else ""
                ),
            }
            action_by_path[page_path] = current
        if reason_code and reason_code not in current["reason_codes"]:
            current["reason_codes"].append(reason_code)
        current["candidate_count"] = max(int(current.get("candidate_count", 0)), candidate_count)
        if priority_rank.get(priority, 9) < priority_rank.get(str(current.get("priority") or "medium"), 9):
            current["priority"] = priority

    for page in aging.get("escalated", []):
        add_action(page, "escalation-candidate", priority="high")
    for page in aging.get("overdue", []):
        add_action(page, "overdue-review", priority="high" if page.get("kind") == "judgment" else "medium")
    for candidate in counter_evidence_scan.get("pages", []):
        if not isinstance(candidate, dict):
            continue
        page = page_by_path.get(str(candidate.get("page_path") or ""))
        if page is None:
            continue
        add_action(
            page,
            "counter-evidence-candidate",
            priority="high" if int(candidate.get("candidate_count", 0) or 0) > 1 else "medium",
            candidate_count=int(candidate.get("candidate_count", 0) or 0),
        )
    actions = list(action_by_path.values())
    actions.sort(
        key=lambda item: (
            priority_rank.get(str(item.get("priority") or "medium"), 9),
            0 if item.get("page_kind") == "judgment" else 1,
            -int(item.get("candidate_count", 0) or 0),
            str(item.get("title") or "").lower(),
        )
    )
    return actions


def _judgment_relation_signatures(memory: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    return {
        ("judgment", str(edge.get("relation") or "related"), str(edge.get("from") or ""), str(edge.get("to") or ""))
        for edge in memory.get("edges", {}).get("judgment_to_judgment", [])
        if edge.get("from") and edge.get("to")
    } | {
        ("decision", str(edge.get("relation") or "supports"), str(edge.get("from") or ""), str(edge.get("to") or ""))
        for edge in memory.get("edges", {}).get("judgment_to_decision", [])
        if edge.get("from") and edge.get("to")
    }


def _judgment_relation_descriptor(
    signature: tuple[str, str, str, str],
    node_map: dict[str, dict[str, Any]],
) -> dict[str, str]:
    relation_kind, relation, source_id, target_id = signature
    source = node_map.get(source_id, {})
    target = node_map.get(target_id, {})
    return {
        "relation_kind": relation_kind,
        "relation": relation,
        "source_id": source_id,
        "source_title": str(source.get("title") or source_id),
        "source_path": str(source.get("path") or ""),
        "target_id": target_id,
        "target_title": str(target.get("title") or target_id),
        "target_path": str(target.get("path") or ""),
    }


def _append_judgment_relation_history_event(
    root: Path,
    previous_memory: dict[str, Any],
    current_memory: dict[str, Any],
    *,
    occurred_at: str,
) -> None:
    from ..app_state import append_runtime_history

    previous_signatures = _judgment_relation_signatures(previous_memory)
    current_signatures = _judgment_relation_signatures(current_memory)
    added = sorted(current_signatures - previous_signatures)
    removed = sorted(previous_signatures - current_signatures)
    if not added and not removed:
        return
    previous_nodes = {
        str(node.get("page_id") or ""): node
        for node in previous_memory.get("judgment_nodes", [])
        if isinstance(node, dict) and node.get("page_id")
    }
    current_nodes = {
        str(node.get("page_id") or ""): node
        for node in current_memory.get("judgment_nodes", [])
        if isinstance(node, dict) and node.get("page_id")
    }
    append_runtime_history(
        root,
        {
            "event_type": "judgment-relation-refresh",
            "occurred_at": occurred_at,
            "added_relations": [_judgment_relation_descriptor(signature, current_nodes) for signature in added[:12]],
            "removed_relations": [_judgment_relation_descriptor(signature, previous_nodes) for signature in removed[:12]],
        },
    )


def compile_runtime_phase(context: CompileContext) -> None:
    from .. import app_compile as compile_facade

    # Round 51: managed static dashboard templates are runtime-owned. Refresh
    # them via CompileContext so compile status accounts for the write.
    # Dynamic owner pages are intentionally excluded here and are written by
    # their dedicated renderers later in the pipeline.
    for relative in MANAGED_DASHBOARD_TEMPLATE_FILES:
        content = DEFAULT_DASHBOARD_FILES[relative]
        context.write_index_artifact(context.root / relative, content)

    machine_memory_build = plan_machine_memory_build(
        context.root,
        context.entries,
        context.concepts,
        context.previews,
        context.entry_terms,
        generated_at=context.compiled_at,
    )
    machine_memory_build_state = machine_memory_build.get("state_document", {})
    if not isinstance(machine_memory_build_state, dict):
        machine_memory_build_state = default_machine_memory_build_state()
    try:
        write_json_document_if_changed_ignoring_generated_timestamps(
            machine_memory_build_state_path(context.root),
            machine_memory_build_state,
        )
    except OSError as exc:
        logger.warning("cache machine-memory build-state save failed: %s", exc)
    context.dirty_machine_memory_source_ids = list(machine_memory_build.get("dirty_source_ids", []))
    context.clean_machine_memory_source_ids = list(machine_memory_build.get("clean_source_ids", []))
    context.dirty_machine_memory_concept_slugs = list(machine_memory_build.get("dirty_concept_slugs", []))
    context.clean_machine_memory_concept_slugs = list(machine_memory_build.get("clean_concept_slugs", []))
    context.machine_memory_core_reused = bool(
        machine_memory_build.get("inputs_clean")
        and machine_memory_snapshot_is_reusable(context.previous_memory)
    )
    if context.machine_memory_core_reused:
        context.memory = reuse_machine_memory_core(context.previous_memory, context.compiled_at)
    else:
        context.memory = compile_facade.build_machine_memory(
            context.root,
            context.entries,
            context.concepts,
            context.previews,
            context.entry_terms,
            context.compiled_at,
        )
    context.memory = attach_judgment_assets_to_machine_memory(
        context.root,
        context.memory,
        context.decision_pages,
        context.judgment_pages,
    )
    context.memory["health"] = build_machine_memory_health(context.memory)
    context.memory["health"].update(
        reconcile_machine_memory_actions(
            context.root,
            context.memory["health"],
            compiled_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        )
    )
    context.memory["health"]["repair_plan"] = build_machine_memory_repair_plan_memory(
        context.root,
        context.memory["health"],
        active_protocol=context.protocol_state["active_protocol"],
    )
    planner_state = dict(context.memory["health"]["repair_plan"].get("planner_state") or {})
    planner_state["state_path"] = relative_path(context.root, planner_state_path(context.root))
    planner_state["generated_at"] = str(planner_state.get("generated_at") or context.compiled_at)
    context.memory["health"]["repair_plan"]["planner_state"] = planner_state
    context.write_maintenance_artifact(planner_state_path(context.root), planner_state)

    route_telemetry_path = query_route_telemetry_path(context.root)
    route_telemetry = {}
    if route_telemetry_path.exists():
        try:
            route_telemetry = json.loads(route_telemetry_path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            route_telemetry = {}
    if not isinstance(route_telemetry, dict):
        route_telemetry = {}
    route_telemetry.setdefault("version", 1)
    route_telemetry.setdefault("entries", [])
    route_telemetry.setdefault("strategy_counts", {})
    route_telemetry.setdefault("protocol_counts", {})
    route_telemetry.setdefault("last_entry", {})
    route_telemetry["updated_at"] = str(route_telemetry.get("updated_at") or context.compiled_at)
    route_telemetry["state_path"] = relative_path(context.root, route_telemetry_path)
    context.write_maintenance_artifact(route_telemetry_path, route_telemetry)

    policy_decisions = [
        execution_policy_decision_record(
            action,
            occurred_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        )
        for action in [
            *context.memory["health"].get("actions", []),
            *context.memory["health"].get("inactive_actions", []),
        ]
        if isinstance(action, dict) and action.get("id")
    ]
    append_execution_policy_decisions(context.root, policy_decisions)
    context.memory["health"]["concept_quality"] = build_concept_quality(context.root, context.memory)
    context.memory["health"]["concept_rewrite"] = reconcile_concept_rewrite_proposals(
        context.root,
        context.memory["health"]["concept_quality"],
        compiled_at=context.compiled_at,
    )
    aging = collect_aging_signals(
        context.decision_pages,
        context.judgment_pages,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.memory["health"]["counter_evidence_scan"] = _counter_evidence_scan_phase(context)
    _append_counter_evidence_runtime_history(context, context.memory["health"]["counter_evidence_scan"])
    context.memory["health"]["judgment_review_actions"] = _build_judgment_review_actions(
        context.decision_pages,
        context.judgment_pages,
        aging=aging,
        counter_evidence_scan=context.memory["health"]["counter_evidence_scan"],
    )
    context.memory["digest"] = machine_memory_digest(context.memory)
    graph = build_machine_memory_graph(context.memory, root=context.root)
    context.memory["graph_digest"] = graph["digest"]
    context.memory["graph_path"] = relative_path(context.root, machine_memory_graph_path(context.root))
    context.memory["history_path"] = relative_path(context.root, machine_memory_history_path(context.root))
    context.transition = summarize_machine_memory_transition(context.previous_memory, context.memory)
    context.memory["transition"] = context.transition
    _append_judgment_relation_history_event(
        context.root,
        context.previous_memory,
        context.memory,
        occurred_at=context.compiled_at,
    )
    context.write_index_artifact(
        machine_memory_state_path(context.root),
        json.dumps(context.memory, indent=2, sort_keys=True) + "\n",
    )
    context.write_index_artifact(
        machine_memory_graph_path(context.root),
        json.dumps(graph, indent=2, sort_keys=True) + "\n",
    )
    report_anchors = collect_report_anchors(context.root)
    context.write_index_artifact(
        machine_memory_graph_html_path(context.root),
        render_machine_memory_graph_html(context.memory, graph, report_anchors=report_anchors),
    )
    append_machine_memory_history(context.root, context.memory, context.transition)
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "machine-memory.md",
        render_machine_memory_index(context.memory),
    )
    context.write_index_artifact(machine_memory_topology_path(context.root), render_machine_memory_topology(context.memory))
    context.write_index_artifact(machine_memory_actions_path(context.root), render_machine_memory_actions(context.memory))
    context.write_index_artifact(
        machine_memory_repair_plan_path(context.root),
        render_machine_memory_repair_plan(context.memory),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "execution-center.md",
        render_execution_center(
            context.root,
            context.memory,
            compiled_at=context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
        ),
    )
    context.execution_audit = build_execution_audit_snapshot(
        context.root,
        context.memory,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "execution-audit.md",
        render_execution_audit(context.execution_audit),
    )

    ranking_build = compile_facade.build_ranking_state(
        context.root,
        context.entries,
        context.concepts,
        generated_at=context.compiled_at,
    )
    ranking_build_state = ranking_build.get("state_document", {})
    if not isinstance(ranking_build_state, dict):
        ranking_build_state = default_ranking_build_state()
    try:
        write_json_document_if_changed_ignoring_generated_timestamps(
            ranking_build_state_path(context.root),
            ranking_build_state,
        )
    except OSError as exc:
        logger.warning("cache ranking build-state save failed: %s", exc)
    context.dirty_ranking_source_ids = list(ranking_build.get("dirty_source_ids", []))
    context.clean_ranking_source_ids = list(ranking_build.get("clean_source_ids", []))
    context.dirty_ranking_concept_slugs = list(ranking_build.get("dirty_concept_slugs", []))
    context.clean_ranking_concept_slugs = list(ranking_build.get("clean_concept_slugs", []))

    from ..app_content import collect_output_density_artifacts, collect_recent_output_artifacts

    context.all_outputs = collect_output_density_artifacts(context.root)
    context.recent_outputs = collect_recent_output_artifacts(context.root)
    material_state_documents = build_material_state_documents(
        context.root,
        generated_at=context.compiled_at,
        entries=context.entries,
        active_protocol=context.protocol_state["active_protocol"],
    )
    context.active_corpora_state = material_state_documents["active_corpora_state"]
    context.material_state = material_state_documents["material_state"]
    context.material_routing = material_state_documents["material_routing"]
    context.archive_candidates = material_state_documents["archive_candidates"]
    context.knowledge_lifecycle = build_knowledge_lifecycle_document(
        context.root,
        generated_at=context.compiled_at,
        decisions=context.decision_pages,
        judgments=context.judgment_pages,
        entries=context.entries,
        active_corpora_state=context.active_corpora_state,
        memory=context.memory,
    )
    context.write_maintenance_artifact(material_state_path(context.root), context.material_state)
    context.write_maintenance_artifact(material_routing_state_path(context.root), context.material_routing)
    context.write_maintenance_artifact(archive_candidates_state_path(context.root), context.archive_candidates)
    context.write_maintenance_artifact(knowledge_lifecycle_state_path(context.root), context.knowledge_lifecycle)
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "protocols.md",
        render_protocols_dashboard(
            context.root,
            context.compiled_at,
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )


__all__ = ["compile_runtime_phase"]
