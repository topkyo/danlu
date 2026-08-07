"""Compile output step owner."""

from __future__ import annotations

from ..app_shell.meta import write_shell_summary
from ..app_shell.summary import build_shell_summary
from ..content.output_artifacts import (
    collect_output_density_artifacts,
    collect_recent_output_artifacts,
)
from ..memory.execution_surfaces import render_concept_rewrite_proposal_page
from ..render.furnace_center import render_furnace_center
from ..render.views import render_review_queue
from .context import CompileContext


def compile_output_phase(context: CompileContext) -> None:
    # Output-pack / domain-pilot auto builders were retired (W4); only collect
    # recent outputs for furnace-center and keep live index writers below.
    context.all_outputs = collect_output_density_artifacts(context.root)
    context.recent_outputs = collect_recent_output_artifacts(context.root)

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
            knowledge_lifecycle=context.knowledge_lifecycle,
        ),
    )
    # W5 thin (A36): batch telemetry index pages retired; keep per-proposal pages when state exists.
    for proposal in context.memory["health"]["concept_rewrite"].get("all_proposals", []):
        context.write_index_artifact(
            context.root / proposal["proposal_path"],
            render_concept_rewrite_proposal_page(proposal),
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
    write_shell_summary(context.root, build_shell_summary(context.root, generated_at=context.compiled_at))


__all__ = ["compile_output_phase"]
