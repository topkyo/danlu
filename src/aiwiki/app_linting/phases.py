"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from ..content.concepts import (
    normalize_concept_hardness,
)
from ..content.io import (
    curated_asset_section_snapshot,
    preserved_section,
)
from ..content.memory import (
    concept_summary_is_placeholder,
)
from ..content.page_sections import CONFLICT_SIGNALS, EVIDENCE_GAPS, page_has_section
from ..execution.paths import (
    execution_policy_log_path,
)
from ..execution.policy import (
    load_execution_receipt_history_strict,
)
from ..execution.repair_plan import (
    rewrite_proposal_is_apply_ready,
)
from ..lifecycle.paths import (
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
)
from ..lifecycle.status import (
    collect_curated_pages,
)
from ..memory.execution_surfaces import (
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
from ..protocol.runtime_config import (
    CONCEPT_HARDNESS_LEVELS,
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
)
from ..protocol.runtime_schema import protocol_runtime_schema_path
from ..protocol.state import load_protocol_state
from ..protocol.templates import CURATED_ASSET_SECTION_ORDER
from ..render.paths import (
    execution_bundle_path,
    execution_proposal_path,
    machine_memory_graph_path,
    product_shell_html_path,
    shell_summary_path,
)
from ..state.constants import (
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
)
from ..state.io import CorruptStateError, load_json_document, load_json_document_strict
from ..state.paths import (
    machine_memory_state_path,
)
from ..utils.markdown import (
    analyze_citation_snapshots,
    frontmatter_string_list,
    parse_frontmatter,
    strip_frontmatter,
)
from ..utils.path import relative_path

if TYPE_CHECKING:
    from .core import _LintContext

_REVIEW_LIFECYCLE_OVERRIDE_STATES = {"active", "deferred", "review"}
_PENDING_REFINEMENT_RE = re.compile(r"(?im)^\s*-\s*pending\s+refinement\.?\s*$")


def _required_judgment_sections(protocol: str) -> tuple[str, str]:
    _ = protocol
    return ("## Judgment", "## Signals")


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


def _lint_governance_phase(context: _LintContext) -> None:
    knowledge_state_path = knowledge_lifecycle_state_path(context.root)
    concept_pages = sorted((context.root / "wiki" / "concepts").glob("*.md"))
    expected_lifecycle_paths = {page["path"] for page in context.decision_pages + context.judgment_pages} | {
        relative_path(context.root, path) for path in concept_pages
    }
    if expected_lifecycle_paths and not knowledge_state_path.exists():
        context.add("error", knowledge_state_path, "Missing knowledge lifecycle state file.")
    elif knowledge_state_path.exists():
        knowledge_state = load_json_document(knowledge_state_path)
        lifecycle_entries = knowledge_state.get("entries") if isinstance(knowledge_state, dict) else None
        if not isinstance(lifecycle_entries, list):
            context.add("error", knowledge_state_path, "Knowledge lifecycle state is not valid JSON.")
        else:
            if expected_lifecycle_paths and len(lifecycle_entries) != len(expected_lifecycle_paths):
                context.add(
                    "warn",
                    knowledge_state_path,
                    f"Knowledge lifecycle state entry count `{len(lifecycle_entries)}` does not match curated page count `{len(expected_lifecycle_paths)}`.",
                )
            for entry in lifecycle_entries:
                if not isinstance(entry, dict):
                    continue
                page_id = str(entry.get("page_id") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                source_ids = entry.get("source_ids")
                active_corpus_ids = entry.get("active_corpus_ids")
                invalidation_signals = entry.get("invalidation_signals")
                if not page_id:
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry is missing `page_id`.")
                if kind not in set(KNOWLEDGE_LIFECYCLE_KINDS):
                    context.add(
                        "error",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry has unsupported kind `{kind or 'unknown'}`.",
                    )
                if lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    context.add(
                        "error",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry has unsupported state `{lifecycle_state or 'unknown'}`.",
                    )
                if not path:
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry is missing `path`.")
                elif not (context.root / path).exists():
                    context.add(
                        "error", knowledge_state_path, f"Knowledge lifecycle entry references missing page `{path}`."
                    )
                elif expected_lifecycle_paths and path not in expected_lifecycle_paths:
                    context.add(
                        "warn",
                        knowledge_state_path,
                        f"Knowledge lifecycle entry references unmanaged page `{path}`.",
                    )
                if not isinstance(source_ids, list):
                    context.add("error", knowledge_state_path, "Knowledge lifecycle entry `source_ids` is not a list.")
                if not isinstance(active_corpus_ids, list):
                    context.add(
                        "error",
                        knowledge_state_path,
                        "Knowledge lifecycle entry `active_corpus_ids` is not a list.",
                    )
                if not isinstance(invalidation_signals, list):
                    context.add(
                        "error",
                        knowledge_state_path,
                        "Knowledge lifecycle entry `invalidation_signals` is not a list.",
                    )
                if kind in {"decision", "judgment"}:
                    judgment_lifecycle_state = str(entry.get("judgment_lifecycle_state") or "")
                    if judgment_lifecycle_state and judgment_lifecycle_state not in JUDGMENT_LIFECYCLE_STATES:
                        context.add(
                            "error",
                            knowledge_state_path,
                            f"Knowledge lifecycle entry `{page_id}` has unsupported judgment lifecycle state `{judgment_lifecycle_state}`.",
                        )
                    if not isinstance(entry.get("judgment_lifecycle_reason_codes", []), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Curated lifecycle entry `judgment_lifecycle_reason_codes` is not a list.",
                        )
                if kind == "concept":
                    if not isinstance(entry.get("issues"), list):
                        context.add("error", knowledge_state_path, "Concept lifecycle entry `issues` is not a list.")
                    if not isinstance(entry.get("review_signal_codes"), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `review_signal_codes` is not a list.",
                        )
                    if not isinstance(entry.get("source_pages"), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `source_pages` is not a list.",
                        )
                    if not str(entry.get("quality_state") or ""):
                        context.add(
                            "warn",
                            knowledge_state_path,
                            f"Concept lifecycle entry `{page_id}` is missing `quality_state`.",
                        )
                    if not isinstance(entry.get("override_reason_codes", []), list):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `override_reason_codes` is not a list.",
                        )
                    override_state = str(entry.get("override_state") or "")
                    if override_state and override_state not in KNOWLEDGE_LIFECYCLE_STATES:
                        context.add(
                            "error",
                            knowledge_state_path,
                            f"Concept lifecycle entry `{page_id}` has unsupported override state `{override_state}`.",
                        )
                    if not isinstance(entry.get("override_active"), bool):
                        context.add(
                            "error",
                            knowledge_state_path,
                            "Concept lifecycle entry `override_active` is not a bool.",
                        )

    knowledge_override_path = knowledge_lifecycle_override_state_path(context.root)
    if concept_pages and not knowledge_override_path.exists():
        context.add("error", knowledge_override_path, "Missing knowledge lifecycle override state file.")
    elif knowledge_override_path.exists():
        override_state = load_json_document(knowledge_override_path)
        override_entries = override_state.get("entries") if isinstance(override_state, dict) else None
        if not isinstance(override_entries, list):
            context.add(
                "error",
                knowledge_override_path,
                "Knowledge lifecycle override state is not valid JSON.",
            )
        else:
            active_override_paths: dict[str, int] = {}
            for entry in override_entries:
                if not isinstance(entry, dict):
                    continue
                slug = str(entry.get("slug") or "")
                path = str(entry.get("path") or "")
                kind = str(entry.get("kind") or "")
                lifecycle_state = str(entry.get("lifecycle_state") or "")
                if not slug:
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry is missing `slug`.",
                    )
                if kind and kind != "concept":
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry has unsupported kind `{kind}`.",
                    )
                if lifecycle_state and lifecycle_state not in KNOWLEDGE_LIFECYCLE_STATES:
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry has unsupported state `{lifecycle_state}`.",
                    )
                active = bool(entry.get("active"))
                if not isinstance(entry.get("active"), bool):
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry `active` is not a bool.",
                    )
                if not path:
                    context.add(
                        "error",
                        knowledge_override_path,
                        "Knowledge lifecycle override entry is missing `path`.",
                    )
                elif active and not (context.root / path).exists():
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Knowledge lifecycle override entry references missing page `{path}`.",
                    )
                if active:
                    active_override_paths[path] = active_override_paths.get(path, 0) + 1
                    operation = str(entry.get("operation") or "")
                    is_review_ack = operation == "review" and lifecycle_state in _REVIEW_LIFECYCLE_OVERRIDE_STATES
                    if lifecycle_state != "retired" and not is_review_ack:
                        context.add(
                            "warn",
                            knowledge_override_path,
                            f"Active concept lifecycle override for `{slug or path}` is `{lifecycle_state or 'unknown'}`; current workflow expects `retired`.",
                        )
            for path, count in active_override_paths.items():
                if path and count > 1:
                    context.add(
                        "error",
                        knowledge_override_path,
                        f"Multiple active knowledge lifecycle overrides reference `{path}`.",
                    )

    if context.manifest["entries"] and not concept_pages:
        context.add("warn", "wiki/concepts", "No concept pages have been compiled yet.")

    for page in concept_pages:
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "concept":
            context.add("warn", page, "Concept page kind is missing or incorrect.")
        if concept_summary_is_placeholder(content):
            context.add("warn", page, "Concept page still contains the fallback summary.")
        for section in (CONFLICT_SIGNALS, EVIDENCE_GAPS):
            if not page_has_section(content, section):
                context.add("warn", page, f"Concept page is missing section `{section}`.")
        source_pages = frontmatter.get("source_pages", [])
        if not source_pages:
            context.add("warn", page, "Concept page has no source-page references.")
        if "hardness" not in frontmatter:
            context.add("warn", page, "Concept page is missing explicit `hardness` metadata.")
        else:
            raw_hardness = str(frontmatter.get("hardness") or "").strip().lower()
            hardness = normalize_concept_hardness(frontmatter.get("hardness"), default="")
            if hardness != raw_hardness:
                context.add(
                    "warn",
                    page,
                    f"Concept page has unsupported `hardness` metadata `{frontmatter.get('hardness', '')}`; expected one of `{', '.join(CONCEPT_HARDNESS_LEVELS)}`.",
                )
            elif hardness == "soft":
                context.add(
                    "warn",
                    page,
                    "Concept page is still marked `hardness: soft`; keep it in the repair backlog until grounded across more evidence or explicitly scoped down.",
                )
            else:
                confidence = str(frontmatter.get("confidence") or "").strip().lower()
                if confidence not in {"medium", "high"}:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should keep `confidence` at least `medium`.",
                    )
                if isinstance(source_pages, list) and len(source_pages) < 3:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should be grounded by at least 3 source pages.",
                    )
                conflict_section = preserved_section(content, CONFLICT_SIGNALS, "")
                if "当前没有显式冲突信号" in conflict_section:
                    context.add(
                        "warn",
                        page,
                        "Concept page with `hardness >= medium` should record at least one explicit conflict or boundary signal.",
                    )
        for source_page in source_pages:
            candidate = context.root / source_page
            if not candidate.exists():
                context.add("error", page, f"Concept page references missing source page: `{source_page}`.")

    memory = context.pack_memory if isinstance(getattr(context, "pack_memory", None), dict) else load_machine_memory(context.root)
    health = memory.get("health") if isinstance(memory, dict) else {}
    overloaded = health.get("overloaded_concept_slugs") if isinstance(health, dict) else []
    if isinstance(overloaded, list):
        overloaded_set = {str(slug).strip() for slug in overloaded if str(slug).strip()}
        for page in concept_pages:
            slug = page.stem
            if slug in overloaded_set:
                context.add(
                    "warn",
                    page,
                    "Concept is overloaded (≥4 sources); consider splitting via repair backlog / split-overloaded-concept.",
                )


def _lint_curated_phase(context: _LintContext) -> None:
    for group, expected_kind in (
        ("wiki/derived", "derived"),
        ("wiki/decisions", "decision"),
        ("wiki/judgments", "judgment"),
    ):
        for page in sorted((context.root / group).glob("*.md")):
            content = page.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            citations = [
                str(path) for path in frontmatter.get("citations", []) if isinstance(path, str) and path.strip()
            ]
            citation_snapshot_state = analyze_citation_snapshots(context.root, citations, frontmatter)
            if frontmatter.get("kind") != expected_kind:
                context.add("warn", page, f"{expected_kind.capitalize()} page kind is missing or incorrect.")
            if "wiki/sources/" not in content and "raw/" not in content:
                context.add("warn", page, f"{expected_kind.capitalize()} page has no explicit source-page reference.")
            if expected_kind in {"derived", "decision", "judgment"} and not citations:
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page is missing structured `citations` metadata.",
                )
            if (
                expected_kind in {"derived", "decision", "judgment"}
                and citations
                and not frontmatter.get("citation_snapshots")
            ):
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page is missing `citation_snapshots` metadata.",
                )
            for citation in citations:
                candidate = context.root / citation
                if not candidate.exists():
                    context.add(
                        "error",
                        page,
                        f"{expected_kind.capitalize()} page references missing citation path: `{citation}`.",
                    )
            if expected_kind in {"decision", "judgment"} and (
                citation_snapshot_state["missing"] or citation_snapshot_state["stale"]
            ):
                context.add(
                    "warn",
                    page,
                    f"{expected_kind.capitalize()} page has citation snapshot gaps: missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                )
            if expected_kind in {"decision", "judgment"} and not frontmatter.get("protocol"):
                context.add("warn", page, f"{expected_kind.capitalize()} page is missing explicit `protocol` metadata.")
            if expected_kind in {"decision", "judgment"}:
                if not str(frontmatter.get("confidence") or "").strip():
                    context.add(
                        "warn", page, f"{expected_kind.capitalize()} page is missing explicit confidence metadata."
                    )
                structured_keys = {
                    "counter_evidence": ("structured `counter_evidence` metadata", "Counter Evidence"),
                    "invalidation_rule": ("structured `invalidation_rule` metadata", "Invalidation"),
                    "next_signals": ("structured `next_signals` metadata", "Next Signals"),
                    "revisit_after": ("`revisit_after` metadata", None),
                    "escalate_after": ("`escalate_after` metadata", None),
                    "formed_at": ("`formed_at` metadata", None),
                    "last_reviewed": ("`last_reviewed` metadata", None),
                }
                for key, (label, body_heading) in structured_keys.items():
                    if key in frontmatter:
                        continue
                    if body_heading:
                        snapshot = curated_asset_section_snapshot(
                            content,
                            body_heading,
                            revisit_after=str(frontmatter.get("revisit_after") or ""),
                            escalate_after=str(frontmatter.get("escalate_after") or ""),
                        )
                        if snapshot["meaningful"]:
                            continue
                    if key in {"formed_at", "last_reviewed", "escalate_after"}:
                        continue
                    context.add(
                        "info",
                        page,
                        f"{expected_kind.capitalize()} page is missing {label}; body-first readers may still resolve it.",
                    )
                for key in ("counter_evidence", "next_signals"):
                    if key in frontmatter and not isinstance(frontmatter.get(key), list):
                        context.add(
                            "warn", page, f"{expected_kind.capitalize()} page `{key}` metadata should be a list."
                        )
                if "counter_evidence" in frontmatter and not frontmatter_string_list(frontmatter, "counter_evidence"):
                    if not curated_asset_section_snapshot(
                        content,
                        "Counter Evidence",
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )["meaningful"]:
                        context.add(
                            "info",
                            page,
                            f"{expected_kind.capitalize()} page has empty structured `counter_evidence` metadata.",
                        )
                if "next_signals" in frontmatter and not frontmatter_string_list(frontmatter, "next_signals"):
                    if not curated_asset_section_snapshot(
                        content,
                        "Next Signals",
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )["meaningful"]:
                        context.add(
                            "info", page, f"{expected_kind.capitalize()} page has empty structured `next_signals` metadata."
                        )
                if "invalidation_rule" in frontmatter and not str(frontmatter.get("invalidation_rule") or "").strip():
                    if not curated_asset_section_snapshot(
                        content,
                        "Invalidation",
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )["meaningful"]:
                        context.add(
                            "info",
                            page,
                            f"{expected_kind.capitalize()} page has empty structured `invalidation_rule` metadata.",
                        )
                if "formed_at" in frontmatter and not str(frontmatter.get("formed_at") or "").strip():
                    pass
                if frontmatter.get("reviewed_at") and not str(frontmatter.get("last_reviewed") or "").strip():
                    pass
            if expected_kind == "decision":
                if frontmatter.get("status") not in DECISION_STATUSES:
                    context.add(
                        "warn",
                        page,
                        f"Decision page has unsupported status `{frontmatter.get('status', '')}`.",
                    )
                for section in ("## Decision", "## Evidence"):
                    if section not in content:
                        context.add("warn", page, f"Decision page is missing section `{section}`.")
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        context.add("warn", page, f"Decision page is missing section `{section}`.")
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        context.add("warn", page, f"Decision page is missing section `## {heading}`.")
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"approved", "needs-revisit", "superseded"}
                        and not snapshot["meaningful"]
                    ):
                        context.add("warn", page, f"Decision page still has placeholder `{heading}` content.")
                if frontmatter.get("status") in {"approved", "needs-revisit", "superseded"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    context.add("warn", page, "Reviewed decision page is missing `reviewed_at`.")
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    context.add(
                        "warn",
                        page,
                        f"Reviewed decision page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                    )
            if expected_kind == "judgment":
                if frontmatter.get("status") not in JUDGMENT_STATUSES:
                    context.add(
                        "warn",
                        page,
                        f"Judgment page has unsupported status `{frontmatter.get('status', '')}`.",
                    )
                for section in _required_judgment_sections(str(frontmatter.get("protocol") or "")):
                    if section not in content:
                        context.add("warn", page, f"Judgment page is missing section `{section}`.")
                for section in ("## Review Status", "## Review Notes"):
                    if section not in content:
                        context.add("warn", page, f"Judgment page is missing section `{section}`.")
                for heading in CURATED_ASSET_SECTION_ORDER:
                    snapshot = curated_asset_section_snapshot(
                        content,
                        heading,
                        revisit_after=str(frontmatter.get("revisit_after") or ""),
                        escalate_after=str(frontmatter.get("escalate_after") or ""),
                    )
                    if not snapshot["present"]:
                        context.add("warn", page, f"Judgment page is missing section `## {heading}`.")
                    elif (
                        heading != "Review History"
                        and frontmatter.get("status") in {"tracking", "confirmed", "rejected"}
                        and not snapshot["meaningful"]
                    ):
                        context.add("warn", page, f"Judgment page still has placeholder `{heading}` content.")
                if frontmatter.get("status") in {"tracking", "confirmed", "rejected"} and not frontmatter.get(
                    "reviewed_at"
                ):
                    context.add("warn", page, "Reviewed judgment page is missing `reviewed_at`.")
                if frontmatter.get("reviewed_at") and citation_snapshot_state["has_drift"]:
                    context.add(
                        "warn",
                        page,
                        f"Reviewed judgment page has citation drift: drifted `{len(citation_snapshot_state['drifted'])}` missing `{len(citation_snapshot_state['missing'])}` stale `{len(citation_snapshot_state['stale'])}`.",
                    )
    for page in sorted((context.root / "wiki" / "elixirs").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if _PENDING_REFINEMENT_RE.search(strip_frontmatter(content)):
            context.add("warn", page, "Elixir page still has placeholder `Pending refinement` content.")
