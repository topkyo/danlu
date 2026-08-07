"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..execution.paths import (
    execution_policy_log_path,
)
from ..execution.policy import (
    load_execution_receipt_history_strict,
)
from ..execution.repair_plan import (
    rewrite_proposal_is_apply_ready,
)
from ..lifecycle.status import (
    collect_curated_pages,
)
from ..memory.execution_audit_surfaces import (
    collect_execution_consistency_signals,
)
from ..memory.paths import (
    concept_rewrite_state_path,
    machine_memory_action_state_path,
    machine_memory_history_path,
)
from ..memory.state import load_machine_memory
from ..planner.paths import planner_state_path, query_route_telemetry_path
from ..protocol.descriptors import protocol_paths
from ..protocol.library import PROTOCOL_LIBRARY
from ..protocol.runtime_schema import protocol_runtime_schema_path
from ..protocol.state import load_protocol_state
from ..render.paths import (
    execution_bundle_path,
    execution_proposal_path,
    machine_memory_graph_path,
    product_shell_html_path,
    shell_summary_path,
)
from ..state.io import CorruptStateError, load_json_document, load_json_document_strict
from ..state.paths import (
    machine_memory_state_path,
)
from ..utils.markdown import (
    parse_frontmatter,
)
from ..utils.path import relative_path

if TYPE_CHECKING:
    from .core import _LintContext


def _lint_layout_phase(context: _LintContext) -> None:
    for entry in context.manifest["entries"]:
        page = context.root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            context.add("error", page, f"Missing source page for manifest entry `{entry['id']}`.")
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        for key in ("id", "kind", "source_files", "generated_by"):
            if key not in frontmatter or frontmatter[key] in ("", []):
                context.add("error", page, f"Frontmatter is missing required key `{key}`.")
        for source_file in frontmatter.get("source_files", []):
            candidate = context.root / source_file
            if not candidate.exists():
                context.add("error", page, f"Referenced source file does not exist: `{source_file}`.")
        if "Pending LLM summary." in content:
            context.add("warn", page, "Source page still contains the placeholder summary.")
        if not frontmatter.get("concepts"):
            context.add("warn", page, "Source page has no compiled concept links.")

    required_indexes = {
        "wiki/indexes/index.md": "Missing master wiki index page.",
        "wiki/indexes/sources.md": "Missing sources index page.",
        "wiki/indexes/concepts.md": "Missing concepts index page.",
        "wiki/indexes/decisions.md": "Missing decisions index page.",
        "wiki/indexes/judgments.md": "Missing judgments index page.",
        "wiki/indexes/judgment-assets.md": "Missing judgment asset dashboard page.",
        "wiki/indexes/protocols.md": "Missing protocol dashboard page.",
        "wiki/indexes/furnace-center.md": "Missing furnace center page.",
        "wiki/indexes/review-queue.md": "Missing review queue page.",
        "wiki/indexes/review-center.md": "Missing review center page.",
        "wiki/indexes/compile-status.md": "Missing compile status page.",
        "wiki/indexes/machine-memory.md": "Missing machine memory index page.",
        "wiki/indexes/graph-view.md": "Missing graph view page.",
    }
    for relative, message in required_indexes.items():
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, message)

    required_schema = {
        "schema/index.md": "Missing runtime schema index.",
        "schema/ingest.md": "Missing runtime ingest rules.",
        "schema/citations.md": "Missing runtime citation rules.",
        "schema/conflicts.md": "Missing runtime conflict rules.",
        "schema/review.md": "Missing runtime review rules.",
        "schema/writeback.md": "Missing runtime writeback rules.",
        "schema/protocols/index.md": "Missing protocol schema index.",
    }
    for relative, message in required_schema.items():
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, message)
    for slug in sorted(PROTOCOL_LIBRARY):
        runtime_schema = protocol_runtime_schema_path(context.root, slug)
        if not runtime_schema.exists():
            context.add("error", runtime_schema, f"Missing protocol runtime schema for `{slug}`.")
            continue
        try:
            runtime_document = json.loads(runtime_schema.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add(
                "error", runtime_schema, f"Protocol runtime schema for `{slug}` is not valid JSON-compatible YAML."
            )
            continue
        if not isinstance(runtime_document, dict):
            context.add("error", runtime_schema, f"Protocol runtime schema for `{slug}` must be a mapping object.")

    context.protocol_state = load_protocol_state(context.root)
    for relative in protocol_paths(context.root, context.protocol_state["active_protocol"]):
        page = context.root / relative
        if not page.exists():
            context.add("error", relative, f"Missing active protocol rule file: `{relative}`.")


def _lint_runtime_phase(context: _LintContext) -> None:
    context.decision_pages = collect_curated_pages(context.root, "decisions", "decision")
    context.judgment_pages = collect_curated_pages(context.root, "judgments", "judgment")
    if machine_memory_state_path(context.root).exists():
        context.pack_memory = load_machine_memory(context.root)

    memory_state = machine_memory_state_path(context.root)
    shell_summary = shell_summary_path(context.root)
    product_shell_html = product_shell_html_path(context.root)
    planner_state = planner_state_path(context.root)
    query_route_telemetry = query_route_telemetry_path(context.root)
    policy_history = execution_policy_log_path(context.root)
    if context.manifest["entries"] and not memory_state.exists():
        context.add("error", memory_state, "Missing machine memory state file.")
    if context.manifest["entries"] and not shell_summary.exists():
        context.add("error", shell_summary, "Missing shell summary JSON.")
    if context.manifest["entries"] and not product_shell_html.exists():
        context.add("error", product_shell_html, "Missing product shell HTML view.")
    if context.manifest["entries"] and not planner_state.exists():
        context.add("error", planner_state, "Missing planner state file.")
    if context.manifest["entries"] and not query_route_telemetry.exists():
        context.add("error", query_route_telemetry, "Missing query route telemetry file.")
    if memory_state.exists():
        try:
            memory = json.loads(memory_state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add("error", memory_state, "Machine memory state is not valid JSON.")
        else:
            if "source_nodes" not in memory or "concept_nodes" not in memory:
                context.add("error", memory_state, "Machine memory state is missing required indexes.")
            if "health" not in memory:
                context.add("warn", memory_state, "Machine memory state is missing graph health data.")
            if not memory.get("digest"):
                context.add("warn", memory_state, "Machine memory state is missing a stable digest.")
            repair_plan = memory.get("health", {}).get("repair_plan", {}) if isinstance(memory, dict) else {}
            execution_proposals = repair_plan.get("execution_proposals", []) if isinstance(repair_plan, dict) else []
            for proposal in execution_proposals:
                if not isinstance(proposal, dict):
                    continue
                action_id = str(proposal.get("action_id") or "")
                proposal_path = context.root / str(
                    proposal.get("proposal_path")
                    or relative_path(context.root, execution_proposal_path(context.root, action_id))
                )
                if action_id and not proposal_path.exists():
                    context.add("error", proposal_path, f"Missing execution proposal page for action `{action_id}`.")
                bundle_path = context.root / str(
                    proposal.get("bundle_path")
                    or relative_path(context.root, execution_bundle_path(context.root, action_id))
                )
                if action_id and not bundle_path.exists():
                    context.add("error", bundle_path, f"Missing execution bundle for action `{action_id}`.")
    if planner_state.exists():
        try:
            planner_document = load_json_document_strict(planner_state)
        except CorruptStateError:
            planner_document = None
        if planner_document is None or not isinstance(planner_document.get("priority_queue"), list):
            context.add("error", planner_state, "Planner state is not valid JSON.")
    if query_route_telemetry.exists():
        try:
            telemetry_document = load_json_document_strict(query_route_telemetry)
        except CorruptStateError:
            telemetry_document = None
        if telemetry_document is None or not isinstance(telemetry_document.get("entries"), list):
            context.add("error", query_route_telemetry, "Query route telemetry is not valid JSON.")
    if shell_summary.exists():
        try:
            load_json_document_strict(shell_summary)
        except CorruptStateError:
            context.add("error", shell_summary, "Shell summary is not valid JSON.")

    graph_export = machine_memory_graph_path(context.root)
    if context.manifest["entries"] and not graph_export.exists():
        context.add("error", graph_export, "Missing machine memory graph export.")
    elif graph_export.exists():
        try:
            graph = json.loads(graph_export.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context.add("error", graph_export, "Machine memory graph export is not valid JSON.")
        else:
            if "nodes" not in graph or "edges" not in graph:
                context.add("error", graph_export, "Machine memory graph export is missing nodes or edges.")

    history_path = machine_memory_history_path(context.root)
    if context.manifest["entries"] and not history_path.exists():
        context.add("warn", history_path, "Machine memory history file has not been initialized.")

    action_state_path = machine_memory_action_state_path(context.root)
    if context.manifest["entries"] and not action_state_path.exists():
        context.add("warn", action_state_path, "Machine memory action state file has not been initialized.")
    elif action_state_path.exists():
        action_state = load_json_document(action_state_path)
        if not isinstance(action_state, dict) or not isinstance(action_state.get("actions"), list):
            context.add("error", action_state_path, "Machine memory action state is not valid JSON.")
        else:
            for action in action_state.get("actions", []):
                if not isinstance(action, dict):
                    continue
                receipt_path = str(action.get("last_receipt_path") or "")
                if receipt_path and not (context.root / receipt_path).exists():
                    context.add(
                        "error",
                        receipt_path,
                        f"Referenced execution receipt does not exist for action `{action.get('id', '')}`.",
                    )
            consistency_signals = collect_execution_consistency_signals(
                context.root,
                [dict(action) for action in action_state.get("actions", []) if isinstance(action, dict)],
                load_execution_receipt_history_strict(context.root),
            )
            for signal in consistency_signals:
                context.add(
                    str(signal.get("severity") or "warn"),
                    str(signal.get("path") or relative_path(context.root, action_state_path)),
                    f"Execution consistency issue for action `{signal.get('action_id', '')}`: {signal.get('message', '')}",
                )
            if action_state.get("actions") and not policy_history.exists():
                context.add("warn", policy_history, "Execution policy decision log has not been initialized.")
    if policy_history.exists():
        with policy_history.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    context.add(
                        "error", policy_history, f"Execution policy log line `{line_number}` is not valid JSON."
                    )
                    break
                if not isinstance(record, dict):
                    context.add(
                        "error", policy_history, f"Execution policy log line `{line_number}` is not a JSON object."
                    )
                    break

    rewrite_state_path = concept_rewrite_state_path(context.root)
    if context.manifest["entries"] and not rewrite_state_path.exists():
        context.add("warn", rewrite_state_path, "Concept rewrite proposal state file has not been initialized.")
    elif rewrite_state_path.exists():
        rewrite_state = load_json_document(rewrite_state_path)
        proposals = rewrite_state.get("proposals") if isinstance(rewrite_state, dict) else None
        if not isinstance(proposals, list):
            context.add("error", rewrite_state_path, "Concept rewrite proposal state is not valid JSON.")
        else:
            for proposal in proposals:
                if not isinstance(proposal, dict):
                    continue
                slug = str(proposal.get("slug") or "")
                proposal_path = context.root / str(proposal.get("proposal_path") or f"wiki/rewrite-proposals/{slug}.md")
                if slug and not proposal_path.exists():
                    context.add("error", proposal_path, f"Missing rewrite proposal page for concept `{slug}`.")
                target_path = context.root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
                if slug and not target_path.exists():
                    context.add("error", target_path, f"Rewrite proposal target concept page is missing: `{slug}`.")
                if proposal.get("apply_ready") and not proposal.get("candidate_markdown"):
                    context.add(
                        "error", proposal_path, "Rewrite proposal is marked apply_ready but has no candidate markdown."
                    )
                if proposal.get("apply_ready") and not rewrite_proposal_is_apply_ready(context.root, proposal):
                    context.add(
                        "error",
                        proposal_path,
                        "Rewrite proposal is marked apply_ready but no longer matches the current concept sources.",
                    )
                proposal_status = str(proposal.get("status") or "")
                if proposal_status == "applied" and not str(proposal.get("previous_markdown") or ""):
                    context.add("error", proposal_path, "Applied rewrite proposal has no rollback snapshot.")
                verification_status = str(proposal.get("verification_status") or "")
                if proposal_status == "applied" and not verification_status:
                    context.add("warn", proposal_path, "Applied rewrite proposal has not been verified yet.")
                if proposal_status == "applied" and verification_status == "failed":
                    context.add(
                        "warn",
                        proposal_path,
                        "Applied rewrite proposal failed verification and should be reverted or regenerated.",
                    )
