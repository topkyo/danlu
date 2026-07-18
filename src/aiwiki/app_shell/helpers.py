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
from ..app_state_paths import (
    agent_workbench_path,
    domain_pilots_path,
    execution_audit_html_path,
    execution_audit_path,
    execution_center_html_path,
    execution_center_path,
    furnace_center_html_path,
    llm_receipt_log_path,
    machine_memory_graph_html_path,
    nightly_health_state_path,
    output_packs_index_path,
    product_shell_html_path,
    review_center_html_path,
    run_log_path,
    shell_summary_path,
)
from ..app_types import ProtocolState, ShellSummary
from ..compile.state import load_compile_state
from ..config import LLMConfig
from ..content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
)
from ..content.io import (
    collect_recent_output_artifacts,
    summarize_runtime_event_for_shell,
)
from ..content.rewrite import load_concept_rewrite_state
from ..execution.history import load_llm_receipt_history, load_runtime_history
from ..execution.l3_proposals import list_l3_proposals
from ..execution.policy import load_execution_receipt_history
from ..input_router import is_obsidian_open_link
from ..lifecycle.knowledge import load_knowledge_lifecycle_state
from ..llm import classify_backend_error
from ..memory.action_core import (
    action_priority_rank,
    action_status_rank,
    action_supports_low_risk_apply,
)
from ..memory.state import load_machine_memory
from ..planner.state import load_planner_state, load_query_route_telemetry
from ..render.paths import (
    execution_bundle_path,
    execution_proposal_path,
)
from ..render.views import (
    judgment_asset_attention_sort_key,
    judgment_asset_shell_record,
    judgment_asset_summary,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document
from ..state.manifest import load_manifest
from ..utils.io import (
    write_if_changed_ignoring_timestamps,
    write_json_document_if_changed_ignoring_generated_timestamps,
)
from ..utils.markdown import parse_frontmatter, strip_frontmatter
from ..utils.path import relative_path
from ..utils.text import tokenize
from ..utils.time import utc_now

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
        command_parts.append("compile")
        return " ".join(command_parts)
    if event_name == "run-lint":
        command_parts.append("lint")
        return " ".join(command_parts)
    if event_name == "run-nightly":
        limit = int(event.get("compile_limit", 5) or 5)
        command_parts.extend(["run-nightly", "--compile-limit", str(limit)])
        return " ".join(command_parts)
    if target:
        return f"./scripts/aiwiki-launcher.sh {event_name}"
    return ""
