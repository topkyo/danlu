"""Compile output step owner."""

from __future__ import annotations

from ..app_shell import build_shell_summary, write_shell_summary
from ..app_state import (
    aging_report_path,
    cognitive_history_path,
    concept_quality_path,
    concept_rewrite_index_path,
    default_output_pack_build_state,
    graph_health_report_path,
    machine_memory_drift_report_path,
)
from ..content.io import (
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
)
from ..memory.execution_surfaces import (
    render_concept_quality,
    render_concept_rewrite_index,
    render_concept_rewrite_proposal_page,
)
from ..memory.status import (
    render_drift_report,
    render_graph_health,
)
from ..render.cognitive_history import render_cognitive_history
from ..render.furnace_center import render_furnace_center
from ..render.views import (
    render_aging_report,
    render_review_queue,
)
from .context import CompileContext


def compile_output_phase(context: CompileContext) -> None:
    # W4 surface cut (A30): auto output pack / slides / figure factory retired.
    context.all_outputs = collect_output_density_artifacts(context.root)
    context.recent_outputs = collect_recent_output_artifacts(context.root)

    context.output_packs = default_output_pack_build_state()
    context.dirty_output_pack_groups = []
    context.clean_output_pack_groups = []

    context.domain_pilots = {
        "compiled_at": context.compiled_at,
        "active_protocol": context.protocol_state["active_protocol"],
        "scorecards": [],
    }
    context.dirty_domain_pilot_protocols = []
    context.clean_domain_pilot_protocols = []

    # W4 surface cut (A30/A39): agent workbench + derived agent packs retired.
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "furnace-center.md",
        render_furnace_center(
            context.decision_pages,
            context.judgment_pages,
            context.memory,
            context.compiled_at,
            context.protocol_state,
            context.recent_outputs,
            context.output_packs,
            context.domain_pilots,
            context.execution_audit,
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    # W4 surface cut (A31): local control HTML centers retired; Product Shell is the UI.
    context.write_index_artifact(concept_quality_path(context.root), render_concept_quality(context.memory))
    context.write_index_artifact(
        concept_rewrite_index_path(context.root),
        render_concept_rewrite_index(context.memory["health"]["concept_rewrite"], context.compiled_at),
    )
    for proposal in context.memory["health"]["concept_rewrite"].get("all_proposals", []):
        context.write_index_artifact(
            context.root / proposal["proposal_path"],
            render_concept_rewrite_proposal_page(proposal),
        )
    context.write_index_artifact(graph_health_report_path(context.root), render_graph_health(context.memory))
    context.write_index_artifact(
        machine_memory_drift_report_path(context.root),
        render_drift_report(context.memory, context.transition),
    )
    context.write_index_artifact(
        context.root / "wiki" / "indexes" / "review-queue.md",
        render_review_queue(
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
            counter_evidence_scan=context.memory.get("health", {}).get("counter_evidence_scan", {}),
        ),
    )
    context.write_index_artifact(
        cognitive_history_path(context.root),
        render_cognitive_history(
            context.root,
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    context.write_index_artifact(
        aging_report_path(context.root),
        render_aging_report(
            context.decision_pages,
            context.judgment_pages,
            context.compiled_at,
            active_protocol=context.protocol_state["active_protocol"],
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    write_shell_summary(context.root, build_shell_summary(context.root, generated_at=context.compiled_at))


__all__ = ["compile_output_phase"]
