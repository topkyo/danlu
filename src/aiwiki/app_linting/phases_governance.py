"""Lint and nightly health helpers extracted from app_compile."""

from __future__ import annotations

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
from ..lifecycle.paths import (
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
)
from ..memory.state import load_machine_memory
from ..protocol.runtime_config import (
    CONCEPT_HARDNESS_LEVELS,
    DECISION_STATUSES,
    JUDGMENT_STATUSES,
)
from ..protocol.templates import CURATED_ASSET_SECTION_ORDER
from ..state.constants import (
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
)
from ..state.io import load_json_document
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
