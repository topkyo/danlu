"""Content/source/lifecycle logic extracted from aiwiki.app."""

from __future__ import annotations

import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .app_protocol import (
    AUTO_PROMOTION_FORMATS,
    CAUSAL_RELATION_TYPES,
    CONCEPT_HARDNESS_LEVELS,
    CONFLICT_SIGNAL_PAIRS,
    CURATED_ASSET_SECTION_ORDER,
    DECISION_QUERY_MARKERS,
    DECISION_STATUSES,
    EVIDENCE_GAP_MARKERS,
    EXECUTION_BAND_LABELS,
    JUDGMENT_QUERY_MARKERS,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PENDING_DECISION_REVIEW_STATUSES,
    PENDING_JUDGMENT_REVIEW_STATUSES,
    PENDING_REWRITE_PROPOSAL_STATUSES,
    PROTOCOL_CLASSIFICATION_MARKERS,
    PROTOCOL_LIBRARY,
    PROTOCOL_PROMOTION_PREFIXES,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    action_focus_score,
    ensure_layout,
    load_protocol_state,
    page_focus_score,
    protocol_execution_policy_rule,
    protocol_title,
    save_manifest,
    schedule_review_windows,
)
from .app_state import (
    DEFAULT_PROTOCOL,
    JUDGMENT_LIFECYCLE_STATES,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
    active_knowledge_lifecycle_overrides,
    default_compile_state,
    default_knowledge_lifecycle_state,
    default_material_routing_state,
    ensure_knowledge_lifecycle_override_state,
    execution_policy_log_path,
    execution_receipt_history_path,
    load_active_corpora_state,
    load_concept_build_state,
    load_concept_rewrite_state,
    load_domain_pilot_build_state,
    load_json_document,
    load_knowledge_lifecycle_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_manifest,
    load_manual_link_state,
    load_material_routing_state,
    load_output_pack_build_state,
    load_planner_state,
    load_runtime_history,
    manual_link_state_path,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
    planner_state_path,
    save_knowledge_lifecycle_state,
)
from .app_types import JudgmentAsset
from .app_utils import (
    STOP_WORDS,
    analyze_citation_snapshots,
    build_citation_snapshots,
    compiled_source_sha,
    detect_kind,
    extract_provenance_paths,
    first_markdown_heading,
    next_identifier,
    normalize_workspace_path,
    parse_frontmatter,
    parse_iso_datetime,
    raw_note_metadata,
    relative_path,
    render_frontmatter,
    replace_first_markdown_heading,
    runtime_write_operation,
    sha256_bytes,
    sha256_file,
    slugify,
    strip_frontmatter,
    tokenize,
    upsert_markdown_section,
    utc_now,
)
from .config import LLMConfig


def sync_manifest_with_raw(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = load_manifest(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    existing_entries = [
        entry
        for entry in entries
        if (root / str(entry.get("stored_path") or "")).is_file()
    ]
    if len(existing_entries) != len(entries):
        entries[:] = existing_entries
        changed = True
    else:
        changed = False
    entry_by_path = {entry["stored_path"]: entry for entry in entries}
    known_paths = set(entry_by_path)
    existing_ids = {entry["id"] for entry in entries}

    for path in sorted((root / "raw" / "inbox").iterdir()):
        if not path.is_file():
            continue
        stored_path = relative_path(root, path)
        metadata = raw_note_metadata(path)
        if stored_path in known_paths:
            entry = entry_by_path[stored_path]
            current_sha = sha256_file(path)
            current_kind = detect_kind(path)
            current_title = metadata.get("title") or entry["title"]
            current_source_type = metadata.get("source_type") or entry["source_type"]
            current_note_kind = metadata.get("note_kind") or str(entry.get("note_kind") or "")
            current_original_path = metadata.get("original_path") or entry["original_path"]
            if (
                entry.get("sha256") != current_sha
                or entry.get("kind") != current_kind
                or entry.get("title") != current_title
                or entry.get("source_type") != current_source_type
                or entry.get("note_kind") != current_note_kind
                or entry.get("original_path") != current_original_path
            ):
                entry["sha256"] = current_sha
                entry["kind"] = current_kind
                entry["title"] = current_title
                entry["source_type"] = current_source_type
                entry["note_kind"] = current_note_kind
                entry["original_path"] = current_original_path
                entry["updated_at"] = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat()
                changed = True
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        seed_label = metadata.get("title") or path.stem
        seed = f"discovered-{stamp}-{slugify(seed_label)}"
        entry_id = next_identifier(existing_ids, seed)
        existing_ids.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "title": metadata.get("title") or path.stem,
                "source_type": metadata.get("source_type") or "raw-drop",
                "note_kind": metadata.get("note_kind") or "",
                "original_path": metadata.get("original_path") or stored_path,
                "stored_path": stored_path,
                "kind": detect_kind(path),
                "sha256": sha256_file(path),
                "imported_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat(),
                "updated_at": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).replace(microsecond=0).isoformat(),
            }
        )
        known_paths.add(stored_path)
        changed = True

    if changed:
        save_manifest(root, manifest)
    return manifest


@runtime_write_operation
def ingest_source(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    existing_ids = {entry["id"] for entry in manifest["entries"]}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    label = title or Path(source).stem or source
    display_title = title or label
    entry_id = next_identifier(existing_ids, f"{stamp}-{slugify(label)}")

    if source.startswith("http://") or source.startswith("https://"):
        destination = root / "raw" / "inbox" / f"{entry_id}.md"
        stub_title = title or source
        stub = "\n".join(
            [
                f"# {stub_title}",
                "",
                "## 来源 URL",
                f"- {source}",
                "",
                "## 采集状态",
                "- 这个 URL 目前只是一个占位 stub。",
                "- 在把它当作事实来源前，请先用剪藏 markdown 或本地附件替换成更完整材料。",
                "",
                "## 备注",
                "- 在补充更完整材料之前，编译器会把这个文件视为占位来源。",
            ]
        )
        destination.write_text(stub + "\n", encoding="utf-8")
        original_path = source
        source_type = "url"
    else:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source not found: {source}")
        destination = root / "raw" / "inbox" / f"{entry_id}{source_path.suffix.lower()}"
        shutil.copy2(source_path, destination)
        original_path = str(source_path)
        source_type = "file"

    entry = {
        "id": entry_id,
        "title": display_title,
        "source_type": source_type,
        "original_path": original_path,
        "stored_path": relative_path(root, destination),
        "kind": detect_kind(destination),
        "sha256": sha256_file(destination),
        "imported_at": utc_now(),
    }
    manifest["entries"].append(entry)
    save_manifest(root, manifest)
    append_wiki_log(
        root,
        "ingest",
        display_title,
        [
            f"source_type: `{source_type}`",
            f"stored_path: `{entry['stored_path']}`",
            f"original_path: `{original_path}`",
        ],
    )
    return entry


def render_source_page(entry: dict[str, Any], preview: str, compiled_at: str) -> str:
    return render_source_page_with_state(entry, preview, compiled_at, concepts=[], existing_page="")


def render_source_page_with_state(
    entry: dict[str, Any],
    preview: str,
    compiled_at: str,
    *,
    concepts: list[str],
    existing_page: str,
) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = compiled_source_sha(existing_page) not in ("", entry["sha256"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "low") if not source_changed else "low"
    if not isinstance(confidence, str) or not confidence:
        confidence = "low"
    summary = (
        preserved_section(existing_page, "Summary", "- Pending LLM summary.")
        if not source_changed
        else "- Pending LLM summary."
    )
    concept_links = ["- No concept links yet."] if not concepts else [
        f"- [{concept_label_to_title(label)}](../concepts/{concept_label_to_slug(label)}.md)"
        for label in concepts
    ]
    frontmatter = render_frontmatter(
        {
            "id": entry["id"],
            "kind": "source",
            "status": "compiled",
            "title": entry["title"],
            "source_files": [entry["stored_path"]],
            "source_sha256": entry["sha256"],
            "citations": citations,
            "concepts": concepts,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
            "confidence": confidence,
        }
    )
    body = "\n".join(
        [
            frontmatter,
            "",
            f"# {entry['title']}",
            "",
            "## Source Record",
            f"- Source type: `{entry['source_type']}`",
            f"- Original path: `{entry['original_path']}`",
            f"- Stored path: `{entry['stored_path']}`",
            f"- Imported at: `{entry['imported_at']}`",
            f"- SHA256: `{entry['sha256']}`",
            "",
            "## Summary",
            summary,
            "",
            "## Concept Links",
            *concept_links,
            "",
            "## Enrichment TODO",
            "- Refresh concept links when new sources shift the synthesis.",
            "- Add backlinks from derived outputs that cite this page.",
            "- Preserve provenance when replacing placeholder text.",
            "",
            "## Preview",
            "```text",
            preview,
            "```",
            "",
            "## Citation Anchor",
            f"- Cite this page as `wiki/sources/{entry['id']}.md`.",
        ]
    )
    return body + "\n"


def concept_candidates(entries: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in entries:
        for token in re.findall(r"[a-zA-Z0-9]{4,}", entry["title"].lower()):
            if token in STOP_WORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:10]]


def preserved_section(markdown: str, heading: str, fallback: str) -> str:
    if not markdown:
        return fallback
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, markdown)
    if not match:
        return fallback
    section = match.group(1).strip()
    return section or fallback


def normalized_markdown_section_lines(markdown: str, heading: str) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return []
    return [line.strip() for line in section.splitlines() if line.strip()]


def curated_asset_placeholder_lines(
    heading: str,
    *,
    revisit_after: str = "",
    escalate_after: str = "",
) -> list[str]:
    placeholders = {
        "Counter Evidence": ["- Pending counter evidence."],
        "Invalidation": ["- Pending invalidation conditions."],
        "Next Signals": [
            "- Pending next signals.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
        ],
        "Review History": ["- No review history yet."],
    }
    return placeholders.get(heading, [])


def render_curated_asset_sections(
    *,
    revisit_after: str,
    escalate_after: str,
) -> list[str]:
    sections: list[str] = []
    for heading in CURATED_ASSET_SECTION_ORDER:
        if heading == "Review History":
            continue
        sections.extend(
            [
                "",
                f"## {heading}",
                *curated_asset_placeholder_lines(
                    heading,
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
            ]
        )
    return sections


def render_review_history_section() -> list[str]:
    return [
        "",
        "## Review History",
        *curated_asset_placeholder_lines("Review History"),
    ]


def curated_asset_section_snapshot(
    markdown: str,
    heading: str,
    *,
    revisit_after: str = "",
    escalate_after: str = "",
) -> dict[str, Any]:
    lines = normalized_markdown_section_lines(markdown, heading)
    placeholders = curated_asset_placeholder_lines(
        heading,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
    )
    meaningful_lines = [line for line in lines if line not in placeholders]
    review_history_entries = 0
    if heading == "Review History":
        review_history_entries = sum(1 for line in meaningful_lines if line.startswith("- `"))
    return {
        "present": bool(lines),
        "meaningful": bool(meaningful_lines),
        "placeholder_only": bool(lines) and not meaningful_lines,
        "review_history_entries": review_history_entries,
    }


def append_review_history_entry(
    markdown: str,
    *,
    reviewed_at: str,
    status: str,
    note: str | None = None,
    confidence: str | None = None,
) -> str:
    existing_lines = normalized_markdown_section_lines(markdown, "Review History")
    history_lines = [line for line in existing_lines if line != "- No review history yet."]
    entry_parts = [f"- `{reviewed_at}` | status `{status}`"]
    if confidence:
        entry_parts.append(f"confidence `{confidence}`")
    if note:
        entry_parts.append(f"note {note}")
    else:
        entry_parts.append("note none")
    history_lines.insert(0, " | ".join(entry_parts))
    return upsert_markdown_section(markdown, "Review History", "\n".join(history_lines))


def review_history_entries(markdown: str) -> list[str]:
    return [
        line
        for line in normalized_markdown_section_lines(markdown, "Review History")
        if line != "- No review history yet."
    ]


def concept_label_to_slug(label: str) -> str:
    return slugify(label)[:64]


def concept_label_to_title(label: str) -> str:
    words = [word for word in label.split() if word]
    if not words:
        return "Concept"
    return " ".join(word.capitalize() for word in words)


def entry_concept_terms(entry: dict[str, Any], context: str, max_terms: int = 5) -> list[str]:
    scores: dict[str, int] = {}
    title_tokens = tokenize(entry["title"])
    phrase_tokens = title_tokens[:3]
    if len(phrase_tokens) >= 2:
        phrase = " ".join(phrase_tokens)
        scores[phrase] = scores.get(phrase, 0) + 8
    for token in title_tokens[:4]:
        scores[token] = scores.get(token, 0) + 5
    for token in tokenize(context):
        scores[token] = scores.get(token, 0) + 1
    ranked = sorted(scores.items(), key=lambda item: (-item[1], len(item[0]), item[0]))
    return [label for label, _score in ranked[:max_terms]]


def source_summary_or_preview(root: Path, entry: dict[str, Any], preview: str) -> str:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if page.exists():
        content = page.read_text(encoding="utf-8", errors="replace")
        summary = preserved_section(content, "Summary", "")
        if compiled_source_sha(content) in ("", entry["sha256"]) and summary and "Pending LLM summary." not in summary:
            return summary
    return preview


def active_manual_source_concept_links(root: Path) -> dict[str, set[str]]:
    state = load_manual_link_state(root)
    mapping: dict[str, set[str]] = {}
    for item in state.get("source_to_concept", []):
        source_id = str(item.get("source_id") or "").strip()
        concept_slug = str(item.get("concept_slug") or "").strip()
        active = bool(item.get("active", True))
        if not source_id or not concept_slug or not active:
            continue
        mapping.setdefault(source_id, set()).add(concept_slug)
    return mapping


def concept_source_input_signature(entry: dict[str, Any], context: str, manual_slugs: list[str]) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_sha256": str(entry.get("sha256") or ""),
        "context": context,
        "manual_slugs": sorted(str(slug) for slug in manual_slugs if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_concept_records(
    root: Path,
    entries: list[dict[str, Any]],
    previews: dict[str, str],
    *,
    generated_at: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    concept_map: dict[str, dict[str, Any]] = {}
    entry_terms: dict[str, list[str]] = {}
    previous_state = load_concept_build_state(root)
    previous_records = previous_state.get("entry_records", {})
    if not isinstance(previous_records, dict):
        previous_records = {}
    manual_links = active_manual_source_concept_links(root)
    dirty_concept_source_ids: list[str] = []
    clean_concept_source_ids: list[str] = []
    entry_records: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry["id"])
        context = source_summary_or_preview(root, entry, previews[entry["id"]])
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = concept_source_input_signature(entry, context, manual_slugs)
        previous_record = previous_records.get(entry_id, {})
        cached_terms = previous_record.get("terms", []) if isinstance(previous_record, dict) else []
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
            and isinstance(cached_terms, list)
        ):
            terms = [str(label) for label in cached_terms if str(label)]
            clean_concept_source_ids.append(entry_id)
        else:
            terms = entry_concept_terms(entry, context)
            dirty_concept_source_ids.append(entry_id)
        for manual_slug in manual_slugs:
            manual_label = manual_slug.replace("-", " ")
            if manual_label not in terms:
                terms.append(manual_label)
        entry_terms[entry_id] = terms
        entry_records[entry_id] = {
            "input_signature": input_signature,
            "terms": list(terms),
        }
        for label in terms:
            slug = concept_label_to_slug(label)
            record = concept_map.setdefault(
                slug,
                {
                    "slug": slug,
                    "label": label,
                    "title": concept_label_to_title(label),
                    "entries": [],
                    "score": 0,
                    "manual_source_ids": set(),
                },
            )
            record["entries"].append(entry)
            record["score"] += 1
            if slug in manual_links.get(entry_id, set()):
                record["manual_source_ids"].add(entry_id)

    ranked_records = sorted(concept_map.values(), key=lambda item: (-item["score"], item["title"].lower()))[:30]
    allowed = {record["slug"] for record in ranked_records}
    filtered_entry_terms: dict[str, list[str]] = {}
    for entry_id, labels in entry_terms.items():
        filtered = [label for label in labels if concept_label_to_slug(label) in allowed]
        filtered_entry_terms[entry_id] = filtered[:5]

    by_slug = {record["slug"]: record for record in ranked_records}
    for record in ranked_records:
        record["manual_source_ids"] = sorted(record.get("manual_source_ids", set()))
        related_counts: dict[str, int] = {}
        for entry in record["entries"]:
            for label in filtered_entry_terms[entry["id"]]:
                other_slug = concept_label_to_slug(label)
                if other_slug == record["slug"] or other_slug not in by_slug:
                    continue
                related_counts[other_slug] = related_counts.get(other_slug, 0) + 1
        related = sorted(related_counts.items(), key=lambda item: (-item[1], by_slug[item[0]]["title"].lower()))
        record["related_slugs"] = [slug for slug, _count in related[:6]]
        record["entry_ids"] = [entry["id"] for entry in record["entries"]]
        record["source_signature"] = concept_source_signature(record)
    state_document = {
        "version": 2,
        "generated_at": generated_at,
        "entry_records": entry_records,
    }
    return ranked_records, filtered_entry_terms, {
        "state_document": state_document,
        "dirty_concept_source_ids": dirty_concept_source_ids,
        "clean_concept_source_ids": clean_concept_source_ids,
    }


def concept_source_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": record["slug"],
        "entry_ids": sorted(record["entry_ids"]),
        "entry_sources": sorted(f"{entry['id']}:{entry['sha256']}" for entry in record["entries"]),
        "related_slugs": sorted(record.get("related_slugs", [])),
        "manual_source_ids": sorted(record.get("manual_source_ids", [])),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def concept_source_pages(record: dict[str, Any]) -> list[str]:
    return [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]]


def machine_memory_source_input_signature(
    root: Path,
    entry: dict[str, Any],
    preview: str,
    concepts: list[str],
) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "kind": str(entry.get("kind") or ""),
        "stored_path": str(entry.get("stored_path") or ""),
        "original_path": str(entry.get("original_path") or ""),
        "sha256": str(entry.get("sha256") or ""),
        "summary": source_summary_or_preview(root, entry, preview),
        "concepts": sorted(str(label) for label in concepts if str(label)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def machine_memory_concept_input_signature(root: Path, record: dict[str, Any]) -> str:
    page = root / "wiki" / "concepts" / f"{record.get('slug', '')}.md"
    frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace")) if page.exists() else {}
    causal_links = parse_causal_links(frontmatter)
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "source_pages": concept_source_pages(record),
        "related_slugs": sorted(str(slug) for slug in record.get("related_slugs", []) if str(slug)),
        "confidence": str(frontmatter.get("confidence") or ""),
        "hardness": normalize_concept_hardness(frontmatter.get("hardness"), default="soft"),
        "causal_links": sorted(
            [{"target": link["target"], "relation": link["relation"]} for link in causal_links],
            key=lambda item: (item["target"], item["relation"]),
        ),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


CONCEPT_RENDER_SCHEMA_VERSION = 2


def concept_render_signature(root: Path, record: dict[str, Any]) -> str:
    source_contexts = [
        load_source_page_context(root, relative)
        for relative in concept_source_pages(record)
    ]
    payload = {
        "render_schema_version": CONCEPT_RENDER_SCHEMA_VERSION,
        "title": record["title"],
        "source_signature": record["source_signature"],
        "source_pages": concept_source_pages(record),
        "source_contexts": [
            {
                "path": context.get("path", ""),
                "title": context.get("title", ""),
                "status": context.get("status", ""),
                "summary": context.get("summary", ""),
            }
            for context in source_contexts
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _normalize_summary_snippet(text: Any, *, limit: int = 200) -> str:
    if not isinstance(text, str):
        return ""
    snippet = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    snippet = snippet.replace("\r", "\n")
    snippet = re.sub(r"^[#>\-\*\d\.\s]+", "", snippet, flags=re.MULTILINE)
    snippet = re.sub(r"[`*_]", "", snippet)
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1].rstrip() + "…"


def _concept_summary_matches_legacy_placeholder(summary: Any) -> bool:
    normalized = _normalize_summary_snippet(summary).lower()
    if not normalized.startswith("this concept currently appears in"):
        return False
    return (
        "use the linked source pages below to deepen or revise this synthesis" in normalized
        or "source page" in normalized
        or "wiki/sources/" in normalized
    )


def render_concept_summary_fallback(record: dict[str, Any], source_contexts: list[dict[str, str]]) -> str:
    source_links: list[str] = []
    for context in source_contexts[:4]:
        source_path = str(context.get("path") or "").strip()
        source_title = str(context.get("title") or "").strip() or Path(source_path or "source").stem
        if source_path:
            source_links.append(f"[{source_title}](../sources/{Path(source_path).name})")
        else:
            source_links.append(f"`{source_title}`")
    source_count = len(record.get("entries", []))
    summary_lines = [
        f"- 当前概念汇总了 `{source_count}` 个 source page：{', '.join(source_links) or '暂无来源链接'}。",
    ]
    first_signal = next(
        (_normalize_summary_snippet(context.get("summary", "")) for context in source_contexts if _normalize_summary_snippet(context.get("summary", ""))),
        "",
    )
    if first_signal:
        extra_sources = max(len(source_contexts) - 1, 0)
        detail_suffix = f"；另外 `{extra_sources}` 个来源补充了边界或上下文。" if extra_sources else ""
        summary_lines.append(f"- 当前最直接的线索：{first_signal}{detail_suffix}")
    elif source_contexts:
        summary_lines.append("- 当前 source page 仍以原始材料为主，建议补充更明确的摘要后再抬高 hardness。")
    else:
        summary_lines.append("- 目前还没有可引用的 source page 摘要，先补材料再进行稳定归纳。")
    if len(source_contexts) <= 1:
        summary_lines.append("- 这还是单来源概念页；继续补充证据、冲突和例外后再升级为更硬的判断。")
    else:
        summary_lines.append("- 下一步优先收敛多来源共识、冲突点与适用边界，再把稳定结论沉淀到这里。")
    return "\n".join(summary_lines)


def normalize_concept_hardness(value: Any, *, default: str = "soft") -> str:
    normalized_default = str(default).strip().lower()
    if normalized_default not in CONCEPT_HARDNESS_LEVELS:
        normalized_default = "soft"
    if not isinstance(value, str):
        return normalized_default
    normalized = value.strip().lower()
    if normalized in CONCEPT_HARDNESS_LEVELS:
        return normalized
    return normalized_default


def concept_hardness_rank(value: Any) -> int:
    return {label: index for index, label in enumerate(CONCEPT_HARDNESS_LEVELS)}.get(
        normalize_concept_hardness(value),
        0,
    )


def parse_causal_links(frontmatter: dict[str, Any]) -> list[dict[str, str]]:
    """Parse causal_links from concept frontmatter.

    Supports pipe-delimited flat format compatible with the line-based parser:
      causal_links:
        - "memory|enables|Agent relies on memory for cross-turn continuity"
    Returns validated list of {target, relation, evidence} dicts.
    """
    raw = frontmatter.get("causal_links", [])
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict):
            target = str(item.get("target") or "").strip()
            relation = str(item.get("relation") or "").strip().lower()
            evidence = str(item.get("evidence") or "").strip()
        elif isinstance(item, str) and "|" in item:
            parts = item.split("|", 2)
            target = parts[0].strip()
            relation = parts[1].strip().lower() if len(parts) > 1 else ""
            evidence = parts[2].strip() if len(parts) > 2 else ""
        else:
            continue
        if not target or relation not in CAUSAL_RELATION_TYPES:
            continue
        result.append({"target": target, "relation": relation, "evidence": evidence})
    return result


def render_concept_conflict_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    signals = detect_concept_conflict_signals(source_contexts)
    if not signals:
        return ["- 当前没有显式冲突信号。"]
    lines: list[str] = []
    for signal in signals[:6]:
        lines.append(f"- `{signal['label']}` | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`")
    return lines


def render_concept_gap_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    gaps = detect_concept_gap_signals(source_contexts)
    if not gaps:
        return ["- 当前没有显式证据缺口。"]
    lines: list[str] = []
    for gap in gaps[:6]:
        lines.append(
            f"- `{gap.get('kind', 'unknown')}` | source `{gap.get('path', 'n/a')}` | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
        )
    return lines


CAUSAL_RELATION_LABELS = {
    "causes": "→ causes",
    "enables": "→ enables",
    "constrains": "⊣ constrains",
    "conflicts_with": "⊘ conflicts with",
}


def render_concept_causal_lines(
    causal_links: list[dict[str, str]],
    record_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    if not causal_links:
        return ["- 当前没有显式因果关系。补充 `causal_links` frontmatter 可建立因果网络。"]
    lines: list[str] = []
    for link in causal_links:
        target = link["target"]
        relation = CAUSAL_RELATION_LABELS.get(link["relation"], link["relation"])
        evidence = link.get("evidence", "")
        target_record = record_lookup.get(target)
        if target_record:
            target_label = f"[{target_record['title']}](./{target}.md)"
        else:
            target_label = f"`{target}`"
        line = f"- {relation} {target_label}"
        if evidence:
            line += f" — {evidence}"
        lines.append(line)
    return lines


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
    hardness = (
        normalize_concept_hardness(existing_frontmatter.get("hardness"), default="soft")
        if not source_changed
        else "soft"
    )
    causal_links = parse_causal_links(existing_frontmatter) if not source_changed else []
    source_pages = concept_source_pages(record)
    render_signature = str(record.get("render_signature") or concept_render_signature(record["root"], record))
    source_contexts = [
        load_source_page_context(record["root"], f"wiki/sources/{entry_id}.md")
        for entry_id in record["entry_ids"]
    ]
    summary_fallback = render_concept_summary_fallback(record, source_contexts)
    existing_summary = preserved_section(existing_page, "Summary", "").strip() if not source_changed else ""
    legacy_placeholder_summary = _concept_summary_matches_legacy_placeholder(existing_summary)
    if source_changed or not existing_summary or legacy_placeholder_summary:
        summary = summary_fallback
        if legacy_placeholder_summary and not source_changed:
            hardness = "soft"
    else:
        summary = existing_summary
    related_source_lines = [
        f"- [{entry['title']}](../sources/{entry['id']}.md)"
        for entry in sorted(record["entries"], key=lambda item: item["title"].lower())
    ] or ["- No related source pages yet."]
    related_concepts = record.get("related_slugs", [])
    related_concept_lines = [
        f"- [{record_for_slug['title']}](./{record_for_slug['slug']}.md)"
        for record_for_slug in sorted(
            [record["record_lookup"][slug] for slug in related_concepts if slug in record["record_lookup"]],
            key=lambda item: item["title"].lower(),
        )
    ] or ["- No related concepts yet."]
    frontmatter_data: dict[str, Any] = {
            "id": f"concept-{record['slug']}",
            "kind": "concept",
            "status": "compiled",
            "title": record["title"],
            "source_pages": source_pages,
            "source_signature": record["source_signature"],
            "render_signature": render_signature,
            "citations": citations,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
            "confidence": confidence,
            "hardness": hardness,
    }
    if causal_links:
        frontmatter_data["causal_links"] = [
            f"{link['target']}|{link['relation']}|{link.get('evidence', '')}"
            for link in causal_links
        ]
    frontmatter = render_frontmatter(frontmatter_data)
    lines = [
        frontmatter,
        "",
        f"# {record['title']}",
        "",
        "## Summary",
        summary,
        "",
        "## Related Sources",
        *related_source_lines,
        "",
        "## Related Concepts",
        *related_concept_lines,
        "",
        "## Causal Network",
        *render_concept_causal_lines(causal_links, record.get("record_lookup", {})),
        "",
        "## Conflict Signals",
        *render_concept_conflict_lines(source_contexts),
        "",
        "## Evidence Gaps",
        *render_concept_gap_lines(source_contexts),
        "",
        "## Maintenance Notes",
        "- Promote stable findings here instead of repeating the same synthesis across source pages.",
        "- Keep contradictions and missing evidence explicit.",
    ]
    return "\n".join(lines) + "\n"


def render_sources_index(entries: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 来源索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源总数：`{len(entries)}`",
        "",
        "## 来源列表",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in entries:
            lines.append(
                f"- [{entry['title']}](../sources/{entry['id']}.md) "
                f"({entry['kind']}, {entry['source_type']})"
            )
    return "\n".join(lines) + "\n"


def render_concepts_index(concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 概念索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 概念页总数：`{len(concepts)}`",
        "",
        "## 概念列表",
    ]
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md) "
                f"({len(concept['entries'])} source(s))"
            )
    return "\n".join(lines) + "\n"


def collect_machine_memory_actions(root: Path) -> list[dict[str, Any]]:
    state = load_machine_memory_action_state(root)
    actions = [dict(action) for action in state.get("actions", []) if isinstance(action, dict)]
    now = datetime.now(timezone.utc)
    active_protocol = load_protocol_state(root)["active_protocol"]
    for action in actions:
        action.setdefault("status", "proposed")
        action.setdefault("active", True)
        action.setdefault("priority", "medium")
        action.setdefault("review_note", "")
        action.setdefault("first_seen_at", "")
        action.setdefault("last_seen_at", "")
        action.setdefault("inactive_since", "")
        action.setdefault("occurrences", 0)
        action.setdefault("pending_review", "true" if action_needs_review(str(action.get("status"))) else "false")
        action.update(evaluate_page_aging(action, now=now))
        action["focus_score"] = action_focus_score(active_protocol, action)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    status_order = {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}
    return sorted(
        actions,
        key=lambda item: (
            0 if item.get("active") else 1,
            status_order.get(str(item.get("status")), 9),
            0 if item.get("escalation_candidate") == "true" else 1,
            0 if item.get("overdue_review") == "true" else 1,
            -int(item.get("focus_score", 0)),
            priority_order.get(str(item.get("priority")), 9),
            -int(item.get("occurrences", 0)),
            str(item.get("title", "")).lower(),
        ),
    )


def collect_machine_memory_action_aging(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    active_actions = [action for action in actions if action.get("active")]
    overdue = [action for action in active_actions if action.get("overdue_review") == "true"]
    escalated = [action for action in active_actions if action.get("escalation_candidate") == "true"]
    scheduled = [action for action in active_actions if action.get("aging_state") == "scheduled"]
    inactive = [action for action in actions if not action.get("active")]
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
        "inactive": inactive,
    }


def action_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 9)


def action_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "resolved": 3, "rejected": 4}.get(status, 9)


def action_supports_low_risk_apply(action: dict[str, Any]) -> bool:
    if not bool(action.get("active", True)) or str(action.get("status") or "") != "accepted":
        return False
    decision = str(action.get("policy_decision") or "")
    if decision:
        return decision == "allow"
    kind = str(action.get("kind") or "")
    return kind in LOW_RISK_APPLYABLE_ACTION_KINDS or kind in RESOLVABLE_MONITOR_ACTION_KINDS


def execution_policy_profile(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    if not active:
        return {
            "execution_policy": "inactive-history",
            "execution_band": "history-only",
            "policy_decision": "history",
            "policy_rule_id": "inactive-history",
            "capabilities": ["history"],
            "policy_summary": "信号已消失，只保留历史与审计价值。",
        }
    if status == "proposed":
        return {
            "execution_policy": "triage",
            "execution_band": "review-first",
            "policy_decision": "review",
            "policy_rule_id": "proposed-triage",
            "capabilities": ["review"],
            "policy_summary": "先 review / triage，再决定是否进入 accepted。",
        }
    if status == "accepted":
        if root is not None:
            protocol = str(action.get("protocol") or DEFAULT_PROTOCOL)
            kind = str(action.get("kind") or "")
            rule = protocol_execution_policy_rule(root, protocol, kind)
            if rule:
                return {
                    "execution_policy": str(rule.get("execution_policy") or "manual-repair"),
                    "execution_band": str(rule.get("execution_band") or "manual-repair"),
                    "policy_decision": str(rule.get("decision") or "review"),
                    "policy_rule_id": f"{protocol}:{kind}",
                    "capabilities": [str(item) for item in rule.get("capabilities", []) if isinstance(item, str) and item],
                    "policy_summary": str(rule.get("policy_summary") or ""),
                }
        if action_supports_low_risk_apply(action):
            return {
                "execution_policy": "semi-auto-apply",
                "execution_band": "bundle-safe-apply",
                "policy_decision": "allow",
                "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
                "capabilities": ["dry-run", "bundle-apply", "revert-safe", "history"],
                "policy_summary": "支持 dry-run、bundle-driven apply 和 receipt 驱动回滚。",
            }
        return {
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "policy_decision": "review",
            "policy_rule_id": f"legacy:{str(action.get('kind') or '')}",
            "capabilities": ["manual-edit", "review"],
            "policy_summary": "只能走人工修复与 review，不开放 safe apply。",
        }
    if status == "deferred":
        return {
            "execution_policy": "parked",
            "execution_band": "deferred",
            "policy_decision": "history",
            "policy_rule_id": "deferred-parked",
            "capabilities": ["resume-review", "history"],
            "policy_summary": "动作已暂缓，保留复查与恢复入口。",
        }
    return {
        "execution_policy": "closed",
        "execution_band": "closed",
        "policy_decision": "history",
        "policy_rule_id": "closed-history",
        "capabilities": ["history"],
        "policy_summary": "动作已关闭，仅保留审计与历史记录。",
    }


def execution_band_label(band: str) -> str:
    return EXECUTION_BAND_LABELS.get(band, band or "unknown")


PATCH_ROLE_LABELS = {
    "source": "来源页",
    "concept": "概念页",
    "index": "索引页",
    "state": "状态文件",
    "output": "输出页",
    "other": "页面",
}


PATCH_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "add-source-concept-link": {
        "summary": "补 source/concept 双向链接，并把新证据吸收到概念页摘要里。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Related Concepts", "Summary", "Citations"),
                "summary": "在来源页补 concept 引用，并保留 raw/source provenance。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary", "Related Concepts"),
                "summary": "把来源页纳入概念页，并更新 grounded synthesis。",
            },
            "state": {
                "mode": "semi-auto-apply",
                "sections": ("source_to_concept",),
                "summary": "通过 manual-link state 注入低风险补链，让 compile 收敛页面链接。",
            },
        },
    },
    "connect-isolated-source": {
        "summary": "把孤立来源接回稳定概念层，并明确为什么要接入。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Summary", "Related Concepts", "Citations"),
                "summary": "从来源页抽出候选概念并补引用。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary"),
                "summary": "优先把来源接到已有稳定概念，而不是盲目新建概念。",
            },
            "index": {
                "mode": "review",
                "sections": ("Concept Coverage", "Open Questions"),
                "summary": "在索引层确认是否还缺概念覆盖或需要新概念。",
            },
        },
    },
    "expand-singleton-concept": {
        "summary": "扩展单节点概念的来源覆盖，并收紧其适用边界。",
        "roles": {
            "concept": {
                "mode": "update",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "补来源覆盖、显式有限证据，并更新相关概念边界。",
            },
            "index": {
                "mode": "review",
                "sections": ("Rewrite Priority", "Open Questions"),
                "summary": "在概念质量和索引层确认是否需要持续重写或补料。",
            },
        },
    },
    "split-overloaded-concept": {
        "summary": "把过载概念拆成更窄的主题，并把来源重新分流。",
        "roles": {
            "concept": {
                "mode": "rewrite",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "缩窄概念边界、保留拆分说明，并给出后续子概念方向。",
            },
            "index": {
                "mode": "review",
                "sections": ("Merge Candidates", "Rewrite Priority"),
                "summary": "在概念质量层复核拆分理由和后续子概念候选。",
            },
        },
    },
    "monitor-bridge-concept": {
        "summary": "确认桥接概念仍有必要，并记录跨簇连接的理由。",
        "roles": {
            "concept": {
                "mode": "review",
                "sections": ("Summary", "Related Concepts", "Related Sources"),
                "summary": "补 bridge maintenance note，明确为什么这个桥接概念还成立。",
            },
            "index": {
                "mode": "review",
                "sections": ("Bridge Concepts", "Repair Signals"),
                "summary": "在图谱健康层确认桥接信号是否稳定，避免误删关键连接。",
            },
        },
    },
    "refresh-citation-snapshots": {
        "summary": "刷新判断页的 citation snapshot metadata，不改正文结论。",
        "roles": {
            "other": {
                "mode": "semi-auto-apply",
                "sections": ("frontmatter", "Citations"),
                "summary": "重建 citation_snapshots，让 review / drift 检测重新收敛。",
            },
        },
    },
}


PATCH_PLAN_AUXILIARY_PATHS: dict[str, tuple[str, ...]] = {
    "connect-isolated-source": ("wiki/indexes/concepts.md",),
    "expand-singleton-concept": ("wiki/indexes/concept-quality.md",),
    "split-overloaded-concept": ("wiki/indexes/concept-quality.md", "wiki/indexes/rewrite-proposals.md"),
    "monitor-bridge-concept": ("wiki/indexes/graph-health.md",),
}


PROTOCOL_PATCH_HINTS: dict[str, tuple[str, ...]] = {
    "general": (),
    "investing": (
        "同步检查 thesis、risk、catalyst 和 invalidation 页面是否要一起更新。",
    ),
    "research": (
        "同步检查 benchmark、experiment、tradeoff 和 regression risk 是否要一起更新。",
    ),
    "product": (
        "同步检查 user problem、metric、launch risk 和 validation gap 是否要一起更新。",
    ),
    "ops": (
        "同步检查 incident timeline、blast radius、mitigation 和 follow-up 是否要一起更新。",
    ),
}


def patch_role_for_path(path: str) -> str:
    if path.startswith("wiki/sources/"):
        return "source"
    if path.startswith("wiki/concepts/"):
        return "concept"
    if path.startswith("wiki/indexes/"):
        return "index"
    if path.startswith(".aiwiki/state/"):
        return "state"
    if path.startswith("output/"):
        return "output"
    return "other"


def patch_sections_for_action(kind: str, role: str) -> tuple[str, ...]:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return tuple(roles[role].get("sections", ()))
    fallback = {
        "source": ("Summary", "Citations"),
        "concept": ("Summary", "Related Sources", "Related Concepts"),
        "index": ("Status", "Open Questions"),
        "state": ("state",),
        "output": ("Summary",),
        "other": ("Summary",),
    }
    return fallback.get(role, ("Summary",))


def patch_summary_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("summary") or "")
    return str(template.get("summary") or "检查相关页面并补充修复说明。")


def patch_mode_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("mode") or "update")
    return "update"


def build_page_patch_plan(root: Path, action: dict[str, Any], *, active_protocol: str = DEFAULT_PROTOCOL) -> list[dict[str, Any]]:
    kind = str(action.get("kind") or "")
    seen_paths: set[str] = set()
    ordered_paths: list[str] = []
    for raw_path in (
        str(action.get("primary_path") or ""),
        str(action.get("secondary_path") or ""),
        *PATCH_PLAN_AUXILIARY_PATHS.get(kind, ()),
    ):
        path = raw_path.strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        ordered_paths.append(path)
    if action_supports_low_risk_apply(action):
        preview = safe_apply_preview(root, action)
        state_path = str(preview.get("state_path") or "") if isinstance(preview, dict) else ""
        if state_path and state_path not in seen_paths:
            seen_paths.add(state_path)
            ordered_paths.append(state_path)

    plan: list[dict[str, Any]] = []
    for path in ordered_paths:
        role = patch_role_for_path(path)
        absolute = root / path
        title = absolute.stem
        if absolute.is_file() and role != "state":
            frontmatter = parse_frontmatter(absolute.read_text(encoding="utf-8", errors="replace"))
            title = str(frontmatter.get("title") or title)
        summary = patch_summary_for_action(kind, role)
        protocol_hints = PROTOCOL_PATCH_HINTS.get(active_protocol, ())
        if protocol_hints and role in {"source", "concept", "index"}:
            summary = f"{summary} {protocol_hints[0]}".strip()
        plan.append(
            {
                "path": path,
                "title": title,
                "role": role,
                "role_label": PATCH_ROLE_LABELS.get(role, role),
                "exists": absolute.is_file(),
                "mode": patch_mode_for_action(kind, role),
                "sections": list(patch_sections_for_action(kind, role)),
                "summary": summary,
                "command_hint": str(action.get("command_hint") or ""),
            }
        )
    return plan


def safe_apply_preview(root: Path, action: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(action.get("kind") or "")
    if kind == "refresh-citation-snapshots":
        page_path = str(action.get("primary_path") or "")
        if not page_path:
            return None
        absolute = root / page_path
        if not absolute.exists():
            return None
        content = absolute.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        if not citations:
            return None
        return {
            "apply_mode": "citation-snapshot-refresh",
            "page_path": page_path,
            "previous_citation_snapshots": list(frontmatter.get("citation_snapshots", []) or []),
            "updated_citation_snapshots": build_citation_snapshots(root, citations),
            "affected_paths": [page_path],
            "follow_up": "执行后会重跑 compile，让 judgment drift / review surface 重新收敛。",
        }
    if kind in RESOLVABLE_MONITOR_ACTION_KINDS:
        primary_path = str(action.get("primary_path") or "")
        return {
            "apply_mode": "resolve-monitor",
            "action_kind": kind,
            "action_id": str(action.get("id") or ""),
            "primary_path": primary_path,
            "affected_paths": [p for p in (primary_path,) if p],
            "follow_up": "标记为已确认并关闭；后续 compile 会刷新 repair plan。",
        }
    if kind not in LOW_RISK_APPLYABLE_ACTION_KINDS:
        return None
    try:
        source_id, concept_slug = validate_low_risk_action_targets(root, action)
    except RuntimeError:
        return None
    primary_path = str(action.get("primary_path") or "")
    secondary_path = str(action.get("secondary_path") or "")
    return {
        "apply_mode": "manual-link-state",
        "state_path": relative_path(root, manual_link_state_path(root)),
        "entry": {
            "source_id": source_id,
            "concept_slug": concept_slug,
            "origin_action_id": str(action.get("id") or ""),
            "active": True,
        },
        "affected_paths": [
            path for path in (primary_path, secondary_path, "wiki/indexes/machine-memory-repair-plan.md") if path
        ],
        "follow_up": "执行后会重跑 compile，让 source/concept/index 层按 manual link state 收敛。",
    }


def execution_policy_decision_record(
    action: dict[str, Any],
    *,
    occurred_at: str,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "execution-policy-decision",
        "occurred_at": occurred_at,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or action.get("id") or ""),
        "action_kind": str(action.get("kind") or ""),
        "status": str(action.get("status") or "proposed"),
        "protocol": str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL),
        "policy_decision": str(action.get("policy_decision") or ""),
        "policy_rule_id": str(action.get("policy_rule_id") or ""),
        "execution_policy": str(action.get("execution_policy") or ""),
        "execution_band": str(action.get("execution_band") or ""),
        "apply_ready": str(action.get("apply_ready") or "false"),
        "active": bool(action.get("active", True)),
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "component_id": str(action.get("component_id") or ""),
    }


def load_execution_policy_decision_history(root: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    path = execution_policy_log_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    records.reverse()
    if limit is None:
        return records
    return records[:limit]


@runtime_write_operation
def append_execution_policy_decisions(root: Path, decisions: list[dict[str, Any]]) -> None:
    if not decisions:
        return
    path = execution_policy_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")


def load_execution_receipt_history(root: Path) -> list[dict[str, Any]]:
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("kind") or "") == "execution-receipt":
            records.append(payload)
    return list(reversed(records))


def remove_stale_generated_execution_proposal_pages(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_proposals_dir(root)
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if str(frontmatter.get("kind") or "") != "execution-proposal":
            continue
        action_id = str(frontmatter.get("action_id") or "")
        if action_id and action_id in active_action_ids:
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_execution_bundle_files(root: Path, active_action_ids: set[str]) -> int:
    removed = 0
    directory = execution_bundles_dir(root)
    if not directory.exists():
        return 0
    active_slugs = {slugify(action_id) for action_id in active_action_ids if action_id}
    for path in sorted(directory.glob("*.json")):
        if path.stem in active_slugs or path.stem.endswith("-dry-run"):
            continue
        if (directory / f"{path.stem}-dry-run.json").exists():
            continue
        path.unlink()
        removed += 1
    return removed


def remove_stale_generated_markdown_files(directory: Path, active_stems: set[str]) -> int:
    removed = 0
    if not directory.exists():
        return 0
    for path in sorted(directory.glob("*.md")):
        if path.stem in active_stems:
            continue
        path.unlink()
        removed += 1
    return removed


def describe_machine_memory_action(action: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    action_id = str(action.get("id") or "")
    kind = str(action.get("kind") or "")
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    review_prefix = f"PYTHONPATH=src python3 -m aiwiki.cli --root . review-action {action_id}"
    kind_steps = {
        "add-source-concept-link": "检查来源页与概念页是否应补引用或反链。",
        "connect-isolated-source": "把孤立来源接入至少一个稳定概念。",
        "expand-singleton-concept": "扩展单节点概念的相关来源或相关概念。",
        "split-overloaded-concept": "把过载概念拆成更窄的概念页或子主题。",
        "monitor-bridge-concept": "确认桥接概念仍然必要，并记录观察结论。",
        "refresh-citation-snapshots": "刷新 citation snapshot metadata，让 drift / review surface 收敛。",
    }
    next_step = kind_steps.get(kind, "检查这个 machine-memory 动作对应的页面。")
    command_hint = ""
    profile = execution_policy_profile(action, root=root)
    execution_policy = str(profile.get("execution_policy") or "triage")
    execution_band = str(profile.get("execution_band") or "review-first")
    policy_decision = str(profile.get("policy_decision") or "")
    policy_rule_id = str(profile.get("policy_rule_id") or "")
    capabilities = [str(item) for item in profile.get("capabilities", []) if isinstance(item, str) and item]
    action_with_policy = {**action, **profile}
    if not active:
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = f'{review_prefix} --status resolved --note "Signal disappeared after compile."'
    elif status == "proposed":
        command_hint = f'{review_prefix} --status accepted --note "Accepted for manual repair."'
    elif status == "accepted":
        if action_supports_low_risk_apply(action_with_policy):
            next_step = "这是低风险动作；可以直接通过 safe execution layer 应用，再让 compile 收敛状态。"
            command_hint = (
                f'PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id}'
                ' --note "Applied accepted low-risk repair."'
            )
        else:
            next_step = f"{next_step} 完成后将动作标为 resolved。"
            command_hint = f'{review_prefix} --status resolved --note "Repair completed."'
    elif status == "deferred":
        next_step = "已确认但暂缓处理；准备恢复时改回 accepted。"
        command_hint = f'{review_prefix} --status accepted --note "Resume deferred repair."'
    elif status in {"resolved", "rejected"}:
        next_step = "保持关闭，除非修复策略改变。"
    return {
        "execution_policy": execution_policy,
        "execution_band": execution_band,
        "policy_decision": policy_decision,
        "policy_rule_id": policy_rule_id,
        "execution_capabilities": ", ".join(capabilities) if capabilities else "none",
        "execution_capability_list": capabilities,
        "policy_summary": str(profile.get("policy_summary") or ""),
        "next_step": next_step,
        "command_hint": command_hint,
        "apply_ready": "true" if action_supports_low_risk_apply(action_with_policy) else "false",
    }


def build_machine_memory_repair_plan(
    root: Path,
    health: dict[str, Any],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    active_actions = [dict(action) for action in health.get("actions", []) if isinstance(action, dict)]
    inactive_actions = [dict(action) for action in health.get("inactive_actions", []) if isinstance(action, dict)]
    for action in active_actions + inactive_actions:
        action["focus_score"] = action_focus_score(active_protocol, action)
        action.update(describe_machine_memory_action(action, root=root))
    ready_actions = [action for action in active_actions if action.get("status") == "accepted"]
    triage_actions = [action for action in active_actions if action.get("status") == "proposed"]
    deferred_actions = [action for action in active_actions if action.get("status") == "deferred"]
    escalated_ids = {action["id"] for action in health.get("escalated_actions", []) if action.get("id")}
    overdue_ids = {action["id"] for action in health.get("overdue_actions", []) if action.get("id")}

    batches: dict[str, dict[str, Any]] = {}
    for action in ready_actions:
        batch_key = str(action.get("component_id") or action.get("primary_path") or action.get("id"))
        label = (
            f"component `{action['component_id']}`" if action.get("component_id") else f"page `{action['primary_path']}`"
        )
        batch = batches.setdefault(
            batch_key,
            {
                "id": batch_key,
                "label": label,
                "component_id": action.get("component_id", ""),
                "primary_paths": set(),
                "secondary_paths": set(),
                "action_ids": [],
                "actions": [],
                "priority_rank": 9,
                "escalated": False,
                "overdue": False,
            },
        )
        batch["primary_paths"].add(str(action.get("primary_path") or ""))
        if action.get("secondary_path"):
            batch["secondary_paths"].add(str(action.get("secondary_path") or ""))
        batch["action_ids"].append(action["id"])
        batch["actions"].append(action)
        batch["priority_rank"] = min(batch["priority_rank"], action_priority_rank(str(action.get("priority") or "")))
        batch["escalated"] = batch["escalated"] or action["id"] in escalated_ids
        batch["overdue"] = batch["overdue"] or action["id"] in overdue_ids

    execution_batches = sorted(
        [
            {
                **batch,
                "primary_paths": sorted(path for path in batch["primary_paths"] if path),
                "secondary_paths": sorted(path for path in batch["secondary_paths"] if path),
                "actions": sorted(
                    batch["actions"],
                    key=lambda item: (
                        -int(item.get("focus_score", 0)),
                        action_priority_rank(str(item.get("priority") or "")),
                        -int(item.get("occurrences", 0)),
                        str(item.get("title", "")).lower(),
                    ),
                ),
            }
            for batch in batches.values()
        ],
        key=lambda item: (
            0 if item["escalated"] else 1,
            0 if item["overdue"] else 1,
            -max((int(action.get("focus_score", 0)) for action in item["actions"]), default=0),
            item["priority_rank"],
            item["label"],
        ),
    )
    execution_proposals = repair_execution_proposals(
        root,
        ready_actions + triage_actions + deferred_actions,
        active_protocol=active_protocol,
    )
    planner_state = build_planner_state(root, execution_proposals, active_protocol=active_protocol)

    return {
        "ready_actions": ready_actions,
        "triage_actions": triage_actions,
        "deferred_actions": deferred_actions,
        "inactive_actions": inactive_actions[:12],
        "execution_batches": execution_batches[:10],
        "execution_proposals": execution_proposals,
        "planner_state": planner_state,
        "counts": {
            "ready": len(ready_actions),
            "triage": len(triage_actions),
            "deferred": len(deferred_actions),
            "inactive": len(inactive_actions),
            "batches": len(execution_batches),
            "proposals": len(execution_proposals),
            "patch_steps": sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals),
            "blocked_proposals": int(planner_state.get("counts", {}).get("blocked", 0) or 0),
        },
    }


def normalize_query_signature(query: str) -> str:
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower())
    signature = "-".join(tokens).strip("-")
    return signature[:160] or "query"


def classify_recurring_output_kind(query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower()))
    protocol_markers = PROTOCOL_CLASSIFICATION_MARKERS.get(protocol, PROTOCOL_CLASSIFICATION_MARKERS[DEFAULT_PROTOCOL])
    decision_markers = DECISION_QUERY_MARKERS + tuple(protocol_markers.get("decision", ()))
    judgment_markers = JUDGMENT_QUERY_MARKERS + tuple(protocol_markers.get("judgment", ()))
    decision_score = sum(1 for marker in decision_markers if marker in normalized)
    judgment_score = sum(1 for marker in judgment_markers if marker in normalized)
    if decision_score <= 0 and judgment_score <= 0:
        return ""
    if decision_score >= judgment_score:
        return "decision"
    return "judgment"


def promotion_page_title(kind: str, query: str, protocol: str = DEFAULT_PROTOCOL) -> str:
    prefix = PROTOCOL_PROMOTION_PREFIXES.get(protocol, PROTOCOL_PROMOTION_PREFIXES[DEFAULT_PROTOCOL]).get(
        kind,
        "决策沉淀" if kind == "decision" else "判断沉淀",
    )
    return f"{prefix}：{query}"


def collect_output_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            query = str(frontmatter.get("query") or "").strip()
            output_format = str(frontmatter.get("format") or "").strip()
            if not query or output_format not in AUTO_PROMOTION_FORMATS:
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": query,
                    "query_signature": normalize_query_signature(query),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "format": output_format,
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["query_signature"], item["created_at"], item["path"]))


def collect_output_density_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": str(frontmatter.get("query") or "").strip(),
                    "format": str(frontmatter.get("format") or "").strip(),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]))


def collect_recent_output_artifacts(root: Path, *, limit: int = 12) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            if str(frontmatter.get("generated_by") or "") == "aiwiki-compile":
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": str(frontmatter.get("query") or "").strip(),
                    "format": str(frontmatter.get("format") or "").strip(),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]), reverse=True)[:limit]


def find_promoted_curated_page(root: Path, kind: str, query_signature: str, protocol: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != kind:
            continue
        if str(frontmatter.get("promotion_query_signature") or "") == query_signature:
            page_protocol = str(frontmatter.get("protocol") or "")
            if page_protocol == protocol or (not page_protocol and protocol == DEFAULT_PROTOCOL):
                return path
    return None


def recurring_promotion_needs_refresh(page_path: Path, artifacts: list[dict[str, str]]) -> bool:
    frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8", errors="replace"))
    current_count = str(frontmatter.get("promotion_count") or "")
    current_last_artifact = str(frontmatter.get("promotion_last_artifact") or "")
    current_sources = {
        str(path)
        for path in frontmatter.get("source_files", [])
        if isinstance(path, str) and path.strip()
    }
    desired_count = str(len(artifacts))
    desired_last_artifact = artifacts[-1]["path"]
    desired_sources = {artifact["path"] for artifact in artifacts}
    if current_count != desired_count:
        return True
    if current_last_artifact != desired_last_artifact:
        return True
    if not desired_sources.issubset(current_sources):
        return True
    return False


def annotate_recurring_promotion(
    root: Path,
    page_path: Path,
    *,
    kind: str,
    protocol: str,
    query: str,
    query_signature: str,
    artifacts: list[dict[str, str]],
    generated_at: str,
) -> None:
    content = page_path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_files = [
        str(path)
        for path in frontmatter.get("source_files", [])
        if isinstance(path, str) and path.strip()
    ]
    for artifact in artifacts:
        artifact_path = artifact["path"]
        if artifact_path not in source_files:
            source_files.append(artifact_path)
    citations = [
        str(path)
        for path in frontmatter.get("citations", [])
        if isinstance(path, str) and path.strip()
    ]
    seen_citations = {path for path in citations}
    for artifact in artifacts:
        artifact_path = root / artifact["path"]
        if not artifact_path.exists():
            continue
        for citation in extract_provenance_paths(root, artifact_path.read_text(encoding="utf-8", errors="replace")):
            if citation in seen_citations:
                continue
            seen_citations.add(citation)
            citations.append(citation)
    formats = sorted({artifact["format"] for artifact in artifacts})
    title = promotion_page_title(kind, query, protocol)
    citation_snapshots = build_citation_snapshots(root, citations)
    frontmatter["title"] = title
    frontmatter["protocol"] = protocol
    frontmatter["source_files"] = source_files
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = citation_snapshots
    frontmatter["promotion_origin"] = "nightly-recurring-output"
    frontmatter["promotion_query"] = query
    frontmatter["promotion_query_signature"] = query_signature
    frontmatter["promotion_count"] = str(len(artifacts))
    frontmatter["promotion_formats"] = formats
    frontmatter["promotion_last_artifact"] = artifacts[-1]["path"]
    frontmatter["last_compiled_at"] = generated_at
    body = replace_first_markdown_heading(strip_frontmatter(content).strip(), title).strip()
    auto_lines = [
        "- Rule: `nightly-recurring-output`",
        f"- Protocol: `{protocol}`",
        f"- Query: `{query}`",
        f"- Signature: `{query_signature}`",
        f"- Matching outputs: `{len(artifacts)}`",
        f"- Latest artifact: `{artifacts[-1]['path']}`",
        f"- Formats: `{', '.join(formats)}`",
    ]
    for artifact in artifacts[-5:]:
        auto_lines.append(f"- Supporting artifact: `{artifact['path']}`")
    updated_body = upsert_markdown_section(body, "Auto Promotion", "\n".join(auto_lines)).strip()
    page_path.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body}\n", encoding="utf-8")


def ensure_wiki_log(root: Path) -> Path:
    ensure_layout(root)
    path = root / "wiki" / "indexes" / "log.md"
    if not path.exists():
        path.write_text("# 知识库日志\n\n", encoding="utf-8")
    return path


def append_wiki_log(root: Path, category: str, title: str, details: list[str]) -> None:
    path = ensure_wiki_log(root)
    timestamp = utc_now()
    lines = [
        f"## [{timestamp}] {category} | {title}",
        "",
        *[f"- {detail}" for detail in details],
        "",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def remove_stale_generated_concept_pages(root: Path, active_slugs: set[str]) -> int:
    removed = 0
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") != "concept":
            continue
        if frontmatter.get("generated_by") != "aiwiki-compile":
            continue
        concept_id = frontmatter.get("id", "")
        if not isinstance(concept_id, str) or not concept_id.startswith("concept-"):
            continue
        slug = concept_id[len("concept-") :]
        if slug in active_slugs:
            continue
        path.unlink()
        removed += 1
    return removed


def review_packs_dir(root: Path) -> Path:
    return root / "output" / "packs" / "review"


def decision_memos_dir(root: Path) -> Path:
    return root / "output" / "packs" / "decision-memos"


def sop_drafts_dir(root: Path) -> Path:
    return root / "output" / "packs" / "sop-drafts"


def pack_stem(seed: str) -> str:
    cleaned = seed.replace("/", "-").replace("\\", "-").replace(".md", "")
    return slugify(cleaned)[:96] or "pack"


def review_pack_path(root: Path, target_path: str) -> Path:
    return review_packs_dir(root) / f"{pack_stem(target_path)}.md"


def decision_memo_path(root: Path, target_path: str) -> Path:
    return decision_memos_dir(root) / f"{pack_stem(target_path)}.md"


def sop_draft_path(root: Path, action_id: str) -> Path:
    return sop_drafts_dir(root) / f"{pack_stem(action_id)}.md"


def execution_proposals_dir(root: Path) -> Path:
    return root / "wiki" / "execution-proposals"


def execution_proposal_path(root: Path, action_id: str) -> Path:
    return execution_proposals_dir(root) / f"{slugify(action_id)}.md"


def execution_bundles_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-bundles"


def execution_bundle_path(root: Path, action_id: str) -> Path:
    return execution_bundles_dir(root) / f"{slugify(action_id)}.json"


def execution_receipts_dir(root: Path) -> Path:
    return root / "output" / "control" / "execution-receipts"


def execution_receipt_path(root: Path, action_id: str) -> Path:
    return execution_receipts_dir(root) / f"{slugify(action_id)}.json"


def manifest_change_summary(previous_entries: list[dict[str, Any]], current_entries: list[dict[str, Any]]) -> dict[str, int]:
    previous_by_path = {
        str(entry.get("stored_path") or ""): entry
        for entry in previous_entries
        if isinstance(entry, dict) and str(entry.get("stored_path") or "")
    }
    current_by_path = {
        str(entry.get("stored_path") or ""): entry
        for entry in current_entries
        if isinstance(entry, dict) and str(entry.get("stored_path") or "")
    }
    previous_paths = set(previous_by_path)
    current_paths = set(current_by_path)
    added_paths = current_paths - previous_paths
    removed_paths = previous_paths - current_paths
    updated_paths = 0
    for stored_path in current_paths & previous_paths:
        previous = previous_by_path[stored_path]
        current = current_by_path[stored_path]
        if any(
            previous.get(field) != current.get(field)
            for field in ("sha256", "title", "kind", "source_type", "note_kind", "original_path")
        ):
            updated_paths += 1
    return {
        "manifest_entries": len(current_entries),
        "added_entries": len(added_paths),
        "updated_entries": updated_paths,
        "removed_entries": len(removed_paths),
        "changed_entries": len(added_paths) + updated_paths + len(removed_paths),
    }


def summarize_runtime_event_for_shell(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    summary = {
        "event_type": event_type,
        "occurred_at": str(event.get("occurred_at") or ""),
        "protocol": str(event.get("protocol") or ""),
        "title": "",
    }
    if event_type == "query":
        summary["title"] = str(event.get("focus_ref") or "Query")
        summary["output_path"] = str(event.get("output_ref") or "")
        summary["corpus_id"] = str(event.get("corpus_id") or "")
        summary["output_format"] = str(event.get("output_format") or "")
    elif event_type == "review":
        summary["title"] = str(event.get("page_path") or "Review")
        summary["page_path"] = str(event.get("page_path") or "")
        summary["status"] = str(event.get("status") or "")
        summary["page_kind"] = str(event.get("page_kind") or "")
    elif event_type == "knowledge-lifecycle-override":
        summary["title"] = str(event.get("slug") or event.get("page_id") or "Lifecycle override")
        summary["operation"] = str(event.get("operation") or "")
        summary["path"] = str(event.get("path") or "")
        summary["lifecycle_state"] = str(event.get("lifecycle_state") or "")
    elif event_type in {"rewrite-review", "rewrite-apply", "rewrite-verify", "rewrite-revert"}:
        summary["title"] = str(event.get("slug") or event.get("target_path") or "Concept rewrite")
        summary["path"] = str(event.get("target_path") or "")
        summary["status"] = str(event.get("status") or "")
        summary["verification_status"] = str(event.get("verification_status") or "")
    elif event_type in {"archive-apply", "archive-revert"}:
        entry_id = str(event.get("source_ids", ["archive"])[0] if event.get("source_ids") else "Archive")
        summary["title"] = entry_id
        summary["entry_id"] = entry_id
        summary["receipt_path"] = str(event.get("receipt_path") or "")
        summary["source_ids"] = [str(item) for item in event.get("source_ids", []) if item]
    elif event_type == "nightly":
        summary["title"] = "Nightly health"
        summary["active_corpus_ids"] = [str(item) for item in event.get("active_corpus_ids", []) if item]
        summary["cooled_corpus_ids"] = [str(item) for item in event.get("cooled_corpus_ids", []) if item]
        summary["expired_corpus_ids"] = [str(item) for item in event.get("expired_corpus_ids", []) if item]
    else:
        summary["title"] = event_type or "runtime-event"
    return summary


def routing_snapshot_for_protocol(routing_entry: dict[str, Any], protocol: str) -> dict[str, Any]:
    if not isinstance(routing_entry, dict):
        return {}
    if str(routing_entry.get("protocol") or "") == protocol:
        return routing_entry
    for snapshot in routing_entry.get("protocol_snapshots", []):
        if isinstance(snapshot, dict) and str(snapshot.get("protocol") or "") == protocol:
            return snapshot
    return {}


def entry_lookup_maps(entries: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id: dict[str, dict[str, Any]] = {}
    path_to_entry_id: dict[str, str] = {}
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        by_id[entry_id] = entry
        stored_path = normalize_workspace_path(str(entry.get("stored_path") or ""))
        if stored_path:
            path_to_entry_id[stored_path] = entry_id
        source_path = f"wiki/sources/{entry_id}.md"
        path_to_entry_id[source_path] = entry_id
    return by_id, path_to_entry_id


def entry_ids_from_paths(path_to_entry_id: dict[str, str], paths: list[str]) -> list[str]:
    entry_ids: list[str] = []
    seen: set[str] = set()
    for candidate in paths:
        normalized = normalize_workspace_path(candidate)
        entry_id = path_to_entry_id.get(normalized, "")
        if not entry_id and normalized.startswith("wiki/sources/") and normalized.endswith(".md"):
            entry_id = Path(normalized).stem
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        entry_ids.append(entry_id)
    return entry_ids


def _validate_rewrite_candidate_markdown(
    candidate_markdown: str,
    slug: str,
    source_signature: str,
    source_pages: list[str],
) -> None:
    frontmatter = parse_frontmatter(candidate_markdown)
    if str(frontmatter.get("id") or "") != f"concept-{slug}":
        raise RuntimeError("Rewrite candidate must preserve the concept id.")
    if str(frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Rewrite candidate must preserve `kind: concept`.")
    if str(frontmatter.get("source_signature") or "") != source_signature:
        raise RuntimeError("Rewrite candidate source_signature no longer matches the target concept.")
    candidate_source_pages = frontmatter.get("source_pages", [])
    if not isinstance(candidate_source_pages, list):
        raise RuntimeError("Rewrite candidate must preserve source_pages.")
    normalized_candidate_sources = [str(item) for item in candidate_source_pages if isinstance(item, str)]
    if normalized_candidate_sources != source_pages:
        raise RuntimeError("Rewrite candidate source_pages no longer match the target concept.")


def rewrite_proposal_candidate_is_current(root: Path, proposal: dict[str, Any]) -> bool:
    slug = str(proposal.get("slug") or "")
    candidate_markdown = str(proposal.get("candidate_markdown") or "")
    if not slug or not candidate_markdown:
        return False
    concept_path = root / str(proposal.get("target_path") or f"wiki/concepts/{slug}.md")
    if not concept_path.exists():
        return False
    current_frontmatter = parse_frontmatter(concept_path.read_text(encoding="utf-8", errors="replace"))
    current_source_signature = str(current_frontmatter.get("source_signature") or "")
    expected_source_signature = str(proposal.get("source_signature") or "")
    if expected_source_signature and current_source_signature != expected_source_signature:
        return False
    current_source_pages = current_frontmatter.get("source_pages", [])
    if not isinstance(current_source_pages, list):
        return False
    normalized_source_pages = [str(item) for item in current_source_pages if isinstance(item, str)]
    try:
        _validate_rewrite_candidate_markdown(
            candidate_markdown,
            slug,
            expected_source_signature,
            normalized_source_pages,
        )
    except RuntimeError:
        return False
    return True


def rewrite_proposal_is_apply_ready(root: Path, proposal: dict[str, Any]) -> bool:
    return str(proposal.get("status") or "") == "accepted" and rewrite_proposal_candidate_is_current(root, proposal)


def validate_low_risk_action_targets(root: Path, action: dict[str, Any]) -> tuple[str, str]:
    if not bool(action.get("active", True)):
        raise RuntimeError("Machine-memory action is no longer active.")
    source_ids = [str(item) for item in action.get("source_ids", []) if isinstance(item, str)]
    concept_slugs = [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str)]
    if not source_ids or not concept_slugs:
        raise RuntimeError("Low-risk link action is missing source_ids or concept_slugs.")
    source_id = source_ids[0]
    concept_slug = concept_slugs[0]
    manifest = sync_manifest_with_raw(root)
    known_source_ids = {str(entry.get("id") or "") for entry in manifest.get("entries", []) if isinstance(entry, dict)}
    if source_id not in known_source_ids:
        raise RuntimeError("Low-risk link action references a source that is no longer in the manifest.")
    primary_path = root / str(action.get("primary_path") or "")
    secondary_path = root / str(action.get("secondary_path") or "")
    if not primary_path.is_file() or primary_path.stem != source_id:
        raise RuntimeError("Low-risk link action primary source page is missing or no longer matches the source id.")
    if not secondary_path.is_file() or secondary_path.stem != concept_slug:
        raise RuntimeError("Low-risk link action secondary concept page is missing or no longer matches the concept slug.")
    primary_frontmatter = parse_frontmatter(primary_path.read_text(encoding="utf-8", errors="replace"))
    secondary_frontmatter = parse_frontmatter(secondary_path.read_text(encoding="utf-8", errors="replace"))
    if str(primary_frontmatter.get("kind") or "") != "source":
        raise RuntimeError("Low-risk link action primary path is not a source page anymore.")
    if str(secondary_frontmatter.get("kind") or "") != "concept":
        raise RuntimeError("Low-risk link action secondary path is not a concept page anymore.")
    return source_id, concept_slug


def placeholder_concept_slugs(root: Path) -> list[str]:
    slugs: list[str] = []
    for page in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if concept_summary_is_placeholder(content):
            slugs.append(page.stem)
    return slugs


def concept_summary_is_placeholder(markdown: str) -> bool:
    summary = preserved_section(markdown, "Summary", "")
    return _concept_summary_matches_legacy_placeholder(summary)


def concept_quality_tokens(label: str) -> set[str]:
    return {token for token in tokenize(label) if token not in STOP_WORDS}


def load_source_page_context(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    if not path.exists():
        return {
            "path": relative,
            "title": relative.rsplit("/", 1)[-1],
            "summary": "",
            "status": "missing",
            "last_compiled_at": "",
        }
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    summary = preserved_section(content, "Summary", "").strip()
    status = "placeholder" if summary == "- Pending LLM summary." else "ready"
    return {
        "path": relative,
        "title": str(frontmatter.get("title") or path.stem),
        "summary": summary,
        "status": status,
        "last_compiled_at": str(frontmatter.get("last_compiled_at") or ""),
    }


def detect_concept_conflict_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_path = {
        context["path"]: str(context.get("summary") or "").lower()
        for context in source_contexts
        if context.get("status") == "ready" and context.get("summary")
    }
    signals: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for positive, negative, label in CONFLICT_SIGNAL_PAIRS:
        positive_hits = sorted(path for path, summary in by_path.items() if positive in summary)
        negative_hits = sorted(path for path, summary in by_path.items() if negative in summary)
        if not positive_hits or not negative_hits:
            continue
        touched_paths = sorted(set(positive_hits) | set(negative_hits))
        if len(touched_paths) < 2 or label in seen_labels:
            continue
        seen_labels.add(label)
        signals.append(
            {
                "label": label,
                "positive": positive,
                "negative": negative,
                "source_pages": touched_paths,
                "source_titles": [
                    next(
                        (
                            str(context.get("title") or path)
                            for context in source_contexts
                            if context.get("path") == path
                        ),
                        path,
                    )
                    for path in touched_paths
                ],
            }
        )
    return signals


def detect_concept_gap_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for context in source_contexts:
        path = str(context.get("path") or "")
        title = str(context.get("title") or path)
        status = str(context.get("status") or "")
        summary = str(context.get("summary") or "").lower()
        if status == "missing":
            gaps.append({"kind": "missing-source-page", "path": path, "title": title, "markers": ["missing-source-page"]})
            continue
        if status == "placeholder":
            gaps.append({"kind": "pending-source-summary", "path": path, "title": title, "markers": ["pending-source-summary"]})
            continue
        markers = sorted({marker for marker in EVIDENCE_GAP_MARKERS if marker in summary})
        if markers:
            gaps.append({"kind": "evidence-gap", "path": path, "title": title, "markers": markers})
    return gaps


def concept_source_freshness_score(
    source_contexts: list[dict[str, str]],
    *,
    compiled_at: str,
) -> int:
    compiled_dt = parse_iso_datetime(compiled_at)
    if compiled_dt is None:
        return 50
    source_ages: list[float] = []
    for context in source_contexts:
        parsed = parse_iso_datetime(str(context.get("last_compiled_at") or ""))
        if parsed is None:
            continue
        age_days = max(0.0, (compiled_dt - parsed).total_seconds() / 86400)
        source_ages.append(age_days)
    if not source_ages:
        return 50
    average_age = sum(source_ages) / len(source_ages)
    if average_age <= 1:
        return 100
    if average_age <= 7:
        return 85
    if average_age <= 30:
        return 70
    if average_age <= 90:
        return 55
    return 35


def concept_quality_metrics(
    source_pages: list[str],
    source_contexts: list[dict[str, str]],
    conflict_signals: list[dict[str, Any]],
    gap_signals: list[dict[str, Any]],
    *,
    compiled_at: str,
) -> dict[str, int]:
    source_count = len(source_pages)
    ready_count = sum(1 for context in source_contexts if context.get("status") == "ready")
    placeholder_count = sum(1 for context in source_contexts if context.get("status") == "placeholder")
    missing_count = sum(1 for context in source_contexts if context.get("status") == "missing")
    coverage_score = min(100, source_count * 35) if source_count else 0
    consistency_score = max(20, 100 - len(conflict_signals) * 35) if source_count else 0
    evidence_ratio = (ready_count / source_count) if source_count else 0.0
    gap_penalty = len(gap_signals) * 14 + placeholder_count * 10 + missing_count * 20
    evidence_depth_score = max(0, round(evidence_ratio * 100) - gap_penalty)
    freshness_score = concept_source_freshness_score(source_contexts, compiled_at=compiled_at)
    quality_score = round(
        coverage_score * 0.28
        + consistency_score * 0.32
        + evidence_depth_score * 0.25
        + freshness_score * 0.15
    )
    return {
        "source_coverage": coverage_score,
        "consistency": consistency_score,
        "evidence_depth": evidence_depth_score,
        "recency": freshness_score,
        "quality_score": max(0, min(100, quality_score)),
        "ready_sources": ready_count,
        "placeholder_sources": placeholder_count,
        "missing_sources": missing_count,
    }


def concept_quality_band(quality_score: int) -> str:
    if quality_score >= 85:
        return "strong"
    if quality_score >= 70:
        return "stable"
    if quality_score >= 55:
        return "watch"
    return "fragile"


def concept_rewrite_priority(
    score: int,
    issues: list[str],
    conflicts: list[dict[str, Any]],
    *,
    quality_score: int,
) -> str:
    if score >= 6 or conflicts or "placeholder-summary" in issues or quality_score < 55:
        return "high"
    if score >= 3 or quality_score < 70:
        return "medium"
    if score > 0 or quality_score < 85:
        return "low"
    return ""


def concept_rewrite_strategy(record: dict[str, Any]) -> str:
    issues = set(record.get("issues", []))
    steps: list[str] = []
    if "placeholder-summary" in issues:
        steps.append("替换占位摘要，改成 grounded synthesis。")
    if "conflicting-source-signals" in issues:
        steps.append("并列呈现冲突来源，明确分歧和适用边界。")
    if "evidence-gap" in issues:
        steps.append("保留证据缺口和不确定性，避免过强结论。")
    if "single-source" in issues:
        steps.append("保持保守措辞，并指出还缺哪些来源。")
    if "no-related-concepts" in issues:
        steps.append("补充相关概念边界和反链。")
    if "merge-boundary" in issues:
        steps.append("检查是否需要合并或拆分概念边界。")
    return " ".join(steps[:3]) or "保持当前概念总结。"


def proposal_rollback_summary(proposal: dict[str, Any]) -> str:
    preview = proposal.get("safe_apply_preview")
    if isinstance(preview, dict):
        apply_mode = str(preview.get("apply_mode") or "")
        if apply_mode == "manual-link-state":
            return "禁用对应的 manual-link state 条目并重跑 compile。"
        if apply_mode == "citation-snapshot-refresh":
            return "恢复之前的 citation_snapshots metadata 并重跑 compile。"
    return "回滚时需要人工恢复目标页，然后重跑 compile。"


def proposal_impact_score(action: dict[str, Any], proposal: dict[str, Any]) -> int:
    priority_base = {"high": 55, "medium": 35, "low": 20}.get(str(action.get("priority") or proposal.get("priority") or "medium"), 20)
    focus_bonus = min(24, int(action.get("focus_score", 0) or 0) * 3)
    occurrence_bonus = min(12, int(action.get("occurrences", 0) or 0) * 2)
    accepted_bonus = 10 if str(action.get("status") or proposal.get("status") or "") == "accepted" else 0
    escalation_bonus = 8 if str(action.get("escalation_candidate") or "") == "true" else 0
    overdue_bonus = 6 if str(action.get("overdue_review") or "") == "true" else 0
    policy_bonus = 6 if str(action.get("policy_decision") or proposal.get("policy_decision") or "") == "allow" else 0
    return min(100, priority_base + focus_bonus + occurrence_bonus + accepted_bonus + escalation_bonus + overdue_bonus + policy_bonus)


def proposal_dependency_weight(proposal: dict[str, Any]) -> tuple[int, int]:
    kind_rank = {
        "split-concept": 5,
        "expand-concept": 4,
        "connect-source": 3,
        "cross-link": 2,
        "refresh-snapshots": 1,
        "monitor-bridge": 1,
        "manual-repair": 0,
    }
    return (
        kind_rank.get(str(proposal.get("proposal_kind") or "manual-repair"), 0),
        int(proposal.get("impact_score", 0) or 0),
    )


def proposals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_targets = {str(path) for path in left.get("target_paths", []) if isinstance(path, str) and path}
    right_targets = {str(path) for path in right.get("target_paths", []) if isinstance(path, str) and path}
    if left_targets and right_targets and left_targets.intersection(right_targets):
        return True
    left_sources = {str(item) for item in left.get("source_ids", []) if isinstance(item, str) and item}
    right_sources = {str(item) for item in right.get("source_ids", []) if isinstance(item, str) and item}
    left_concepts = {str(item) for item in left.get("concept_slugs", []) if isinstance(item, str) and item}
    right_concepts = {str(item) for item in right.get("concept_slugs", []) if isinstance(item, str) and item}
    if left_sources and right_sources and left_sources.intersection(right_sources):
        return True
    if left_concepts and right_concepts and left_concepts.intersection(right_concepts):
        return True
    component_id = str(left.get("component_id") or "")
    return bool(component_id) and component_id == str(right.get("component_id") or "")


def derive_proposal_dependencies(proposals: list[dict[str, Any]]) -> None:
    for proposal in proposals:
        current_weight = proposal_dependency_weight(proposal)
        depends_on: list[str] = []
        for candidate in proposals:
            if candidate is proposal:
                continue
            candidate_action_id = str(candidate.get("action_id") or "")
            if not candidate_action_id or not proposals_overlap(proposal, candidate):
                continue
            if proposal_dependency_weight(candidate) <= current_weight:
                continue
            if candidate_action_id not in depends_on:
                depends_on.append(candidate_action_id)
        proposal["depends_on"] = depends_on


def build_planner_state(
    root: Path,
    proposals: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    previous_state = load_planner_state(root)
    executed_actions = [dict(item) for item in previous_state.get("executed_actions", []) if isinstance(item, dict)]
    proposal_records: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for proposal in proposals:
        action_id = str(proposal.get("action_id") or "")
        depends_on = [str(item) for item in proposal.get("depends_on", []) if isinstance(item, str) and item]
        blocked = bool(depends_on)
        status = str(proposal.get("status") or "proposed")
        is_low_risk = str(proposal.get("risk") or "medium") == "low"
        auto_bundle_candidate = is_low_risk and status == "accepted" and not blocked
        human_required = bool(blocked or not auto_bundle_candidate)
        proposal_record = {
            **proposal,
            "status": status,
            "blocked": blocked,
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        proposal_records.append(proposal_record)
        queue_item = {
            "item_id": f"proposal:{action_id}",
            "item_kind": "execution-proposal",
            "action_id": action_id,
            "title": str(proposal.get("title") or action_id),
            "priority": str(proposal.get("priority") or "medium"),
            "status": status,
            "protocol": str(proposal.get("protocol") or active_protocol),
            "impact_score": int(proposal.get("impact_score", 0) or 0),
            "priority_score": int(proposal.get("priority_score", 0) or 0),
            "blocked": blocked,
            "depends_on": depends_on,
            "target_paths": list(proposal.get("target_paths", []) or []),
            "command_hint": str(proposal.get("command_hint") or ""),
            "next_step": str(proposal.get("next_step") or ""),
            "auto_bundle_candidate": auto_bundle_candidate,
            "human_required": human_required,
        }
        queue.append(queue_item)
        nodes.append(
            {
                "action_id": action_id,
                "title": queue_item["title"],
                "priority_score": queue_item["priority_score"],
                "impact_score": queue_item["impact_score"],
                "blocked": blocked,
            }
        )
        edges.extend({"from": action_id, "to": dependency} for dependency in depends_on)
    queue.sort(
        key=lambda item: (
            0 if not item.get("blocked") else 1,
            -int(item.get("priority_score", 0) or 0),
            action_priority_rank(str(item.get("priority") or "medium")),
            str(item.get("title") or "").lower(),
        )
    )
    next_action = queue[0] if queue else {}
    return {
        "version": 1,
        "generated_at": utc_now(),
        "state_path": relative_path(root, planner_state_path(root)),
        "active_protocol": active_protocol,
        "pending_proposals": proposal_records,
        "priority_queue": queue[:12],
        "dependency_graph": {
            "nodes": nodes[:16],
            "edges": edges[:24],
        },
        "next_action": next_action,
        "executed_actions": executed_actions[:16],
        "counts": {
            "pending_proposals": len(proposal_records),
            "blocked": sum(1 for item in queue if item.get("blocked")),
            "unblocked": sum(1 for item in queue if not item.get("blocked")),
            "executed_actions": len(executed_actions),
        },
    }


def repair_execution_proposals(
    root: Path,
    actions: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    strategy_map = {
        "add-source-concept-link": {
            "kind": "cross-link",
            "risk": "low",
            "summary": "补 source/concept 双向链接，并检查概念摘要是否需要吸收新证据。",
            "edits": [
                "在 source page 里补 concept 引用或相关链接。",
                "在 concept page 的 Related Sources 里加入该 source page。",
                "如果来源提供新证据，重写 concept 摘要并保持 provenance。",
            ],
        },
        "connect-isolated-source": {
            "kind": "connect-source",
            "risk": "medium",
            "summary": "把孤立来源接入至少一个稳定概念，并显式记录依据。",
            "edits": [
                "先从 source page 抽出候选概念。",
                "优先补到现有稳定概念；必要时再新建概念页。",
                "保持 source page 对 raw evidence 的回指。",
            ],
        },
        "expand-singleton-concept": {
            "kind": "expand-concept",
            "risk": "medium",
            "summary": "扩展单节点概念的来源覆盖或相关概念边界。",
            "edits": [
                "补更多来源或相关概念反链。",
                "重写摘要时强调当前证据仍然有限。",
                "如果概念过窄，考虑降级为 source-specific note。",
            ],
        },
        "split-overloaded-concept": {
            "kind": "split-concept",
            "risk": "high",
            "summary": "拆分过载概念，明确子概念边界和来源分流。",
            "edits": [
                "先定义更窄的子概念名称和边界。",
                "把 source pages 重新分流到更具体的概念页。",
                "在原概念页保留拆分说明和跳转链接。",
            ],
        },
        "monitor-bridge-concept": {
            "kind": "monitor-bridge",
            "risk": "low",
            "summary": "记录桥接概念仍然必要的原因，避免误删跨簇连接。",
            "edits": [
                "在 concept page 里补一段 bridge maintenance note。",
                "确认相关概念链接仍然成立。",
                "如果桥接已经失效，再把动作转成 merge 或 split。 ",
            ],
        },
        "refresh-citation-snapshots": {
            "kind": "refresh-snapshots",
            "risk": "low",
            "summary": "刷新 judgment citation snapshot metadata，让 drift / review surface 收敛。",
            "edits": [
                "重建 citation_snapshots metadata，不改正文结论。",
                "确认 provenance 仍指向现有 citation 列表。",
                "执行后重跑 compile，验证 judgment drift 与 review window 是否收敛。",
            ],
        },
    }
    protocol_hints = {
        "general": {
            "summary_suffix": "",
            "edits": [],
        },
        "investing": {
            "summary_suffix": " 同时检查 thesis、risk、catalyst 和 invalidation 是否需要同步更新。",
            "edits": [
                "如果涉及公司/赛道概念，明确 bull / bear evidence、catalyst、risk 和 invalidation。",
                "优先保持 company / thesis / valuation / risk factor 的边界清晰。",
            ],
        },
        "research": {
            "summary_suffix": " 同时检查 benchmark、experiment、tradeoff 和 regression risk 是否需要同步更新。",
            "edits": [
                "如果涉及研发概念，明确 benchmark、experiment、architecture tradeoff 和 regression risk。",
                "优先把 next experiment 或 validation path 写清楚。",
            ],
        },
        "product": {
            "summary_suffix": " 同时检查 user problem、metric、launch readiness 和 validation gap 是否需要同步更新。",
            "edits": [
                "如果涉及产品概念，明确 user problem、bet、metric impact 和 launch risk。",
                "优先把 next validation 或 rollout checkpoint 写清楚。",
            ],
        },
        "ops": {
            "summary_suffix": " 同时检查 incident timeline、blast radius、mitigation 和 follow-up 是否需要同步更新。",
            "edits": [
                "如果涉及运维概念，明确 incident 状态、根因判断、残余风险和 follow-up。",
                "优先把 owner、rollback path 或 next review window 写清楚。",
            ],
        },
    }
    proposals: list[dict[str, Any]] = []
    for action in actions:
        template = strategy_map.get(str(action.get("kind") or ""), {})
        action_id = str(action.get("id") or "")
        proposal_protocol = str(action.get("protocol") or active_protocol or DEFAULT_PROTOCOL)
        hint = protocol_hints.get(proposal_protocol, protocol_hints[DEFAULT_PROTOCOL])
        target_paths = [
            path
            for path in (
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            )
            if path
        ]
        proposal = {
            "id": f"proposal-{action_id}",
            "action_id": action_id,
            "title": str(action.get("title") or ""),
            "priority": str(action.get("priority") or "medium"),
            "status": str(action.get("status") or "proposed"),
            "execution_policy": str(action.get("execution_policy") or "triage"),
            "execution_band": str(action.get("execution_band") or "review-first"),
            "policy_decision": str(action.get("policy_decision") or ""),
            "policy_rule_id": str(action.get("policy_rule_id") or ""),
            "proposal_kind": str(template.get("kind") or "manual-repair"),
            "risk": str(template.get("risk") or "medium"),
            "summary": (
                str(template.get("summary") or action.get("reason") or "")
                + str(hint.get("summary_suffix") or "")
            ).strip(),
            "target_paths": target_paths,
            "suggested_edits": list(template.get("edits") or [str(action.get("reason") or "检查相关页面并补修复说明。")])
            + list(hint.get("edits") or []),
            "command_hint": str(action.get("command_hint") or ""),
            "next_step": str(action.get("next_step") or ""),
            "protocol": proposal_protocol,
            "focus_score": int(action.get("focus_score", 0)),
            "component_id": str(action.get("component_id") or ""),
            "source_ids": [str(item) for item in action.get("source_ids", []) if isinstance(item, str) and item],
            "concept_slugs": [str(item) for item in action.get("concept_slugs", []) if isinstance(item, str) and item],
            "apply_ready": str(action.get("apply_ready") or "false"),
        }
        proposal["page_patch_plan"] = build_page_patch_plan(root, action, active_protocol=proposal_protocol)
        proposal["proposal_path"] = relative_path(root, execution_proposal_path(root, action_id))
        proposal["bundle_path"] = relative_path(root, execution_bundle_path(root, action_id))
        proposal["safe_apply_preview"] = safe_apply_preview(root, action)
        proposal["rollback_summary"] = proposal_rollback_summary(proposal)
        proposal["impact_score"] = proposal_impact_score(action, proposal)
        proposal["priority_score"] = min(
            120,
            int(proposal["impact_score"])
            + {"accepted": 16, "proposed": 8, "deferred": 2}.get(proposal["status"], 0)
            + {"allow": 8, "review": 0, "history": -10}.get(proposal["policy_decision"], 0)
            + {"bundle-safe-apply": 6, "review-first": 0, "manual-repair": -4, "deferred": -8}.get(
                proposal["execution_band"],
                0,
            ),
        )
        proposals.append(proposal)
    derive_proposal_dependencies(proposals)
    for proposal in proposals:
        proposal["priority_score"] = max(
            0,
            int(proposal.get("priority_score", 0) or 0) - (4 * len(proposal.get("depends_on", []))),
        )
    proposals.sort(
        key=lambda item: (
            0 if not item.get("depends_on") else 1,
            action_status_rank(item["status"]),
            -int(item.get("priority_score", 0)),
            -int(item.get("impact_score", 0)),
            action_priority_rank(item["priority"]),
            item["proposal_kind"],
            item["title"].lower(),
        )
    )
    return proposals[:16]


def build_concept_quality(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    placeholder_slugs = set(placeholder_concept_slugs(root))
    singleton_slugs = set(memory.get("health", {}).get("singleton_concept_slugs", []))
    concept_nodes = [dict(node) for node in memory.get("concept_nodes", []) if isinstance(node, dict)]
    concept_records: dict[str, dict[str, Any]] = {}
    compiled_at = str(memory.get("compiled_at") or utc_now())

    merge_candidates: list[dict[str, Any]] = []
    for index, left in enumerate(concept_nodes):
        left_tokens = concept_quality_tokens(str(left.get("title") or left.get("slug") or ""))
        left_sources = set(left.get("source_pages", []))
        if not left_tokens or not left_sources:
            continue
        for right in concept_nodes[index + 1 :]:
            right_tokens = concept_quality_tokens(str(right.get("title") or right.get("slug") or ""))
            right_sources = set(right.get("source_pages", []))
            if not right_tokens or not right_sources:
                continue
            shared_sources = sorted(left_sources & right_sources)
            if not shared_sources:
                continue
            shared_tokens = sorted(left_tokens & right_tokens)
            left_slug = str(left.get("slug") or "")
            right_slug = str(right.get("slug") or "")
            subset_match = left_tokens <= right_tokens or right_tokens <= left_tokens or left_slug in right_slug or right_slug in left_slug
            if not subset_match and len(shared_tokens) < 2:
                continue
            merge_candidates.append(
                {
                    "left_slug": left_slug,
                    "left_title": str(left.get("title") or left_slug),
                    "right_slug": right_slug,
                    "right_title": str(right.get("title") or right_slug),
                    "shared_sources": shared_sources,
                    "shared_tokens": shared_tokens,
                    "score": len(shared_sources) * 2 + len(shared_tokens),
                }
            )

    merge_candidates.sort(
        key=lambda item: (-int(item.get("score", 0)), item["left_title"].lower(), item["right_title"].lower())
    )
    merge_candidate_slugs = {
        slug
        for candidate in merge_candidates
        for slug in (candidate.get("left_slug", ""), candidate.get("right_slug", ""))
        if slug
    }

    for node in concept_nodes:
        slug = str(node.get("slug") or "")
        title = str(node.get("title") or slug)
        source_pages = list(node.get("source_pages", []))
        related_slugs = list(node.get("related_slugs", []))
        hardness = normalize_concept_hardness(node.get("hardness"), default="soft")
        confidence = str(node.get("confidence") or "")
        source_contexts = [load_source_page_context(root, relative) for relative in source_pages]
        conflict_signals = detect_concept_conflict_signals(source_contexts)
        gap_signals = detect_concept_gap_signals(source_contexts)
        issues: list[str] = []
        score = 0
        if hardness == "soft":
            issues.append("soft-hardness")
            score += 1
        if slug in placeholder_slugs:
            issues.append("placeholder-summary")
            score += 3
        if slug in singleton_slugs or len(source_pages) <= 1:
            issues.append("single-source")
            score += 2
        if not related_slugs:
            issues.append("no-related-concepts")
            score += 1
        if conflict_signals:
            issues.append("conflicting-source-signals")
            score += 3
        if gap_signals:
            issues.append("evidence-gap")
            score += 2
        if slug in merge_candidate_slugs:
            issues.append("merge-boundary")
            score += 1
        metrics = concept_quality_metrics(
            source_pages,
            source_contexts,
            conflict_signals,
            gap_signals,
            compiled_at=compiled_at,
        )
        quality_score = int(metrics.get("quality_score", 0))
        concept_records[slug] = {
            "slug": slug,
            "title": title,
            "path": f"wiki/concepts/{slug}.md",
            "source_pages": source_pages,
            "source_signature": str(node.get("source_signature") or ""),
            "source_count": len(source_pages),
            "related_count": len(related_slugs),
            "confidence": confidence,
            "hardness": hardness,
            "issues": issues,
            "score": score,
            "quality_score": quality_score,
            "quality_band": concept_quality_band(quality_score),
            "quality_metrics": {
                "source_coverage": int(metrics.get("source_coverage", 0)),
                "consistency": int(metrics.get("consistency", 0)),
                "evidence_depth": int(metrics.get("evidence_depth", 0)),
                "recency": int(metrics.get("recency", 0)),
            },
            "ready_source_count": int(metrics.get("ready_sources", 0)),
            "placeholder_source_count": int(metrics.get("placeholder_sources", 0)),
            "missing_source_count": int(metrics.get("missing_sources", 0)),
            "conflict_signals": conflict_signals[:4],
            "gap_signals": gap_signals[:4],
            "quality_state": (
                "stable"
                if score == 0 and quality_score >= 75
                else ("rewrite-now" if score >= 3 or quality_score < 55 else "watch")
            ),
        }

    weak_concepts: list[dict[str, Any]] = []
    stable_concepts: list[dict[str, Any]] = []
    rewrite_candidates: list[dict[str, Any]] = []
    all_conflict_signals: list[dict[str, Any]] = []
    all_gap_signals: list[dict[str, Any]] = []
    for record in concept_records.values():
        record["rewrite_priority"] = concept_rewrite_priority(
            int(record.get("score", 0)),
            list(record.get("issues", [])),
            list(record.get("conflict_signals", [])),
            quality_score=int(record.get("quality_score", 0)),
        )
        record["rewrite_strategy"] = concept_rewrite_strategy(record)
        if record["conflict_signals"]:
            for signal in record["conflict_signals"]:
                all_conflict_signals.append({"slug": record["slug"], "title": record["title"], **signal})
        if record["gap_signals"]:
            for gap in record["gap_signals"]:
                all_gap_signals.append({"slug": record["slug"], "title": record["title"], **gap})
        if int(record.get("score", 0)) > 0:
            weak_concepts.append(record)
            rewrite_candidates.append(
                {
                    "slug": record["slug"],
                    "title": record["title"],
                    "path": record["path"],
                    "source_signature": record.get("source_signature", ""),
                    "priority": record["rewrite_priority"],
                    "issues": list(record.get("issues", [])),
                    "score": int(record.get("score", 0)),
                    "quality_score": int(record.get("quality_score", 0)),
                    "quality_band": str(record.get("quality_band") or ""),
                    "quality_metrics": dict(record.get("quality_metrics", {})),
                    "rewrite_strategy": record["rewrite_strategy"],
                    "conflict_count": len(record.get("conflict_signals", [])),
                    "gap_count": len(record.get("gap_signals", [])),
                    "source_pages": list(record.get("source_pages", [])),
                }
            )
        else:
            stable_concepts.append(record)

    weak_concepts.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("quality_score", 0)),
            -len(item.get("conflict_signals", [])),
            int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    stable_concepts.sort(
        key=lambda item: (
            -int(item.get("quality_score", 0)),
            -int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    rewrite_candidates.sort(
        key=lambda item: (
            action_priority_rank(item.get("priority", "")),
            -int(item.get("score", 0)),
            int(item.get("quality_score", 0)),
            -int(item.get("conflict_count", 0)),
            item.get("title", "").lower(),
        )
    )
    hard_concepts = sorted(
        (
            record
            for record in concept_records.values()
            if concept_hardness_rank(record.get("hardness")) >= concept_hardness_rank("medium")
        ),
        key=lambda item: (
            -concept_hardness_rank(item.get("hardness")),
            -int(item.get("source_count", 0)),
            -int(item.get("quality_score", 0)),
            item.get("title", "").lower(),
        ),
    )
    all_conflict_signals.sort(
        key=lambda item: (
            -len(item.get("source_pages", [])),
            item.get("title", "").lower(),
            item.get("label", ""),
        )
    )
    all_gap_signals.sort(
        key=lambda item: (
            item.get("kind", ""),
            item.get("title", "").lower(),
            item.get("path", ""),
        )
    )
    all_concepts = sorted(
        concept_records.values(),
        key=lambda item: (-int(item.get("score", 0)), int(item.get("quality_score", 0)), item.get("title", "").lower()),
    )
    average_quality_score = round(
        sum(int(record.get("quality_score", 0)) for record in all_concepts) / len(all_concepts),
        1,
    ) if all_concepts else 0.0
    quality_bands = {
        band: sum(1 for record in all_concepts if str(record.get("quality_band") or "") == band)
        for band in ("strong", "stable", "watch", "fragile")
    }
    hardness_counts = {
        label: sum(1 for record in all_concepts if normalize_concept_hardness(record.get("hardness")) == label)
        for label in CONCEPT_HARDNESS_LEVELS
    }
    return {
        "all_concepts": all_concepts,
        "hard_concepts": hard_concepts[:12],
        "weak_concepts": weak_concepts[:20],
        "stable_concepts": stable_concepts[:12],
        "merge_candidates": merge_candidates[:12],
        "rewrite_candidates": rewrite_candidates[:12],
        "conflict_signals": all_conflict_signals[:12],
        "gap_signals": all_gap_signals[:12],
        "placeholder_slugs": sorted(placeholder_slugs),
        "average_quality_score": average_quality_score,
        "quality_bands": quality_bands,
        "counts": {
            "weak": len(weak_concepts),
            "stable": len(stable_concepts),
            "merge_candidates": len(merge_candidates),
            "placeholders": len(placeholder_slugs),
            "rewrite_candidates": len(rewrite_candidates),
            "conflict_signals": len(all_conflict_signals),
            "gap_signals": len(all_gap_signals),
            "strong_quality": quality_bands["strong"],
            "stable_quality": quality_bands["stable"],
            "watch_quality": quality_bands["watch"],
            "fragile_quality": quality_bands["fragile"],
            "soft_hardness": hardness_counts["soft"],
            "medium_hardness": hardness_counts["medium"],
            "hard_hardness": hardness_counts["hard"],
            "medium_or_hard": hardness_counts["medium"] + hardness_counts["hard"],
        },
    }

from .app_lifecycle import (  # noqa: E402
    action_needs_review,
    action_transition_profile,
    apply_knowledge_lifecycle_override,
    archive_transition_profile,
    build_concept_lifecycle_entry,
    build_knowledge_lifecycle_document,
    build_knowledge_lifecycle_entry,
    collect_aging_signals,
    collect_curated_pages,
    concept_lifecycle_classification,
    concept_lifecycle_invalidation_signals,
    concept_lifecycle_matches_protocol,
    concept_lifecycle_review_signals,
    concept_protocol_ambiguity_state,
    concept_protocol_relevance,
    concept_protocol_relevance_for_source,
    curated_page_template,
    curated_page_transition_profile,
    default_curated_status,
    display_action_status,
    display_curated_status,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_protocol_relevance_ambiguity,
    display_protocol_relevance_mode,
    display_rewrite_proposal_status,
    evaluate_page_aging,
    frontmatter_string_list,
    judgment_asset_frontmatter,
    judgment_lifecycle_profile,
    knowledge_lifecycle_active_corpus_ids,
    knowledge_lifecycle_classification,
    knowledge_lifecycle_counts,
    knowledge_lifecycle_governance_summary,
    knowledge_lifecycle_invalidation_signals,
    page_needs_review,
    protocol_related_concept_lifecycle_summary,
    refresh_knowledge_lifecycle_state,
    render_knowledge_lifecycle_entry_summary,
    review_queue,
    rewrite_proposal_needs_review,
    rewrite_proposal_status_rank,
    rewrite_transition_profile,
    select_knowledge_lifecycle_entries,
    sort_curated_pages,
    sort_knowledge_lifecycle_entries,
    transition_profile,
    valid_curated_statuses,
)
from .app_render import (  # noqa: E402
    append_wiki_log,
    build_domain_pilot_scorecard,
    build_domain_pilots,
    build_domain_pilots_incremental,
    build_output_pack_decision_memos,
    build_output_pack_review_packs,
    build_output_pack_sop_drafts,
    build_output_packs,
    build_output_packs_incremental,
    compact_section_lines,
    decision_memo_path,
    decision_memo_recommendation_lines,
    decision_memo_section_lines,
    decision_memos_dir,
    domain_pilot_protocol_input_signature,
    domain_pilot_protocol_inputs,
    domain_pilot_scorecard_is_reusable,
    domain_pilot_state_scorecard,
    domain_pilots_index_path,
    ensure_wiki_log,
    execution_bundle_path,
    execution_bundles_dir,
    execution_proposal_path,
    execution_proposals_dir,
    execution_receipt_path,
    execution_receipts_dir,
    extract_sop_pattern_frequencies,
    furnace_quick_commands,
    judgment_asset_attention_sort_key,
    judgment_asset_gap_codes,
    judgment_asset_shell_record,
    judgment_asset_summary,
    load_workspace_markdown,
    output_pack_decision_memo_group_input_signature,
    output_pack_group_is_reusable,
    output_pack_lifecycle_summary_input_signature,
    output_pack_repair_plan_candidates,
    output_pack_review_candidates,
    output_pack_review_group_input_signature,
    output_pack_reviewed_candidates,
    output_pack_sop_group_input_signature,
    output_pack_state_records,
    output_pack_version_history_lines,
    pack_stem,
    pack_workspace_link,
    pilot_scorecard_path,
    pilot_scorecards_dir,
    pilot_stage,
    protocol_execution_receipts,
    protocol_output_pack_rows,
    protocol_scorecard,
    remove_stale_generated_concept_pages,
    render_agent_pack,
    render_agent_workbench,
    render_aging_report,
    render_cognitive_history,
    render_compile_status,
    render_curated_index,
    render_curated_page_summary,
    render_domain_pilots_index,
    render_furnace_center,
    render_furnace_center_html,
    render_judgment_assets,
    render_master_index,
    render_output_packs_index,
    render_review_center_html,
    render_review_queue,
    review_pack_path,
    review_packs_dir,
    sop_draft_path,
    sop_drafts_dir,
    sop_pattern_key,
    workspace_file_signature,
    workspace_link,
)
