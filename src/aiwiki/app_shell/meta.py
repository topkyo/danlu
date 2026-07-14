from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from ..app_lifecycle import (
    action_transition_profile,
    archive_transition_profile,
    collect_aging_signals,
    collect_curated_pages,
    curated_page_transition_profile,
    knowledge_lifecycle_governance_summary,
    review_queue,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    transition_profile,
    valid_curated_statuses,
)
from ..app_protocol import (
    ACTION_STATUSES,
    PROTOCOL_LIBRARY,
    REWRITE_PROPOSAL_STATUSES,
    ensure_layout,
    load_protocol_state,
)
from ..app_state import (
    DEFAULT_PROTOCOL,
    active_material_archive_entries,
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    furnace_center_html_path,
    llm_receipt_log_path,
    load_archive_candidates_state,
    load_compile_state,
    load_concept_rewrite_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_llm_receipt_history,
    load_machine_memory,
    load_manifest,
    load_material_archive_state,
    load_planner_state,
    load_query_route_telemetry,
    load_runtime_history,
    machine_memory_graph_html_path,
    nightly_health_state_path,
    output_packs_index_path,
    product_shell_html_path,
    review_center_html_path,
    run_log_path,
    shell_summary_path,
)
from ..app_types import ProtocolState, ShellSummary
from ..app_utils import (
    parse_frontmatter,
    relative_path,
    runtime_write_operation,
    strip_frontmatter,
    tokenize,
    utc_now,
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..config import LLMConfig
from ..content.io import (
    collect_recent_output_artifacts,
    summarize_runtime_event_for_shell,
)
from ..content.memory import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
    load_execution_receipt_history,
)
from ..execution.l3_proposals import list_l3_proposals
from ..llm import classify_backend_error
from ..render.paths import (
    execution_bundle_path,
    execution_proposal_path,
)
from ..render.views import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
)
from .surfaces import shell_search_results

build_shell_summary: Any = None
render_product_shell_html: Any = None

def shell_links(root: Path) -> dict[str, str]:
    return {
        "summary_path": relative_path(root, shell_summary_path(root)),
        "product_shell_html": relative_path(root, product_shell_html_path(root)),
        "furnace_center_markdown": "wiki/indexes/furnace-center.md",
        "review_center_markdown": "wiki/indexes/review-center.md",
        "judgment_assets_markdown": "wiki/indexes/judgment-assets.md",
        "cognitive_history_markdown": "wiki/indexes/cognitive-history.md",
        "execution_center_markdown": "wiki/indexes/execution-center.md",
        "execution_audit_markdown": "wiki/indexes/execution-audit.md",
        "graph_view_markdown": "wiki/indexes/graph-view.md",
        "protocols_markdown": "wiki/indexes/protocols.md",
        "domain_pilots_markdown": "wiki/indexes/domain-pilots.md",
        "output_packs_markdown": "wiki/indexes/output-packs.md",
        "agent_workbench_markdown": "wiki/indexes/agent-workbench.md",
        "furnace_center_html": relative_path(root, furnace_center_html_path(root)),
        "review_center_html": relative_path(root, review_center_html_path(root)),
        "execution_center_html": relative_path(root, execution_center_html_path(root)),
        "execution_audit_html": relative_path(root, execution_audit_html_path(root)),
        "graph_html": relative_path(root, machine_memory_graph_html_path(root)),
        "product_shell_design": "docs/Furnace Product Shell Plugin.md",
        "product_shell_runtime_plan": "docs/Furnace Product Shell Runtime Plan.md",
    }

def shell_curated_page_roots(root: Path) -> dict[str, str]:
    """Return repo-relative prefixes for curated-page categories.

    Exposed in ShellSummary as the single source of truth for which path
    prefixes count as "curated pages" (decisions / judgments). The plugin
    reads this instead of hardcoding `wiki/decisions/` / `wiki/judgments/`
    so that CLI remains authoritative and the plugin stays a thin client.

    Values are repo-relative directory prefixes ending in "/". They are
    NOT vault-absolute paths: the plugin resolves the active file's
    repo-relative path and checks `startswith(prefix)`.
    """
    _ = root  # kept in signature for symmetry with other shell_* helpers
    return {
        "decisions": "wiki/decisions/",
        "judgments": "wiki/judgments/",
    }

def shell_capabilities(root: Path) -> dict[str, Any]:
    return {
        "launcher_mode": "repo-local",
        "supports_hidden_state_read": False,
        "commands": {
            "p0": [
                "shell-status",
                "dashboard",
                "search",
                "compile",
                "ask",
                "run-ask",
                "nightly",
                "protocol-status",
                "protocol-set",
                "llm-check",
            ],
            "p1": [
                "run-compile",
                "run-nightly",
                "file-back",
                "review-page",
                "review-rewrite",
                "apply-rewrite",
                "verify-rewrite",
                "revert-rewrite",
                "retire-concept",
                "reactivate-concept",
                "apply-archive",
                "revert-archive",
            ],
            "p2": ["review-action", "apply-action", "revert-action", "watch", "auto-once"],
        },
        "views": {
            "furnace_center_markdown": (root / "wiki" / "indexes" / "furnace-center.md").exists(),
            "review_center_markdown": (root / "wiki" / "indexes" / "review-center.md").exists(),
            "execution_center_markdown": execution_center_path(root).exists(),
            "execution_audit_markdown": execution_audit_path(root).exists(),
            "domain_pilots_markdown": domain_pilots_path(root).exists(),
            "output_packs_markdown": output_packs_index_path(root).exists(),
            "agent_workbench_markdown": agent_workbench_path(root).exists(),
            "furnace_center_html": furnace_center_html_path(root).exists(),
            "review_center_html": review_center_html_path(root).exists(),
            "execution_center_html": execution_center_html_path(root).exists(),
            "execution_audit_html": execution_audit_html_path(root).exists(),
            "graph_html": machine_memory_graph_html_path(root).exists(),
            "product_shell_html": product_shell_html_path(root).exists(),
        },
    }

def shell_protocol_state(root: Path) -> ProtocolState:
    state = load_protocol_state(root)
    available = sorted(PROTOCOL_LIBRARY)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active not in available:
        active = DEFAULT_PROTOCOL if DEFAULT_PROTOCOL in available else (available[0] if available else DEFAULT_PROTOCOL)
    return {
        "active_protocol": active,
        "available_protocols": available,
        "protocols": list(state.get("protocols", [])) if isinstance(state.get("protocols"), list) else [],
        "state_path": str(state.get("state_path") or ""),
    }

def shell_status_dashboard(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    summary = write_shell_summary(root, build_shell_summary(root))
    return {
        "generated_at": str(summary.get("generated_at") or ""),
        "active_protocol": str(summary.get("active_protocol") or DEFAULT_PROTOCOL),
        "dashboard": dict(summary.get("dashboard", {})) if isinstance(summary.get("dashboard"), dict) else {},
        "suggested_next_actions": list(summary.get("suggested_next_actions", [])),
        "drift_warnings": list(summary.get("drift_warnings", [])),
        "links": dict(summary.get("links", {})) if isinstance(summary.get("links"), dict) else {},
    }

def shell_search(root: Path, query: str, *, limit: int = 12) -> dict[str, Any]:
    ensure_layout(root)
    summary = build_shell_summary(root)
    summary["search_results"] = shell_search_results(root, query, limit=limit)
    write_shell_summary(root, summary)
    return dict(summary["search_results"])

@runtime_write_operation
def write_shell_summary(root: Path, summary: ShellSummary | None = None) -> ShellSummary:
    summary = summary or build_shell_summary(root)
    write_json_document_if_changed_ignoring_generated_timestamps(shell_summary_path(root), summary)
    write_if_changed_ignoring_timestamps(product_shell_html_path(root), render_product_shell_html(summary))
    return summary
