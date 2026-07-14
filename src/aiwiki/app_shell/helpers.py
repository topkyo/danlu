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
from ..input_router import is_obsidian_open_link
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

LLM_FRONTDOOR_EVENTS = {
    "run-ask-frontdoor",
    "run-ask",
    "run-compile",
    "run-compile-concept",
    "run-compile-concept-rewrite-proposal",
    "run-compile-summary",
    "run-lint",
    "run-nightly",
}
LLM_PRIMARY_HEALTH_EVENTS = ("run-ask-frontdoor", "run-ask")

def _latest_llm_receipt(root: Path, *, preferred_events: tuple[str, ...] = ()) -> dict[str, Any]:
    history = load_llm_receipt_history(root)
    if preferred_events:
        for event in reversed(history):
            if not isinstance(event, dict):
                continue
            if is_obsidian_open_link(str(event.get("question") or "")):
                continue
            if str(event.get("event") or "") in preferred_events:
                return dict(event)
    for event in reversed(history):
        if not isinstance(event, dict):
            continue
        if is_obsidian_open_link(str(event.get("question") or "")):
            continue
        if str(event.get("event") or "") in LLM_FRONTDOOR_EVENTS:
            return dict(event)
    return {}

def _first_non_empty(event: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def _build_llm_rerun_command(event: dict[str, Any]) -> str:
    event_name = str(event.get("event") or "")
    target = str(event.get("target") or "")
    prompt_profile = str(event.get("prompt_profile") or "")
    command_parts = ["./scripts/aiwiki-launcher.sh"]
    if event_name in {"run-ask", "run-ask-frontdoor"}:
        question = str(event.get("question") or "").strip()
        output_format = str(event.get("format") or "report").strip() or "report"
        protocol = str(event.get("protocol") or "").strip()
        if not question:
            return ""
        command_parts.extend(["run-ask", json.dumps(question), "--format", output_format])
        if protocol:
            command_parts.extend(["--protocol", protocol])
        if prompt_profile == "lean":
            command_parts.append("--lean")
        return " ".join(command_parts)
    if event_name == "run-compile-summary":
        limit = int(event.get("limit", 5) or 5)
        command_parts.extend(["run-compile", "--limit", str(limit)])
        return " ".join(command_parts)
    if event_name == "run-lint":
        command_parts.append("run-lint")
        return " ".join(command_parts)
    if event_name == "run-nightly":
        limit = int(event.get("compile_limit", 5) or 5)
        command_parts.extend(["run-nightly", "--compile-limit", str(limit)])
        if not bool(event.get("semantic_lint", True)):
            command_parts.append("--no-semantic-lint")
        return " ".join(command_parts)
    if target:
        return f"./scripts/aiwiki-launcher.sh {event_name}"
    return ""
