"""Content/source/lifecycle logic extracted from aiwiki.app."""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import LLMConfig

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

from .app_state import (
    DEFAULT_PROTOCOL,
    KNOWLEDGE_LIFECYCLE_KINDS,
    KNOWLEDGE_LIFECYCLE_STATES,
    active_knowledge_lifecycle_overrides,
    default_compile_state,
    default_knowledge_lifecycle_state,
    default_material_routing_state,
    ensure_knowledge_lifecycle_override_state,
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
    load_runtime_history,
    manual_link_state_path,
    material_archive_action_id,
    material_archive_state_path,
    material_state_path,
    save_knowledge_lifecycle_state,
)

from .app_protocol import (
    AUTO_PROMOTION_FORMATS,
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
    action_focus_score,
    ensure_layout,
    load_protocol_state,
    page_focus_score,
    protocol_title,
    save_manifest,
    schedule_review_windows,
)

def sync_manifest_with_raw(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = load_manifest(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    entry_by_path = {entry["stored_path"]: entry for entry in entries}
    known_paths = set(entry_by_path)
    existing_ids = {entry["id"] for entry in entries}
    changed = False

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
            current_original_path = metadata.get("original_path") or entry["original_path"]
            if (
                entry.get("sha256") != current_sha
                or entry.get("kind") != current_kind
                or entry.get("title") != current_title
                or entry.get("source_type") != current_source_type
                or entry.get("original_path") != current_original_path
            ):
                entry["sha256"] = current_sha
                entry["kind"] = current_kind
                entry["title"] = current_title
                entry["source_type"] = current_source_type
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


def machine_memory_concept_input_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": str(record.get("slug") or ""),
        "title": str(record.get("title") or ""),
        "source_signature": str(record.get("source_signature") or ""),
        "source_pages": concept_source_pages(record),
        "related_slugs": sorted(str(slug) for slug in record.get("related_slugs", []) if str(slug)),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def concept_render_signature(root: Path, record: dict[str, Any]) -> str:
    source_contexts = [
        load_source_page_context(root, relative)
        for relative in concept_source_pages(record)
    ]
    payload = {
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


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
    source_pages = concept_source_pages(record)
    render_signature = str(record.get("render_signature") or concept_render_signature(record["root"], record))
    summary_fallback = "\n".join(
        [
            f"- This concept currently appears in `{len(record['entries'])}` source page(s).",
            "- Use the linked source pages below to deepen or revise this synthesis.",
        ]
    )
    summary = preserved_section(existing_page, "Summary", summary_fallback) if not source_changed else summary_fallback
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
    source_contexts = [
        load_source_page_context(record["root"], f"wiki/sources/{entry_id}.md")
        for entry_id in record["entry_ids"]
    ]
    frontmatter = render_frontmatter(
        {
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
        }
    )
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


def default_curated_status(kind: str) -> str:
    if kind == "decision":
        return "proposed"
    if kind == "judgment":
        return "tentative"
    return "filed"


def valid_curated_statuses(kind: str) -> tuple[str, ...]:
    if kind == "decision":
        return DECISION_STATUSES
    if kind == "judgment":
        return JUDGMENT_STATUSES
    return ()


def page_needs_review(kind: str, status: str) -> bool:
    if kind == "decision":
        return status in PENDING_DECISION_REVIEW_STATUSES
    if kind == "judgment":
        return status in PENDING_JUDGMENT_REVIEW_STATUSES
    return False


def evaluate_page_aging(page: dict[str, str], now: datetime | None = None) -> dict[str, str]:
    now = now or datetime.now(timezone.utc)
    revisit_after = parse_iso_datetime(page.get("revisit_after", ""))
    escalate_after = parse_iso_datetime(page.get("escalate_after", ""))
    overdue = bool(revisit_after and revisit_after <= now)
    escalated = bool(escalate_after and escalate_after <= now)
    aging_state = ""
    if escalated:
        aging_state = "escalated"
    elif overdue:
        aging_state = "overdue"
    elif revisit_after:
        aging_state = "scheduled"
    return {
        "revisit_after": revisit_after.replace(microsecond=0).isoformat() if revisit_after else "",
        "escalate_after": escalate_after.replace(microsecond=0).isoformat() if escalate_after else "",
        "aging_state": aging_state,
        "overdue_review": "true" if overdue else "false",
        "escalation_candidate": "true" if escalated else "false",
    }


def collect_aging_signals(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pages = decisions + judgments
    overdue = sorted(
        [page for page in pages if page.get("overdue_review") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
    escalated = sorted(
        [page for page in pages if page.get("escalation_candidate") == "true"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("escalate_after", "") or "9999", page["title"].lower()),
    )
    scheduled = sorted(
        [page for page in pages if page.get("aging_state") == "scheduled"],
        key=lambda page: (-page_focus_score(active_protocol, page), page.get("revisit_after", "") or "9999", page["title"].lower()),
    )
    return {
        "overdue": overdue,
        "escalated": escalated,
        "scheduled": scheduled,
    }


def display_curated_status(status: str) -> str:
    mapping = {
        "filed": "已归档",
        "proposed": "待决策",
        "approved": "已批准",
        "needs-revisit": "待复审",
        "superseded": "已替代",
        "tentative": "暂定判断",
        "tracking": "持续观察",
        "confirmed": "已确认",
        "rejected": "已否决",
    }
    return mapping.get(status, status or "unknown")


def curated_page_template(
    *,
    kind: str,
    protocol: str,
    title: str,
    artifact_ref: str,
    filed_at: str,
    revisit_after: str,
    escalate_after: str,
    supporting_body: str,
) -> list[str]:
    origin_block = [
        "## Origin",
        f"- Filed from: `{artifact_ref}`",
        f"- Filed at: `{filed_at}`",
        f"- Protocol: `{protocol}`",
        "",
    ]
    if kind == "derived":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Filed Content",
            supporting_body,
        ]
    if kind == "decision":
        if protocol == "investing":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Position Decision",
                "- State the action: observe, build, add, trim, exit, or reject.",
                "",
                "## Scope And Sizing",
                "- Record the position scope, sizing guardrails, or watchlist boundary.",
                "",
                "## Thesis",
                "- Summarize the thesis and the supporting evidence.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Bear Case And Invalidation",
                "- Record the counter-thesis, invalidation triggers, and stop conditions.",
                "",
                "## Catalysts And Revisit",
                "- Record the next earnings/event/catalyst and what to monitor before revisiting.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the action is approved, resized, exited, or invalidated.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "research":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Architecture Decision",
                "- State the action: adopt, reject, defer, migrate, or rollback.",
                "",
                "## Affected Surface",
                "- Record the systems, components, teams, or experiments affected.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Validation Plan",
                "- Define the benchmark, test, or rollout signal that would validate this decision.",
                "",
                "## Rollback And Risks",
                "- Record regression risks, rollback path, and explicit failure conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the rollout result, benchmark, or regression signal changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "product":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Product Decision",
                "- State the action: prioritize, launch, roll out, deprecate, or pause.",
                "",
                "## User Problem And Bet",
                "- Record the target user problem, the product bet, and the expected behavior change.",
                "",
                "## Metric And Validation",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the primary metric, rollout checkpoint, or validation signal.",
                "",
                "## Launch Risks And Rollback",
                "- Record launch blockers, segment risk, and rollback/containment conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when launch readiness, metric movement, or the product bet changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "ops":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Incident Decision",
                "- State the action: mitigate, roll back, fail over, isolate, escalate, or follow up.",
                "",
                "## Incident Scope",
                "- Record the impacted service, blast radius, owner, and current operational state.",
                "",
                "## Mitigation Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the signal that shows mitigation is working.",
                "",
                "## Residual Risk And Follow-up",
                "- Record rollback/failover paths, residual risk, and follow-up owner.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the incident state, blast radius, or owner changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Decision",
            "- State the concrete decision here.",
            "",
            "## Why",
            "- Summarize the rationale and tradeoffs.",
            "",
            "## Evidence",
            f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
            "",
            "## Risks And Revisit",
            "- Record what could invalidate this decision and when to revisit it.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `proposed`",
            "- Review this page when the decision is approved, superseded, or needs revisit.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "investing":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Investment Judgment",
            "- State the thesis or judgment call here.",
            "",
            "## Drivers And Catalysts",
            f"- Summarize the key drivers and catalysts from `{artifact_ref}` and supporting sources.",
            "",
            "## Risks And Invalidation",
            "- Record the main risks, disconfirming signals, and invalidation conditions.",
            "",
            "## Confidence And Watchlist",
            "- Keep confidence explicit and list the next datapoints to watch.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the thesis strengthens, weakens, or is invalidated.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "research":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Research Judgment",
            "- State the hypothesis, expected gain, or architecture judgment here.",
            "",
            "## Supporting Evidence",
            f"- Summarize benchmark, experiment, or source evidence from `{artifact_ref}` and `wiki/sources/*.md`.",
            "",
            "## Counter Evidence",
            "- Record the regression risks, weak signals, or conflicting results.",
            "",
            "## Open Questions",
            "- List what remains uncertain and what experiment should resolve it.",
            "",
            "## Confidence And Next Experiment",
            "- Keep confidence explicit and name the next benchmark or follow-up check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new benchmark, regression, or experiment evidence arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "product":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Product Judgment",
            "- State the insight, product bet, or launch-readiness judgment here.",
            "",
            "## User Signal And Evidence",
            f"- Summarize user signal, metric evidence, or rollout data from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Signals",
            "- Record what user, metric, or launch evidence could invalidate this judgment.",
            "",
            "## Confidence And Next Validation",
            "- Keep confidence explicit and name the next validation checkpoint, release, or metric review.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the signal strengthens, weakens, or the launch plan changes.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "ops":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Ops Judgment",
            "- State the root-cause, blast-radius, or operational-risk judgment here.",
            "",
            "## Incident Evidence",
            f"- Summarize incident timeline, logs, or runbook evidence from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Evidence",
            "- Record what would falsify this root-cause or operational-risk judgment.",
            "",
            "## Confidence And Follow-up",
            "- Keep confidence explicit and name the next incident review, runbook update, or mitigation check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new incident evidence, residual risk, or follow-up status arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    return [
        f"# {title}",
        "",
        *origin_block,
        "## Judgment",
        "- State the judgment call here.",
        "",
        "## Signals",
        f"- Summarize the signals from `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence.",
        "",
        "## Counterevidence",
        "- Record what could make this judgment wrong.",
        "",
        "## Confidence And Follow-up",
        "- Keep confidence explicit and list what to watch next.",
        f"- Default revisit window: `{revisit_after or 'none'}`",
        f"- Default escalation window: `{escalate_after or 'none'}`",
        *render_curated_asset_sections(
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        ),
        "",
        "## Review Status",
        "- Current status: `tentative`",
        "- Review this page when the judgment is confirmed, rejected, or moved to active tracking.",
        "",
        "## Review Notes",
        "- No review has been recorded yet.",
        *render_review_history_section(),
        "",
        "## Supporting Artifact",
        supporting_body,
    ]


def action_needs_review(status: str) -> bool:
    return status in PENDING_ACTION_STATUSES


def display_action_status(status: str) -> str:
    mapping = {
        "proposed": "待处理",
        "accepted": "已接受",
        "deferred": "暂缓",
        "resolved": "已解决",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_needs_review(status: str) -> bool:
    return status in PENDING_REWRITE_PROPOSAL_STATUSES


def display_rewrite_proposal_status(status: str) -> str:
    mapping = {
        "proposed": "待审提案",
        "accepted": "已接受提案",
        "deferred": "暂缓提案",
        "applied": "已应用",
        "rejected": "已拒绝",
    }
    return mapping.get(status, status or "unknown")


def rewrite_proposal_status_rank(status: str) -> int:
    return {"proposed": 0, "accepted": 1, "deferred": 2, "applied": 3, "rejected": 4}.get(status, 9)


def transition_profile(
    allowed_transitions: list[str],
    *,
    preferred_transitions: list[str] | None = None,
    default_transition: str = "",
) -> dict[str, Any]:
    allowed = [str(item).strip() for item in allowed_transitions if str(item).strip()]
    preferred = [str(item).strip() for item in (preferred_transitions or []) if str(item).strip() in allowed]
    default_value = str(default_transition or "").strip()
    if default_value not in allowed:
        default_value = preferred[0] if preferred else (allowed[0] if allowed else "")
    return {
        "allowed_transitions": allowed,
        "preferred_transitions": preferred,
        "default_transition": default_value,
    }


def curated_page_transition_profile(kind: str, status: str) -> dict[str, Any]:
    if kind == "decision":
        if status == "proposed":
            return transition_profile(
                ["approved", "needs-revisit", "superseded"],
                preferred_transitions=["approved", "needs-revisit"],
                default_transition="approved",
            )
        if status == "approved":
            return transition_profile(
                ["needs-revisit", "superseded"],
                preferred_transitions=["needs-revisit"],
                default_transition="needs-revisit",
            )
        if status == "needs-revisit":
            return transition_profile(
                ["approved", "superseded"],
                preferred_transitions=["approved"],
                default_transition="approved",
            )
        return transition_profile([])
    if kind == "judgment":
        if status == "tentative":
            return transition_profile(
                ["tracking", "confirmed", "rejected"],
                preferred_transitions=["tracking", "confirmed"],
                default_transition="tracking",
            )
        if status == "tracking":
            return transition_profile(
                ["confirmed", "rejected"],
                preferred_transitions=["confirmed"],
                default_transition="confirmed",
            )
        if status == "confirmed":
            return transition_profile(
                ["tracking", "rejected"],
                preferred_transitions=["tracking"],
                default_transition="tracking",
            )
        return transition_profile([])
    return transition_profile([])


def rewrite_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["deferred", "rejected"],
            preferred_transitions=["deferred"],
            default_transition="deferred",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "rejected"],
            preferred_transitions=["accepted"],
            default_transition="accepted",
        )
    return transition_profile([])


def action_transition_profile(status: str) -> dict[str, Any]:
    if status == "proposed":
        return transition_profile(
            ["accepted", "deferred", "rejected"],
            preferred_transitions=["accepted", "deferred"],
            default_transition="accepted",
        )
    if status == "accepted":
        return transition_profile(
            ["resolved", "deferred", "rejected"],
            preferred_transitions=["resolved", "deferred"],
            default_transition="resolved",
        )
    if status == "deferred":
        return transition_profile(
            ["accepted", "resolved", "rejected"],
            preferred_transitions=["accepted", "resolved"],
            default_transition="accepted",
        )
    return transition_profile([])


def archive_transition_profile(*, can_apply: bool, can_revert: bool) -> dict[str, Any]:
    if can_apply:
        return transition_profile(["apply"], preferred_transitions=["apply"], default_transition="apply")
    if can_revert:
        return transition_profile(["revert"], preferred_transitions=["revert"], default_transition="revert")
    return transition_profile([])


def sort_curated_pages(pages: list[dict[str, str]]) -> list[dict[str, str]]:
    def sort_key(page: dict[str, str]) -> tuple[str, str]:
        return (page.get("reviewed_at", "") or page.get("updated_at", ""), page["title"].lower())

    return sorted(pages, key=sort_key, reverse=True)


def collect_curated_pages(root: Path, folder: str, expected_kind: str) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        status = str(frontmatter.get("status") or default_curated_status(expected_kind))
        reviewed_at = str(frontmatter.get("reviewed_at") or "")
        updated_at = str(frontmatter.get("last_compiled_at") or "")
        protocol = str(frontmatter.get("protocol") or DEFAULT_PROTOCOL)
        revisit_after = str(frontmatter.get("revisit_after") or "")
        escalate_after = str(frontmatter.get("escalate_after") or "")
        if not revisit_after and not escalate_after:
            base_timestamp = reviewed_at or updated_at or utc_now()
            revisit_after, escalate_after = schedule_review_windows(
                expected_kind,
                status,
                base_timestamp,
                protocol=protocol,
            )
        asset_snapshots = {
            heading: curated_asset_section_snapshot(
                content,
                heading,
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            )
            for heading in CURATED_ASSET_SECTION_ORDER
        }
        citations = [
            str(path)
            for path in frontmatter.get("citations", [])
            if isinstance(path, str) and path.strip()
        ]
        citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
        review_entries = review_history_entries(content)
        asset_score = sum(1 for snapshot in asset_snapshots.values() if snapshot.get("meaningful"))
        pages.append(
            {
                "page_id": str(frontmatter.get("id") or path.stem),
                "title": str(frontmatter.get("title") or path.stem),
                "path": relative_path(root, path),
                "kind": str(frontmatter.get("kind") or ""),
                "status": status,
                "protocol": protocol,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "updated_at": updated_at,
                "revisit_after": revisit_after,
                "escalate_after": escalate_after,
                "matches_expected_kind": str(frontmatter.get("kind") or "") == expected_kind,
                "pending_review": "true" if page_needs_review(expected_kind, status) else "false",
                "asset_score": str(asset_score),
                "has_counter_evidence": "true" if asset_snapshots["Counter Evidence"]["meaningful"] else "false",
                "has_invalidation": "true" if asset_snapshots["Invalidation"]["meaningful"] else "false",
                "has_next_signals": "true" if asset_snapshots["Next Signals"]["meaningful"] else "false",
                "has_review_history": "true" if asset_snapshots["Review History"]["meaningful"] else "false",
                "review_history_entries": str(asset_snapshots["Review History"]["review_history_entries"]),
                "latest_review_history_entry": review_entries[0] if review_entries else "",
                "citation_count": str(len(citations)),
                "citation_snapshot_count": str(len(citation_snapshot_state["recorded"])),
                "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
                "citation_drift_count": str(len(citation_snapshot_state["drifted"])),
                "citation_snapshot_gap_count": str(
                    len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
                ),
            }
        )
    enriched: list[dict[str, str]] = []
    for page in pages:
        enriched_page = dict(page)
        enriched_page.update(evaluate_page_aging(enriched_page, now=now))
        enriched.append(enriched_page)
    return sort_curated_pages(enriched)


def review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, list[dict[str, str]]]:
    pending_decisions = sorted(
        [page for page in decisions if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    pending_judgments = sorted(
        [page for page in judgments if page.get("pending_review") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("revisit_after", "") or "9999",
            page["title"].lower(),
        ),
    )
    reviewed = [
        page
        for page in decisions + judgments
        if page.get("reviewed_at") and page.get("pending_review") != "true"
    ]
    reviewed = sorted(reviewed, key=lambda page: (page.get("reviewed_at", ""), page["title"].lower()), reverse=True)
    return {
        "pending_decisions": pending_decisions,
        "pending_judgments": pending_judgments,
        "recently_reviewed": reviewed,
    }


def knowledge_lifecycle_invalidation_signals(page: dict[str, str]) -> list[str]:
    signals: list[str] = []
    if str(page.get("status") or "") == "needs-revisit":
        signals.append("explicit-needs-revisit")
    if page.get("citation_drift") == "true":
        signals.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        signals.append("citation-snapshot-gap")
    if page.get("overdue_review") == "true":
        signals.append("overdue-review")
    if page.get("escalation_candidate") == "true":
        signals.append("escalation-candidate")
    return signals


def knowledge_lifecycle_active_corpus_ids(
    source_ids: list[str],
    active_corpora: list[dict[str, Any]],
    *,
    concept_slug: str = "",
) -> list[str]:
    source_id_set = {source_id for source_id in source_ids if source_id}
    active_ids: list[str] = []
    for corpus in active_corpora:
        if str(corpus.get("status") or "") not in {"active", "cooling"}:
            continue
        corpus_id = str(corpus.get("corpus_id") or "")
        if not corpus_id:
            continue
        if concept_slug:
            concept_slugs = {str(item) for item in corpus.get("concept_slugs", []) if isinstance(item, str)}
            if concept_slug in concept_slugs and corpus_id not in active_ids:
                active_ids.append(corpus_id)
                continue
        if not source_id_set:
            continue
        corpus_source_ids = {
            str(item)
            for item in [*(corpus.get("source_ids", []) or []), *(corpus.get("bridge_evidence_ids", []) or [])]
            if isinstance(item, str)
        }
        if source_id_set & corpus_source_ids:
            active_ids.append(corpus_id)
    return sorted(active_ids)


def knowledge_lifecycle_classification(
    *,
    status: str,
    pending_review: bool,
    invalidation_signals: list[str],
    active_corpus_ids: list[str],
) -> tuple[str, list[str]]:
    if status in {"superseded", "rejected"}:
        return "retired", ["terminal-status"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if pending_review:
        return "review", ["pending-review-status"]
    if active_corpus_ids and status in {"approved", "confirmed"}:
        return "active", ["active-corpus-linked"]
    return "deferred", ["reviewed-idle"]


def concept_lifecycle_invalidation_signals(quality_record: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if quality_record.get("conflict_signals"):
        signals.append("concept-conflict")
    if quality_record.get("gap_signals"):
        signals.append("concept-evidence-gap")
    return signals


def concept_lifecycle_review_signals(
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
    *,
    active_corpus_ids: list[str],
) -> list[str]:
    signals: list[str] = []
    proposal_status = str(rewrite_proposal.get("status") or "")
    if rewrite_proposal.get("active") and rewrite_proposal.get("pending_review") == "true":
        if proposal_status == "accepted":
            signals.append("rewrite-proposal-accepted")
        elif proposal_status == "deferred":
            signals.append("rewrite-proposal-deferred")
        else:
            signals.append("rewrite-proposal-proposed")
    if rewrite_proposal.get("apply_ready"):
        signals.append("rewrite-apply-ready")
    if active_corpus_ids and str(quality_record.get("quality_state") or "") != "stable":
        signals.append("active-quality-pressure")
    return signals


def concept_lifecycle_classification(
    *,
    source_ids: list[str],
    active_corpus_ids: list[str],
    invalidation_signals: list[str],
    review_signals: list[str],
) -> tuple[str, list[str]]:
    if not source_ids:
        return "retired", ["no-source-pages"]
    if invalidation_signals:
        return "revisit", ["invalidation-signal", *invalidation_signals]
    if review_signals:
        return "review", ["quality-review", *review_signals]
    if active_corpus_ids:
        return "active", ["active-corpus-linked"]
    return "deferred", ["compiled-idle"]


def build_knowledge_lifecycle_entry(
    root: Path,
    page: dict[str, str],
    *,
    expected_kind: str,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
) -> dict[str, Any]:
    page_path = root / str(page.get("path") or "")
    content = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
    frontmatter = parse_frontmatter(content)
    citations = [
        str(item)
        for item in frontmatter.get("citations", [])
        if isinstance(item, str) and item.strip()
    ]
    if not citations and content:
        citations = extract_provenance_paths(root, content)
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(source_ids, active_corpora)
    invalidation_signals = knowledge_lifecycle_invalidation_signals(page)
    lifecycle_state, reason_codes = knowledge_lifecycle_classification(
        status=str(page.get("status") or ""),
        pending_review=page.get("pending_review") == "true",
        invalidation_signals=invalidation_signals,
        active_corpus_ids=active_corpus_ids,
    )
    return {
        "page_id": str(frontmatter.get("id") or Path(str(page.get("path") or "")).stem),
        "title": str(page.get("title") or frontmatter.get("title") or Path(str(page.get("path") or "")).stem),
        "path": str(page.get("path") or ""),
        "kind": expected_kind,
        "protocol": str(page.get("protocol") or frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        "status": str(page.get("status") or ""),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": page.get("pending_review") == "true",
        "overdue_review": page.get("overdue_review") == "true",
        "escalation_candidate": page.get("escalation_candidate") == "true",
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": int(page.get("citation_count", "0") or "0"),
        "citation_drift": page.get("citation_drift") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "confidence": str(page.get("confidence") or ""),
    }


def build_concept_lifecycle_entry(
    root: Path,
    path: Path,
    *,
    path_to_entry_id: dict[str, str],
    active_corpora: list[dict[str, Any]],
    quality_record: dict[str, Any],
    rewrite_proposal: dict[str, Any],
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    slug = path.stem
    source_pages = [
        str(item)
        for item in frontmatter.get("source_pages", [])
        if isinstance(item, str) and item.strip()
    ]
    source_ids = entry_ids_from_paths(path_to_entry_id, source_pages)
    active_corpus_ids = knowledge_lifecycle_active_corpus_ids(
        source_ids,
        active_corpora,
        concept_slug=slug,
    )
    invalidation_signals = concept_lifecycle_invalidation_signals(quality_record)
    review_signals = concept_lifecycle_review_signals(
        quality_record,
        rewrite_proposal,
        active_corpus_ids=active_corpus_ids,
    )
    lifecycle_state, reason_codes = concept_lifecycle_classification(
        source_ids=source_ids,
        active_corpus_ids=active_corpus_ids,
        invalidation_signals=invalidation_signals,
        review_signals=review_signals,
    )
    return {
        "page_id": str(frontmatter.get("id") or f"concept-{slug}"),
        "title": str(frontmatter.get("title") or path.stem),
        "path": relative_path(root, path),
        "kind": "concept",
        "protocol": "",
        "status": str(frontmatter.get("status") or "compiled"),
        "lifecycle_state": lifecycle_state,
        "reason_codes": reason_codes,
        "reviewed_at": "",
        "revisit_after": "",
        "escalate_after": "",
        "aging_state": "",
        "pending_review": bool(review_signals),
        "overdue_review": False,
        "escalation_candidate": False,
        "source_ids": source_ids,
        "active_corpus_ids": active_corpus_ids,
        "invalidation_signals": invalidation_signals,
        "citation_count": 0,
        "citation_drift": False,
        "citation_drift_count": 0,
        "citation_snapshot_gap_count": 0,
        "review_history_entries": 0,
        "asset_score": 0,
        "confidence": str(frontmatter.get("confidence") or ""),
        "source_pages": source_pages,
        "source_signature": str(frontmatter.get("source_signature") or ""),
        "quality_state": str(quality_record.get("quality_state") or "stable"),
        "issues": list(quality_record.get("issues") or []),
        "rewrite_priority": str(quality_record.get("rewrite_priority") or "low"),
        "rewrite_strategy": str(quality_record.get("rewrite_strategy") or ""),
        "review_signal_codes": review_signals,
        "rewrite_proposal_status": str(rewrite_proposal.get("status") or ""),
        "rewrite_pending_review": rewrite_proposal.get("pending_review") == "true",
        "rewrite_apply_ready": bool(rewrite_proposal.get("apply_ready")),
        "source_count": int(quality_record.get("source_count") or len(source_pages)),
        "related_count": int(quality_record.get("related_count") or 0),
        "override_active": False,
        "override_state": "",
        "override_reason_codes": [],
        "override_note": "",
        "override_updated_at": "",
        "override_source": "",
    }


def apply_knowledge_lifecycle_override(
    entry: dict[str, Any],
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(entry)
    if not override or not bool(override.get("active")):
        return normalized
    override_state = str(override.get("lifecycle_state") or "")
    if override_state not in KNOWLEDGE_LIFECYCLE_STATES:
        return normalized
    override_reason_codes = [
        str(reason)
        for reason in override.get("reason_codes", [])
        if isinstance(reason, str) and reason.strip()
    ]
    normalized["derived_lifecycle_state"] = str(entry.get("lifecycle_state") or "")
    normalized["derived_reason_codes"] = list(entry.get("reason_codes") or [])
    normalized["override_active"] = True
    normalized["override_state"] = override_state
    normalized["override_reason_codes"] = override_reason_codes
    normalized["override_note"] = str(override.get("note") or "")
    normalized["override_updated_at"] = str(override.get("updated_at") or override.get("applied_at") or "")
    normalized["override_source"] = str(override.get("operation") or "manual-runtime")
    normalized["lifecycle_state"] = override_state
    normalized["reason_codes"] = ["manual-override", *(override_reason_codes or [f"manual-{override_state}"])]
    if override_state == "retired":
        normalized["pending_review"] = False
        normalized["overdue_review"] = False
        normalized["escalation_candidate"] = False
    return normalized


def knowledge_lifecycle_counts(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_state = {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}
    by_kind = {kind: {"total": 0, "by_state": {state: 0 for state in KNOWLEDGE_LIFECYCLE_STATES}} for kind in KNOWLEDGE_LIFECYCLE_KINDS}
    invalidated = 0
    active_corpus_linked = 0
    for entry in entries:
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        kind = str(entry.get("kind") or "")
        if lifecycle_state in by_state:
            by_state[lifecycle_state] += 1
        if kind in by_kind:
            by_kind[kind]["total"] += 1
            if lifecycle_state in by_kind[kind]["by_state"]:
                by_kind[kind]["by_state"][lifecycle_state] += 1
        if entry.get("invalidation_signals"):
            invalidated += 1
        if entry.get("active_corpus_ids"):
            active_corpus_linked += 1
    return {
        "total": len(entries),
        "by_state": by_state,
        "by_kind": by_kind,
        "invalidated": invalidated,
        "active_corpus_linked": active_corpus_linked,
    }


def display_knowledge_lifecycle_state(state: str) -> str:
    mapping = {
        "active": "活跃",
        "review": "待审",
        "deferred": "暂挂",
        "retired": "已退役",
        "revisit": "待回看",
    }
    return mapping.get(state, state or "unknown")


def display_protocol_relevance_mode(mode: str) -> str:
    mapping = {
        "source-top1": "top1",
        "strong-top2": "strong-top2",
        "cross-protocol-bridge": "bridge-top2",
    }
    return mapping.get(mode, mode or "unknown")


def display_protocol_relevance_ambiguity(state: str) -> str:
    mapping = {
        "dominant": "dominant",
        "mixed": "mixed",
        "bridge": "bridge",
    }
    return mapping.get(state, state or "unknown")


def select_knowledge_lifecycle_entries(
    knowledge_lifecycle: dict[str, Any],
    *,
    kinds: set[str] | None = None,
    states: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for entry in knowledge_lifecycle.get("entries", []):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        lifecycle_state = str(entry.get("lifecycle_state") or "")
        if kinds is not None and kind not in kinds:
            continue
        if states is not None and lifecycle_state not in states:
            continue
        selected.append(dict(entry))
    return selected


def sort_knowledge_lifecycle_entries(
    entries: list[dict[str, Any]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> list[dict[str, Any]]:
    state_rank = {"revisit": 0, "review": 1, "active": 2, "deferred": 3, "retired": 4}
    return sorted(
        entries,
        key=lambda entry: (
            state_rank.get(str(entry.get("lifecycle_state") or ""), 9),
            0 if str(entry.get("protocol") or "") == active_protocol and active_protocol else 1,
            0 if bool(entry.get("override_active")) else 1,
            -len(entry.get("invalidation_signals", []) if isinstance(entry.get("invalidation_signals"), list) else []),
            -len(entry.get("active_corpus_ids", []) if isinstance(entry.get("active_corpus_ids"), list) else []),
            str(entry.get("title") or "").lower(),
        ),
    )


def render_knowledge_lifecycle_entry_summary(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or entry.get("page_id") or "unknown")
    path = str(entry.get("path") or "")
    kind = str(entry.get("kind") or "knowledge")
    lifecycle_state = str(entry.get("lifecycle_state") or "")
    parts = [
        f"kind `{kind}`",
        f"state `{display_knowledge_lifecycle_state(lifecycle_state)}`",
    ]
    if bool(entry.get("override_active")):
        parts.append(f"override `{str(entry.get('override_state') or lifecycle_state or 'unknown')}`")
    invalidation_signals = entry.get("invalidation_signals", [])
    if isinstance(invalidation_signals, list) and invalidation_signals:
        parts.append(f"invalidation `{','.join(str(item) for item in invalidation_signals[:3])}`")
    active_corpus_ids = entry.get("active_corpus_ids", [])
    if isinstance(active_corpus_ids, list) and active_corpus_ids:
        parts.append(f"active_corpora `{len(active_corpus_ids)}`")
    review_signal_codes = entry.get("review_signal_codes", [])
    if isinstance(review_signal_codes, list) and review_signal_codes:
        parts.append(f"review_signals `{','.join(str(item) for item in review_signal_codes[:3])}`")
    reason_codes = entry.get("reason_codes", [])
    if isinstance(reason_codes, list) and reason_codes:
        parts.append(f"reasons `{','.join(str(item) for item in reason_codes[:3])}`")
    protocol_relevance_mode = str(entry.get("protocol_relevance_primary_mode") or "")
    if protocol_relevance_mode:
        parts.append(f"protocol_relevance `{display_protocol_relevance_mode(protocol_relevance_mode)}`")
    protocol_relevance_ambiguity = str(entry.get("protocol_relevance_ambiguity") or "")
    if protocol_relevance_ambiguity:
        parts.append(f"protocol_ambiguity `{display_protocol_relevance_ambiguity(protocol_relevance_ambiguity)}`")
    return f"- [{title}](../../{path}) | " + " | ".join(parts)


def knowledge_lifecycle_governance_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    concept_counts = (
        knowledge_lifecycle.get("counts", {})
        .get("by_kind", {})
        .get("concept", {})
        .get("by_state", {})
    )
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "counts": {
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": int(concept_counts.get("active", 0) or 0),
            "deferred_concepts": int(concept_counts.get("deferred", 0) or 0),
        },
    }


def concept_protocol_relevance_for_source(
    source_id: str,
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    routing_entry = routing_by_entry_id.get(source_id, {})
    if not isinstance(routing_entry, dict):
        return {}
    top_protocols = [
        str(item.get("protocol") or "")
        for item in routing_entry.get("top_protocols", [])
        if isinstance(item, dict) and str(item.get("protocol") or "")
    ]
    if protocol not in top_protocols[:2]:
        return {}
    routing_snapshot = routing_snapshot_for_protocol(routing_entry, protocol)
    if not routing_snapshot:
        return {}
    selected_as = str(routing_snapshot.get("selected_as") or "")
    if top_protocols[:1] == [protocol]:
        mode = "source-top1"
    elif bool(routing_entry.get("cross_protocol_bridge")) and selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "cross-protocol-bridge"
    elif selected_as in {"hot-evidence", "warm-evidence"}:
        mode = "strong-top2"
    else:
        return {}
    return {
        "source_id": source_id,
        "mode": mode,
        "selected_as": selected_as,
        "total_score": float(routing_snapshot.get("total_score", 0.0) or 0.0),
    }


def concept_protocol_relevance(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_ids = [str(item) for item in entry.get("source_ids", []) if isinstance(item, str) and item]
    if not source_ids:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    mode_rank = {"source-top1": 0, "cross-protocol-bridge": 1, "strong-top2": 2}
    matched_sources = [
        match
        for match in (
            concept_protocol_relevance_for_source(
                source_id,
                protocol=protocol,
                routing_by_entry_id=routing_by_entry_id,
            )
            for source_id in source_ids
        )
        if match
    ]
    if not matched_sources:
        return {"related": False, "primary_mode": "", "modes": [], "source_ids": []}
    matched_sources.sort(
        key=lambda item: (
            mode_rank.get(str(item.get("mode") or ""), 9),
            -float(item.get("total_score", 0.0) or 0.0),
            str(item.get("source_id") or ""),
        )
    )
    modes: list[str] = []
    matched_source_ids: list[str] = []
    for item in matched_sources:
        mode = str(item.get("mode") or "")
        source_id = str(item.get("source_id") or "")
        if mode and mode not in modes:
            modes.append(mode)
        if source_id and source_id not in matched_source_ids:
            matched_source_ids.append(source_id)
    return {
        "related": True,
        "primary_mode": modes[0] if modes else "",
        "modes": modes,
        "source_ids": matched_source_ids,
    }


def concept_protocol_ambiguity_state(modes: list[str]) -> str:
    normalized = [str(item) for item in modes if isinstance(item, str) and item]
    if "cross-protocol-bridge" in normalized:
        return "bridge"
    if normalized == ["source-top1"]:
        return "dominant"
    return "mixed"


def concept_lifecycle_matches_protocol(
    entry: dict[str, Any],
    *,
    protocol: str,
    routing_by_entry_id: dict[str, dict[str, Any]],
) -> bool:
    return bool(
        concept_protocol_relevance(
            entry,
            protocol=protocol,
            routing_by_entry_id=routing_by_entry_id,
        ).get("related")
    )


def protocol_related_concept_lifecycle_summary(
    knowledge_lifecycle: dict[str, Any] | None,
    material_routing: dict[str, Any] | None,
    *,
    protocol: str,
) -> dict[str, Any]:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    material_routing = material_routing or default_material_routing_state()
    routing_by_entry_id = {
        str(entry.get("entry_id") or ""): entry
        for entry in material_routing.get("entries", [])
        if isinstance(entry, dict) and entry.get("entry_id")
    }
    mode_counts = {
        "source-top1": 0,
        "strong-top2": 0,
        "cross-protocol-bridge": 0,
    }
    ambiguity_counts = {
        "dominant": 0,
        "mixed": 0,
        "bridge": 0,
    }
    related_entries: list[dict[str, Any]] = []
    for entry in select_knowledge_lifecycle_entries(knowledge_lifecycle, kinds={"concept"}):
        relevance = concept_protocol_relevance(entry, protocol=protocol, routing_by_entry_id=routing_by_entry_id)
        if not relevance.get("related"):
            continue
        primary_mode = str(relevance.get("primary_mode") or "")
        ambiguity = concept_protocol_ambiguity_state(list(relevance.get("modes", [])))
        if primary_mode in mode_counts:
            mode_counts[primary_mode] += 1
        if ambiguity in ambiguity_counts:
            ambiguity_counts[ambiguity] += 1
        related_entries.append(
            {
                **entry,
                "protocol_relevance_primary_mode": primary_mode,
                "protocol_relevance_modes": list(relevance.get("modes", [])),
                "protocol_relevance_source_ids": list(relevance.get("source_ids", [])),
                "protocol_relevance_ambiguity": ambiguity,
            }
        )
    related_concepts = sort_knowledge_lifecycle_entries(related_entries, active_protocol=protocol)
    concept_backlog = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") in {"review", "revisit"}
    ]
    review_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "review"]
    revisit_concepts = [entry for entry in concept_backlog if str(entry.get("lifecycle_state") or "") == "revisit"]
    retired_concepts = [
        entry for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "retired"
    ]
    ambiguity_watchlist = [
        entry
        for entry in related_concepts
        if str(entry.get("protocol_relevance_ambiguity") or "") in {"mixed", "bridge"}
    ]
    mixed_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "mixed"
    ]
    bridge_concepts = [
        entry for entry in ambiguity_watchlist if str(entry.get("protocol_relevance_ambiguity") or "") == "bridge"
    ]
    return {
        "concept_backlog": concept_backlog,
        "review_concepts": review_concepts,
        "revisit_concepts": revisit_concepts,
        "retired_concepts": retired_concepts,
        "ambiguity_watchlist": ambiguity_watchlist,
        "mixed_concepts": mixed_concepts,
        "bridge_concepts": bridge_concepts,
        "counts": {
            "related_concepts": len(related_concepts),
            "concept_backlog": len(concept_backlog),
            "review_concepts": len(review_concepts),
            "revisit_concepts": len(revisit_concepts),
            "retired_concepts": len(retired_concepts),
            "active_concepts": sum(
                1 for entry in related_concepts if str(entry.get("lifecycle_state") or "") == "active"
            ),
            "direct_related_concepts": mode_counts["source-top1"],
            "secondary_related_concepts": mode_counts["strong-top2"],
            "bridge_related_concepts": mode_counts["cross-protocol-bridge"],
            "dominant_related_concepts": ambiguity_counts["dominant"],
            "mixed_related_concepts": ambiguity_counts["mixed"],
            "ambiguity_bridge_concepts": ambiguity_counts["bridge"],
        },
        "inference_mode": "source-top1-plus-strong-top2-plus-cross-protocol-bridge",
        "ambiguity_mode": "dominant-vs-mixed-vs-bridge",
    }


def refresh_knowledge_lifecycle_state(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = build_knowledge_lifecycle_document(
        root,
        generated_at=generated_at,
        decisions=decisions,
        judgments=judgments,
        entries=entries,
        active_corpora_state=active_corpora_state,
        memory=memory,
    )
    save_knowledge_lifecycle_state(root, document)
    return document


def build_knowledge_lifecycle_document(
    root: Path,
    *,
    generated_at: str,
    decisions: list[dict[str, str]] | None = None,
    judgments: list[dict[str, str]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    active_corpora_state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_layout(root)
    override_state = ensure_knowledge_lifecycle_override_state(root)
    active_overrides = active_knowledge_lifecycle_overrides(override_state)
    manifest_entries = entries if entries is not None else load_manifest(root).get("entries", [])
    _entry_by_id, path_to_entry_id = entry_lookup_maps(manifest_entries)
    decision_pages = decisions if decisions is not None else collect_curated_pages(root, "decisions", "decision")
    judgment_pages = judgments if judgments is not None else collect_curated_pages(root, "judgments", "judgment")
    concept_memory = memory if memory is not None else load_machine_memory(root)
    concept_quality = build_concept_quality(root, concept_memory) if concept_memory else {
        "weak_concepts": [],
        "stable_concepts": [],
    }
    concept_quality_by_slug = {
        str(record.get("slug") or ""): dict(record)
        for record in (concept_quality.get("all_concepts", []) or [])
        if isinstance(record, dict) and record.get("slug")
    }
    concept_rewrite_by_slug = {
        str(proposal.get("slug") or ""): dict(proposal)
        for proposal in load_concept_rewrite_state(root).get("proposals", [])
        if isinstance(proposal, dict) and proposal.get("slug")
    }
    active_corpora = [
        dict(corpus)
        for corpus in (active_corpora_state or load_active_corpora_state(root)).get("corpora", [])
        if isinstance(corpus, dict)
    ]
    lifecycle_entries = [
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="decision",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in decision_pages
        ],
        *[
            build_knowledge_lifecycle_entry(
                root,
                page,
                expected_kind="judgment",
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
            )
            for page in judgment_pages
        ],
        *[
            build_concept_lifecycle_entry(
                root,
                path,
                path_to_entry_id=path_to_entry_id,
                active_corpora=active_corpora,
                quality_record=concept_quality_by_slug.get(
                    path.stem,
                    {
                        "slug": path.stem,
                        "quality_state": "stable",
                        "issues": [],
                        "rewrite_priority": "low",
                        "rewrite_strategy": "",
                        "source_count": 0,
                        "related_count": 0,
                    },
                ),
                rewrite_proposal=concept_rewrite_by_slug.get(path.stem, {}),
            )
            for path in sorted((root / "wiki" / "concepts").glob("*.md"))
        ],
    ]
    lifecycle_entries = [
        apply_knowledge_lifecycle_override(entry, active_overrides.get(str(entry.get("path") or "")))
        if str(entry.get("kind") or "") == "concept"
        else entry
        for entry in lifecycle_entries
    ]
    document = {
        "version": 1,
        "generated_at": generated_at,
        "entries": lifecycle_entries,
        "counts": knowledge_lifecycle_counts(lifecycle_entries),
    }
    return document


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
    return (
        bool(action.get("active", True))
        and str(action.get("status") or "") == "accepted"
        and str(action.get("kind") or "") in LOW_RISK_APPLYABLE_ACTION_KINDS
    )


def execution_policy_profile(action: dict[str, Any]) -> dict[str, Any]:
    status = str(action.get("status") or "proposed")
    active = bool(action.get("active", True))
    if not active:
        return {
            "execution_policy": "inactive-history",
            "execution_band": "history-only",
            "capabilities": ["history"],
            "policy_summary": "信号已消失，只保留历史与审计价值。",
        }
    if status == "proposed":
        return {
            "execution_policy": "triage",
            "execution_band": "review-first",
            "capabilities": ["review"],
            "policy_summary": "先 review / triage，再决定是否进入 accepted。",
        }
    if status == "accepted" and action_supports_low_risk_apply(action):
        return {
            "execution_policy": "semi-auto-apply",
            "execution_band": "bundle-safe-apply",
            "capabilities": ["dry-run", "bundle-apply", "revert-safe", "history"],
            "policy_summary": "支持 dry-run、bundle-driven apply 和 receipt 驱动回滚。",
        }
    if status == "accepted":
        return {
            "execution_policy": "manual-repair",
            "execution_band": "manual-repair",
            "capabilities": ["manual-edit", "review"],
            "policy_summary": "只能走人工修复与 review，不开放 safe apply。",
        }
    if status == "deferred":
        return {
            "execution_policy": "parked",
            "execution_band": "deferred",
            "capabilities": ["resume-review", "history"],
            "policy_summary": "动作已暂缓，保留复查与恢复入口。",
        }
    return {
        "execution_policy": "closed",
        "execution_band": "closed",
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
        ordered_paths.append(".aiwiki/state/manual-links.json")

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
    if str(action.get("kind") or "") not in LOW_RISK_APPLYABLE_ACTION_KINDS:
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


def build_execution_bundle(
    root: Path,
    proposal: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    patch_steps: list[dict[str, Any]] = []
    for index, patch in enumerate(proposal.get("page_patch_plan", []), start=1):
        patch_steps.append(
            {
                "step": index,
                "path": str(patch.get("path") or ""),
                "role": str(patch.get("role") or ""),
                "role_label": str(patch.get("role_label") or patch.get("role") or "page"),
                "mode": str(patch.get("mode") or "update"),
                "sections": list(patch.get("sections") or []),
                "summary": str(patch.get("summary") or ""),
                "exists": bool(patch.get("exists", False)),
                "command_hint": str(patch.get("command_hint") or ""),
            }
        )
    bundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-compile",
        "compiled_at": compiled_at,
        "action_id": str(proposal.get("action_id") or ""),
        "title": str(proposal.get("title") or ""),
        "status": str(proposal.get("status") or "proposed"),
        "proposal_kind": str(proposal.get("proposal_kind") or "manual-repair"),
        "risk": str(proposal.get("risk") or "medium"),
        "priority": str(proposal.get("priority") or "medium"),
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "summary": str(proposal.get("summary") or ""),
        "target_paths": list(proposal.get("target_paths") or []),
        "suggested_edits": list(proposal.get("suggested_edits") or []),
        "proposal_path": str(proposal.get("proposal_path") or ""),
        "bundle_path": str(proposal.get("bundle_path") or ""),
        "page_patch_plan": patch_steps,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
        "command_hint": str(proposal.get("command_hint") or ""),
        "next_step": str(proposal.get("next_step") or ""),
        "dry_run_supported": bool(proposal.get("safe_apply_preview")),
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def execution_bundle_digest(bundle: dict[str, Any]) -> str:
    payload = {
        "action_id": str(bundle.get("action_id") or ""),
        "title": str(bundle.get("title") or ""),
        "status": str(bundle.get("status") or ""),
        "proposal_kind": str(bundle.get("proposal_kind") or ""),
        "risk": str(bundle.get("risk") or ""),
        "priority": str(bundle.get("priority") or ""),
        "protocol": str(bundle.get("protocol") or DEFAULT_PROTOCOL),
        "summary": str(bundle.get("summary") or ""),
        "target_paths": list(bundle.get("target_paths") or []),
        "suggested_edits": list(bundle.get("suggested_edits") or []),
        "page_patch_plan": list(bundle.get("page_patch_plan") or []),
        "safe_apply_preview": bundle.get("safe_apply_preview"),
        "command_hint": str(bundle.get("command_hint") or ""),
        "next_step": str(bundle.get("next_step") or ""),
        "dry_run_supported": bool(bundle.get("dry_run_supported")),
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def load_execution_bundle(path: Path) -> dict[str, Any]:
    document = load_json_document(path)
    if not isinstance(document, dict) or str(document.get("kind") or "") != "execution-bundle":
        raise RuntimeError(f"Invalid execution bundle: {path}")
    return document


def build_execution_receipt(
    root: Path,
    action: dict[str, Any],
    *,
    applied_at: str,
    note: str | None,
    proposal: dict[str, Any],
    operation: str = "apply",
    resulting_status: str = "resolved",
) -> dict[str, Any]:
    bundle = build_execution_bundle(root, proposal, compiled_at=applied_at)
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-apply-action",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": str(action.get("id") or ""),
        "title": str(action.get("title") or ""),
        "status": resulting_status,
        "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
        "apply_mode": "manual-link-state" if operation == "apply" else "manual-link-state-revert",
        "note": note or "",
        "primary_path": str(action.get("primary_path") or ""),
        "secondary_path": str(action.get("secondary_path") or ""),
        "receipt_path": relative_path(root, execution_receipt_path(root, str(action.get("id") or ""))),
        "bundle": bundle,
        "safe_apply_preview": proposal.get("safe_apply_preview"),
    }


def build_material_archive_bundle(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> dict[str, Any]:
    command_hint = (
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . revert-archive {entry_id}"
        if operation == "apply"
        else f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-archive {entry_id}"
    )
    action_id = material_archive_action_id(entry_id)
    bundle = {
        "version": 1,
        "kind": "execution-bundle",
        "generated_by": "aiwiki-material-archive",
        "compiled_at": applied_at,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "proposal_kind": "material-archive",
        "risk": "low",
        "priority": "low",
        "protocol": protocol,
        "summary": f"{operation} material archive override for `{entry_id}`.",
        "target_paths": [
            path
            for path in (
                source_path,
                relative_path(root, material_archive_state_path(root)),
                relative_path(root, material_state_path(root)),
            )
            if path
        ],
        "suggested_edits": [f"temperature `{current_temperature}` -> `{resulting_temperature}`"],
        "proposal_path": "",
        "bundle_path": "",
        "page_patch_plan": [],
        "safe_apply_preview": {
            "apply_mode": (
                "material-temperature-archive"
                if operation == "apply"
                else "material-temperature-archive-revert"
            ),
            "state_path": relative_path(root, material_archive_state_path(root)),
            "entry": {
                "entry_id": entry_id,
                "active": operation == "apply",
                "temperature": resulting_temperature,
            },
            "affected_paths": [
                path
                for path in (
                    source_path,
                    relative_path(root, material_archive_state_path(root)),
                    relative_path(root, material_state_path(root)),
                )
                if path
            ],
            "follow_up": "执行后会重跑 compile，让 material-state / archive-candidates / ask 排序同步收敛。",
        },
        "command_hint": command_hint,
        "next_step": "如需恢复材料，再执行对应的 revert-archive。",
        "dry_run_supported": False,
    }
    bundle["digest"] = execution_bundle_digest(bundle)
    return bundle


def build_material_archive_receipt(
    root: Path,
    *,
    entry_id: str,
    title: str,
    source_path: str,
    protocol: str,
    applied_at: str,
    note: str | None,
    operation: str,
    current_temperature: str,
    resulting_temperature: str,
) -> dict[str, Any]:
    action_id = material_archive_action_id(entry_id)
    receipt_path = execution_receipt_path(root, action_id)
    bundle = build_material_archive_bundle(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        operation=operation,
        current_temperature=current_temperature,
        resulting_temperature=resulting_temperature,
    )
    return {
        "version": 1,
        "kind": "execution-receipt",
        "generated_by": "aiwiki-material-archive",
        "applied_at": applied_at,
        "operation": operation,
        "action_id": action_id,
        "title": f"{'Archive' if operation == 'apply' else 'Restore'} {title}",
        "status": "resolved" if operation == "apply" else "proposed",
        "protocol": protocol,
        "subject_kind": "material-archive",
        "subject_id": entry_id,
        "apply_mode": "material-temperature-archive" if operation == "apply" else "material-temperature-archive-revert",
        "note": note or "",
        "primary_path": source_path,
        "secondary_path": "",
        "current_temperature": current_temperature,
        "resulting_temperature": resulting_temperature,
        "receipt_path": relative_path(root, receipt_path),
        "bundle": bundle,
        "safe_apply_preview": bundle.get("safe_apply_preview"),
    }


def append_execution_receipt_history(root: Path, receipt: dict[str, Any]) -> None:
    path = execution_receipt_history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")


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
        if path.stem in active_slugs:
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


def describe_machine_memory_action(action: dict[str, Any]) -> dict[str, str]:
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
    }
    next_step = kind_steps.get(kind, "检查这个 machine-memory 动作对应的页面。")
    command_hint = ""
    profile = execution_policy_profile(action)
    execution_policy = str(profile.get("execution_policy") or "triage")
    execution_band = str(profile.get("execution_band") or "review-first")
    capabilities = [str(item) for item in profile.get("capabilities", []) if isinstance(item, str) and item]
    if not active:
        next_step = "信号已消失；确认是否要作为已解决归档。"
        if status in PENDING_ACTION_STATUSES:
            command_hint = f'{review_prefix} --status resolved --note "Signal disappeared after compile."'
    elif status == "proposed":
        command_hint = f'{review_prefix} --status accepted --note "Accepted for manual repair."'
    elif status == "accepted":
        if action_supports_low_risk_apply(action):
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
        "execution_capabilities": ", ".join(capabilities) if capabilities else "none",
        "execution_capability_list": capabilities,
        "policy_summary": str(profile.get("policy_summary") or ""),
        "next_step": next_step,
        "command_hint": command_hint,
        "apply_ready": "true" if action_supports_low_risk_apply(action) else "false",
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
        action.update(describe_machine_memory_action(action))
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

    return {
        "ready_actions": ready_actions,
        "triage_actions": triage_actions,
        "deferred_actions": deferred_actions,
        "inactive_actions": inactive_actions[:12],
        "execution_batches": execution_batches[:10],
        "execution_proposals": execution_proposals,
        "counts": {
            "ready": len(ready_actions),
            "triage": len(triage_actions),
            "deferred": len(deferred_actions),
            "inactive": len(inactive_actions),
            "batches": len(execution_batches),
            "proposals": len(execution_proposals),
            "patch_steps": sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals),
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


def render_curated_page_summary(page: dict[str, str]) -> str:
    suffix_parts = [f"状态 `{display_curated_status(page.get('status', '') or 'unknown')}`"]
    protocol = page.get("protocol", "")
    if protocol:
        suffix_parts.append(f"协议 `{protocol}`")
    confidence = page.get("confidence", "")
    if confidence:
        suffix_parts.append(f"置信度 `{confidence}`")
    reviewed_at = page.get("reviewed_at", "")
    if reviewed_at:
        suffix_parts.append(f"审阅时间 `{reviewed_at}`")
    revisit_after = page.get("revisit_after", "")
    if revisit_after:
        suffix_parts.append(f"复审截止 `{revisit_after}`")
    if page.get("asset_score"):
        suffix_parts.append(f"资产 `{page.get('asset_score')}/4`")
    review_history_entries = int(page.get("review_history_entries", "0") or "0")
    if review_history_entries:
        suffix_parts.append(f"复审历史 `{review_history_entries}`")
    citation_drift_count = int(page.get("citation_drift_count", "0") or "0")
    citation_snapshot_gap_count = int(page.get("citation_snapshot_gap_count", "0") or "0")
    if page.get("citation_drift") == "true":
        suffix_parts.append(f"证据漂移 `{citation_drift_count or 1}`")
    if citation_snapshot_gap_count:
        suffix_parts.append(f"快照缺口 `{citation_snapshot_gap_count}`")
    if page.get("overdue_review") == "true":
        suffix_parts.append("已到期待复审")
    if page.get("escalation_candidate") == "true":
        suffix_parts.append("需要升级处理")
    return f"- [{page['title']}](../../{page['path']}) | " + " | ".join(suffix_parts)


def render_curated_index(
    heading: str,
    section_name: str,
    pages: list[dict[str, str]],
    compiled_at: str,
) -> str:
    pending_review = sum(1 for page in pages if page.get("pending_review") == "true")
    overdue_review = sum(1 for page in pages if page.get("overdue_review") == "true")
    escalated = sum(1 for page in pages if page.get("escalation_candidate") == "true")
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    status_counts: dict[str, int] = {}
    for page in pages:
        status = page.get("status", "") or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [
        f"# {heading}",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 页面总数：`{len(pages)}`",
        f"- 待审阅数量：`{pending_review}`",
        f"- 已到期数量：`{overdue_review}`",
        f"- 需要升级：`{escalated}`",
        f"- 证据漂移：`{len(drifted)}`",
        f"- 快照缺口：`{len(snapshot_gaps)}`",
        "",
        "## 状态统计",
    ]
    if not status_counts:
        lines.append("- 还没有相关页面。")
    else:
        for status, count in sorted(status_counts.items()):
            lines.append(f"- `{display_curated_status(status)}`：`{count}`")
    lines.extend(
        [
            "",
        f"## {section_name}",
        ]
    )
    if not pages:
        lines.append(f"- 还没有{section_name}。")
    else:
        for page in pages:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 证据漂移"])
    if not drifted:
        lines.append("- 当前没有检测到 citation drift。")
    else:
        for page in drifted[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gaps:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gaps[:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_judgment_assets(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> str:
    pages = sorted(
        decisions + judgments,
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            -(int(page.get("asset_score", "0") or "0")),
            page.get("title", "").lower(),
        ),
    )
    strong_assets = [page for page in pages if int(page.get("asset_score", "0") or "0") >= 3]
    missing_counter = [page for page in pages if page.get("has_counter_evidence") != "true"]
    missing_invalidation = [page for page in pages if page.get("has_invalidation") != "true"]
    missing_next_signals = [page for page in pages if page.get("has_next_signals") != "true"]
    missing_history = [page for page in pages if page.get("has_review_history") != "true"]
    lines = [
        "# 判断资产",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 资产完整（>= 3/4）：`{len(strong_assets)}`",
        f"- 缺反证：`{len(missing_counter)}`",
        f"- 缺失效条件：`{len(missing_invalidation)}`",
        f"- 缺下一信号：`{len(missing_next_signals)}`",
        f"- 缺复审历史：`{len(missing_history)}`",
        "",
        "## 强判断资产",
    ]
    if not strong_assets:
        lines.append("- 当前还没有资产完整度较高的 decision / judgment 页面。")
    else:
        for page in strong_assets[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Counter Evidence"])
    if not missing_counter:
        lines.append("- 当前所有判断资产都包含显式 counter evidence。")
    else:
        for page in missing_counter[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Invalidation"])
    if not missing_invalidation:
        lines.append("- 当前所有判断资产都包含显式 invalidation 条件。")
    else:
        for page in missing_invalidation[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Next Signals"])
    if not missing_next_signals:
        lines.append("- 当前所有判断资产都包含下一次观察信号。")
    else:
        for page in missing_next_signals[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Review History"])
    if not missing_history:
        lines.append("- 当前所有判断资产都已经积累复审历史。")
    else:
        for page in missing_history[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_cognitive_history(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    pages = sort_curated_pages(decisions + judgments)
    drifted_pages = sorted(
        [page for page in pages if page.get("citation_drift") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -int(page.get("citation_drift_count", "0") or "0"),
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )
    snapshot_gap_pages = sorted(
        [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("citation_snapshot_gap_count", "0") or "0"),
            0 if page.get("pending_review") == "true" else 1,
            page.get("title", "").lower(),
        ),
    )
    long_history_pages = sorted(
        [page for page in pages if int(page.get("review_history_entries", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("review_history_entries", "0") or "0"),
            page.get("reviewed_at", "") or "",
            page.get("title", "").lower(),
        ),
        reverse=True,
    )
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    lifecycle_entry_titles = {
        str(entry.get("path") or ""): str(entry.get("title") or entry.get("page_id") or "")
        for entry in knowledge_lifecycle.get("entries", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    concept_override_events: list[tuple[str, str, str, str]] = []
    for event in load_runtime_history(root):
        if str(event.get("event_type") or "") != "knowledge-lifecycle-override":
            continue
        if str(event.get("kind") or "") != "concept":
            continue
        occurred_at = str(event.get("occurred_at") or "")
        path = str(event.get("path") or "")
        title = lifecycle_entry_titles.get(path) or str(event.get("slug") or path or "unknown concept")
        operation = str(event.get("operation") or "override")
        lifecycle_state = str(event.get("lifecycle_state") or "")
        concept_override_events.append((occurred_at, title, path, f"{operation} -> {lifecycle_state or 'unknown'}"))
    concept_override_events.sort(key=lambda item: item[0], reverse=True)
    recent_events: list[tuple[str, str, str, str]] = []
    for page in pages:
        page_path = root / page["path"]
        if not page_path.exists():
            continue
        content = page_path.read_text(encoding="utf-8", errors="replace")
        for entry in review_history_entries(content)[:3]:
            match = re.match(r"- `([^`]+)`", entry)
            reviewed_at = match.group(1) if match else ""
            recent_events.append((reviewed_at, page["title"], page["path"], entry))
    recent_events.sort(key=lambda item: item[0], reverse=True)
    lines = [
        "# 认知历史",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- decision / judgment 页面：`{len(pages)}`",
        f"- 证据漂移页面：`{len(drifted_pages)}`",
        f"- snapshot 缺口页面：`{len(snapshot_gap_pages)}`",
        f"- 有复审历史的页面：`{len(long_history_pages)}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- concept lifecycle 事件：`{len(concept_override_events)}`",
        "",
        "## 证据漂移",
    ]
    if not drifted_pages:
        lines.append("- 当前没有 reviewed judgment / decision 因 citation drift 被标记。")
    else:
        for page in drifted_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gap_pages:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gap_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:16]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 概念生命周期事件"])
    if not concept_override_events:
        lines.append("- 当前还没有 concept lifecycle override 事件。")
    else:
        for occurred_at, title, path, detail in concept_override_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}"
            )
    lines.extend(["", "## 最近认知事件"])
    if not recent_events:
        lines.append("- 当前还没有 review history 事件。")
    else:
        for reviewed_at, title, path, entry in recent_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | reviewed `{reviewed_at or 'unknown'}` | {entry.replace(f'- `{reviewed_at}` | ', '') if reviewed_at else entry}"
            )
    lines.extend(["", "## 长历史页面"])
    if not long_history_pages:
        lines.append("- 当前还没有积累多轮复审历史的页面。")
    else:
        for page in long_history_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 建议动作",
        ]
    )
    if drifted_pages:
        lines.append(f"- 先复查 `{len(drifted_pages)}` 个被新证据挑战的 decision / judgment。")
    if snapshot_gap_pages:
        lines.append(f"- 补齐 `{len(snapshot_gap_pages)}` 个缺少 citation snapshot 的页面，避免 drift 失真。")
    if long_history_pages:
        lines.append(f"- 从 `{min(len(long_history_pages), 5)}` 个长历史页面里提炼更稳定的 judgment pattern。")
    if not any((drifted_pages, snapshot_gap_pages, long_history_pages)):
        lines.append("- 当前认知历史层比较干净，继续靠 nightly 累积 review history。")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def compact_section_lines(markdown: str, heading: str, *, fallback: str, limit: int = 5) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    if not section:
        return [fallback]
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    if not lines:
        return [fallback]
    if len(lines) > limit:
        return [*lines[:limit], "- ..."]
    return lines


def workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../{target})"


def pack_workspace_link(path: str, label: str | None = None) -> str:
    target = path.strip()
    display = label or target
    return f"[{display}](../../../{target})"


def load_workspace_markdown(root: Path, relative: str) -> tuple[dict[str, Any], str]:
    path = root / relative
    content = path.read_text(encoding="utf-8", errors="replace")
    return parse_frontmatter(content), content


def workspace_file_signature(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists() or not path.is_file():
        return ""
    return sha256_file(path)


def output_pack_review_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str,
) -> list[dict[str, str]]:
    pages = decisions + judgments
    return sorted(
        [
            page
            for page in pages
            if page.get("pending_review") == "true"
            or page.get("citation_drift") == "true"
            or page.get("overdue_review") == "true"
            or page.get("escalation_candidate") == "true"
        ],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            0 if page.get("citation_drift") == "true" else 1,
            0 if page.get("pending_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )


def output_pack_reviewed_candidates(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
) -> list[dict[str, str]]:
    return sort_curated_pages([page for page in decisions + judgments if page.get("reviewed_at") and page.get("pending_review") != "true"])


def output_pack_repair_plan_candidates(memory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    ready_actions = [
        action for action in repair_plan.get("ready_actions", []) if isinstance(action, dict) and action.get("active")
    ]
    execution_proposals = [
        proposal for proposal in repair_plan.get("execution_proposals", []) if isinstance(proposal, dict)
    ]
    return ready_actions, execution_proposals


def output_pack_state_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in record.items() if key != "content"} for record in records if isinstance(record, dict)]


def output_pack_group_is_reusable(root: Path, records: list[dict[str, Any]]) -> bool:
    for record in records:
        path = str(record.get("path") or "")
        if not path:
            return False
        if not (root / path).exists():
            return False
    return True


def output_pack_lifecycle_summary_input_signature(lifecycle_summary: dict[str, Any], *, active_protocol: str) -> str:
    payload = {
        "active_protocol": active_protocol,
        "lifecycle_summary": lifecycle_summary,
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_review_group_input_signature(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "review_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "citation_drift": str(page.get("citation_drift") or ""),
                "citation_snapshot_gap_count": str(page.get("citation_snapshot_gap_count", "") or ""),
                "revisit_after": str(page.get("revisit_after") or ""),
                "escalate_after": str(page.get("escalate_after") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in review_candidates
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_decision_memo_group_input_signature(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "reviewed_candidates": [
            {
                "path": str(page.get("path") or ""),
                "title": str(page.get("title") or ""),
                "status": str(page.get("status") or ""),
                "kind": str(page.get("kind") or ""),
                "protocol": str(page.get("protocol") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
                "confidence": str(page.get("confidence") or ""),
                "page_signature": workspace_file_signature(root, str(page.get("path") or "")),
            }
            for page in reviewed_candidates
        ],
        "recent_outputs": [
            {
                "path": str(artifact.get("path") or ""),
                "title": str(artifact.get("title") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or ""),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs[:5]
            if isinstance(artifact, dict)
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def output_pack_sop_group_input_signature(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
) -> str:
    payload = {
        "active_protocol": active_protocol,
        "execution_proposals": [
            {
                "action_id": str(proposal.get("action_id") or ""),
                "title": str(proposal.get("title") or ""),
                "risk": str(proposal.get("risk") or ""),
                "proposal_kind": str(proposal.get("proposal_kind") or ""),
                "protocol": str(proposal.get("protocol") or ""),
                "summary": str(proposal.get("summary") or ""),
                "proposal_path": str(proposal.get("proposal_path") or ""),
                "bundle_path": str(proposal.get("bundle_path") or ""),
                "target_paths": list(proposal.get("target_paths", []) or []),
                "page_patch_plan": list(proposal.get("page_patch_plan", []) or []),
                "suggested_edits": list(proposal.get("suggested_edits", []) or []),
            }
            for proposal in execution_proposals
        ],
        "ready_actions": [
            {
                "id": str(action.get("id") or ""),
                "title": str(action.get("title") or ""),
                "status": str(action.get("status") or ""),
                "priority": str(action.get("priority") or ""),
                "protocol": str(action.get("protocol") or ""),
                "execution_band": str(action.get("execution_band") or ""),
                "primary_path": str(action.get("primary_path") or ""),
                "secondary_path": str(action.get("secondary_path") or ""),
                "reason": str(action.get("reason") or ""),
                "next_step": str(action.get("next_step") or ""),
                "command_hint": str(action.get("command_hint") or ""),
                "active": bool(action.get("active")),
                "bundle_exists": execution_bundle_path(root, str(action.get("id") or "")).exists(),
                "low_risk_apply": action_supports_low_risk_apply(action),
            }
            for action in ready_actions
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_output_pack_review_packs(
    root: Path,
    review_candidates: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    review_packs: list[dict[str, Any]] = []
    for page in review_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        reasons: list[str] = []
        if page.get("pending_review") == "true":
            reasons.append("pending review")
        if page.get("overdue_review") == "true":
            reasons.append("overdue review")
        if page.get("escalation_candidate") == "true":
            reasons.append("escalation candidate")
        if page.get("citation_drift") == "true":
            reasons.append("citation drift")
        if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
            reasons.append("citation snapshot gap")
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = review_pack_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"review-pack-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "review-pack",
                "title": f"Review Pack · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# Review Pack · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Kind: `{kind}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Review reasons: `{', '.join(reasons) or 'manual review'}`",
            f"- Revisit / Escalate: `{page.get('revisit_after', '') or 'none'}` / `{page.get('escalate_after', '') or 'none'}`",
            "",
            f"## Current {section_name}",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。"),
            "",
            f"## {evidence_section} Snapshot",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据快照。"),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence."),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions."),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet."),
            "",
            "## Review Checklist",
            *[f"- {line}" for line in PROTOCOL_LIBRARY.get(protocol, {}).get("review", [])],
            "",
            "## Commands",
            f"- `PYTHONPATH=src python3 -m aiwiki.cli --root . review-page {page['path']} --status "
            f"{'approved' if kind == 'decision' else 'confirmed'} --note \"Review pack follow-up.\"`",
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [审阅队列](../../../wiki/indexes/review-queue.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
            ]
        )
        review_packs.append(
            {
                "title": f"Review Pack · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reasons": ", ".join(reasons) or "manual review",
            }
        )
    return review_packs


def build_output_pack_decision_memos(
    root: Path,
    reviewed_candidates: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> list[dict[str, Any]]:
    decision_memos: list[dict[str, Any]] = []
    for page in reviewed_candidates:
        frontmatter, content = load_workspace_markdown(root, page["path"])
        kind = str(frontmatter.get("kind") or page.get("kind") or "curated")
        memo_label = "Decision Memo" if kind == "decision" else "Judgment Memo"
        section_name = "Decision" if kind == "decision" else "Judgment"
        evidence_section = "Evidence" if kind == "decision" else "Signals"
        citations = [str(item) for item in frontmatter.get("citations", []) if isinstance(item, str) and item.strip()]
        destination = decision_memo_path(root, page["path"])
        protocol = str(frontmatter.get("protocol") or active_protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"decision-memo-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "decision-memo",
                "title": f"{memo_label} · {page['title']}",
                "protocol": protocol,
                "target_path": page["path"],
                "target_kind": kind,
                "source_files": [page["path"]],
                "citations": citations,
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# {memo_label} · {page['title']}",
            "",
            "## Overview",
            f"- Target page: `{page['path']}`",
            f"- Status: `{display_curated_status(page.get('status', 'unknown'))}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Reviewed at: `{page.get('reviewed_at', '') or 'unknown'}`",
            f"- Confidence: `{frontmatter.get('confidence') or page.get('confidence', '') or 'n/a'}`",
            "",
            "## Executive Summary",
            *compact_section_lines(content, section_name, fallback="- 当前还没有稳定结论。", limit=6),
            "",
            f"## {evidence_section}",
            *compact_section_lines(content, evidence_section, fallback="- 当前还没有整理过证据。", limit=6),
            "",
            "## Counter Evidence",
            *compact_section_lines(content, "Counter Evidence", fallback="- Pending counter evidence.", limit=5),
            "",
            "## Invalidation",
            *compact_section_lines(content, "Invalidation", fallback="- Pending invalidation conditions.", limit=5),
            "",
            "## Next Signals",
            *compact_section_lines(content, "Next Signals", fallback="- Pending next signals.", limit=5),
            "",
            "## Review History",
            *compact_section_lines(content, "Review History", fallback="- No review history yet.", limit=6),
            "",
            "## Citations",
        ]
        if not citations:
            lines.append("- 当前没有结构化 citations。")
        else:
            lines.extend(f"- `{citation}`" for citation in citations)
        if recent_outputs:
            lines.extend(["", "## Nearby Recent Outputs"])
            for artifact in recent_outputs[:5]:
                lines.append(
                    f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                    f" | format `{artifact['format'] or 'unknown'}`"
                    f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                )
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(page['path'], page['title'])}",
                "- [判断资产](../../../wiki/indexes/judgment-assets.md)",
                "- [认知历史](../../../wiki/indexes/cognitive-history.md)",
                "- [审阅中心](../../../wiki/indexes/review-center.md)",
            ]
        )
        decision_memos.append(
            {
                "title": f"{memo_label} · {page['title']}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "target_path": page["path"],
                "protocol": protocol,
                "reviewed_at": page.get("reviewed_at", "") or "",
            }
        )
    return decision_memos


def build_output_pack_sop_drafts(
    root: Path,
    ready_actions: list[dict[str, Any]],
    execution_proposals: list[dict[str, Any]],
    *,
    active_protocol: str,
    compiled_at: str,
) -> tuple[list[dict[str, Any]], int]:
    sop_drafts: list[dict[str, Any]] = []
    proposal_by_action = {
        str(proposal.get("action_id") or ""): proposal
        for proposal in execution_proposals
        if proposal.get("action_id")
    }
    proposal_count = 0
    for proposal in execution_proposals:
        action_id = str(proposal.get("action_id") or "").strip()
        if not action_id:
            continue
        destination = sop_draft_path(root, action_id)
        protocol = str(proposal.get("protocol") or active_protocol)
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "protocol": protocol,
                "action_id": action_id,
                "source_files": [str(proposal.get("proposal_path") or "")],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        patch_plan = proposal.get("page_patch_plan", [])
        bundle_path = str(proposal.get("bundle_path") or "")
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {proposal.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Risk: `{proposal.get('risk', 'medium')}`",
            f"- Proposal kind: `{proposal.get('proposal_kind', 'manual-repair')}`",
            f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
            f"- Targets: `{', '.join(proposal.get('target_paths', [])) or 'none'}`",
            f"- Bundle: `{bundle_path or 'none'}`",
            "",
            "## Strategy",
            f"- {proposal.get('summary', '检查目标页面并确认是否执行。')}",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.append(
                f"2. 如果 dry-run 结果符合预期，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。"
            )
        else:
            lines.append("2. 当前没有 bundle，先回到 execution proposal 页面确认执行边界。")
        lines.append(
            f"3. 如需回滚，执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}`。"
        )
        lines.extend(["", "## Page-Level Patch Plan"])
        if not patch_plan:
            lines.append("- 当前没有页级 patch step。")
        else:
            for patch in patch_plan:
                lines.append(
                    f"- `{patch.get('path', '')}`"
                    f" | role `{patch.get('role_label', patch.get('role', 'page'))}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
                lines.append(f"  - {patch.get('summary', '检查相关页面并补充修复说明。')}")
        lines.extend(["", "## Suggested Edits"])
        edits = proposal.get("suggested_edits", [])
        if not edits:
            lines.append("- 当前没有额外建议。")
        else:
            lines.extend(f"- {edit}" for edit in edits[:8])
        lines.extend(
            [
                "",
                "## Related Links",
                f"- {pack_workspace_link(str(proposal.get('proposal_path') or ''), 'Execution Proposal')}" if proposal.get("proposal_path") else "- Execution Proposal: none",
                f"- {pack_workspace_link(bundle_path, 'Execution Bundle')}" if bundle_path else "- Execution Bundle: none",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆修复计划](../../../wiki/indexes/machine-memory-repair-plan.md)",
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {proposal.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": protocol,
                "risk": str(proposal.get("risk") or "medium"),
            }
        )
        proposal_count += 1

    for action in ready_actions:
        action_id = str(action.get("id") or "").strip()
        if not action_id or action_id in proposal_by_action:
            continue
        destination = sop_draft_path(root, action_id)
        band = str(action.get("execution_band") or "review-first")
        action_protocol = str(action.get("protocol") or active_protocol)
        bundle_absolute = execution_bundle_path(root, action_id)
        bundle_relative = relative_path(root, bundle_absolute)
        bundle_path = bundle_relative if bundle_absolute.exists() else ""
        frontmatter_text = render_frontmatter(
            {
                "id": f"sop-draft-{destination.stem}",
                "kind": "output-pack",
                "pack_kind": "sop-draft",
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "protocol": action_protocol,
                "action_id": action_id,
                "source_files": [str(action.get("primary_path") or "")],
                "generated_by": "aiwiki-compile",
                "last_compiled_at": compiled_at,
            }
        )
        lines = [
            frontmatter_text,
            "",
            f"# SOP Draft · {action.get('title') or action_id}",
            "",
            "## Overview",
            f"- Action id: `{action_id}`",
            f"- Status: `{display_action_status(str(action.get('status') or 'proposed'))}`",
            f"- Priority: `{action.get('priority', 'medium')}`",
            f"- Protocol: `{action_protocol}` ({protocol_title(action_protocol)})",
            f"- Execution band: `{band}` ({execution_band_label(band)})",
            f"- Primary / Secondary: `{action.get('primary_path', '')}` / `{action.get('secondary_path', '') or 'none'}`",
            "",
            "## Step-by-Step",
            f"1. 先跑 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run`。",
        ]
        if bundle_path:
            lines.extend(
                [
                    f"2. 如果执行 band 仍允许，再执行 `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_path}`。",
                    f"3. 必要时用 `PYTHONPATH=src python3 -m aiwiki.cli --root . revert-action {action_id}` 回滚。",
                ]
            )
            bundle_link = f"- [Execution Bundle](../../../{bundle_path})"
        else:
            lines.extend(
                [
                    "2. 当前还没有稳定 bundle；先停在 dry-run，或回到 execution proposal 层生成 bundle。",
                    "3. 生成 bundle 后再执行真实 apply。",
                ]
            )
            bundle_link = "- Execution Bundle: none"
        lines.extend(
            [
                "",
                "## Action Notes",
                f"- Reason: {action.get('reason', 'n/a')}",
                f"- Next step: {action.get('next_step', 'n/a')}",
                f"- Command hint: `{action.get('command_hint', '') or 'none'}`",
                "",
                "## Related Links",
                "- [执行中心](../../../wiki/indexes/execution-center.md)",
                "- [执行审计](../../../wiki/indexes/execution-audit.md)",
                "- [机器记忆动作队列](../../../wiki/indexes/machine-memory-actions.md)",
                bundle_link,
            ]
        )
        sop_drafts.append(
            {
                "title": f"SOP Draft · {action.get('title') or action_id}",
                "path": relative_path(root, destination),
                "content": "\n".join(lines) + "\n",
                "action_id": action_id,
                "protocol": action_protocol,
                "risk": "low" if action_supports_low_risk_apply(action) else "medium",
            }
        )
    return sop_drafts, proposal_count


def build_output_packs(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    review_packs = build_output_pack_review_packs(
        root,
        review_candidates,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    decision_memos = build_output_pack_decision_memos(
        root,
        reviewed_candidates,
        recent_outputs,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    sop_drafts, proposal_count = build_output_pack_sop_drafts(
        root,
        ready_actions,
        execution_proposals,
        active_protocol=active_protocol,
        compiled_at=compiled_at,
    )
    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }


def build_output_packs_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    review_candidates = output_pack_review_candidates(decisions, judgments, active_protocol=active_protocol)
    reviewed_candidates = output_pack_reviewed_candidates(decisions, judgments)
    ready_actions, execution_proposals = output_pack_repair_plan_candidates(memory)
    previous_state = load_output_pack_build_state(root)
    previous_group_records = previous_state.get("group_records", {})
    signatures = {
        "lifecycle_summary": output_pack_lifecycle_summary_input_signature(
            lifecycle_summary,
            active_protocol=active_protocol,
        ),
        "review_packs": output_pack_review_group_input_signature(
            root,
            review_candidates,
            active_protocol=active_protocol,
        ),
        "decision_memos": output_pack_decision_memo_group_input_signature(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
        ),
        "sop_drafts": output_pack_sop_group_input_signature(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
        ),
    }
    dirty_groups: list[str] = []
    clean_groups: list[str] = []
    review_packs: list[dict[str, Any]]
    decision_memos: list[dict[str, Any]]
    sop_drafts: list[dict[str, Any]]

    lifecycle_reusable = (
        isinstance(previous_group_records.get("lifecycle_summary"), dict)
        and str(previous_group_records["lifecycle_summary"].get("input_signature") or "") == signatures["lifecycle_summary"]
    )
    if lifecycle_reusable:
        clean_groups.append("lifecycle_summary")
    else:
        dirty_groups.append("lifecycle_summary")

    previous_review_packs = previous_state.get("review_packs", [])
    review_reusable = (
        isinstance(previous_group_records.get("review_packs"), dict)
        and str(previous_group_records["review_packs"].get("input_signature") or "") == signatures["review_packs"]
        and output_pack_group_is_reusable(root, previous_review_packs)
    )
    if review_reusable:
        review_packs = [dict(record) for record in previous_review_packs]
        clean_groups.append("review_packs")
    else:
        review_packs = build_output_pack_review_packs(
            root,
            review_candidates,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("review_packs")

    previous_decision_memos = previous_state.get("decision_memos", [])
    memo_reusable = (
        isinstance(previous_group_records.get("decision_memos"), dict)
        and str(previous_group_records["decision_memos"].get("input_signature") or "") == signatures["decision_memos"]
        and output_pack_group_is_reusable(root, previous_decision_memos)
    )
    if memo_reusable:
        decision_memos = [dict(record) for record in previous_decision_memos]
        clean_groups.append("decision_memos")
    else:
        decision_memos = build_output_pack_decision_memos(
            root,
            reviewed_candidates,
            recent_outputs,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("decision_memos")

    previous_sop_drafts = previous_state.get("sop_drafts", [])
    sop_reusable = (
        isinstance(previous_group_records.get("sop_drafts"), dict)
        and str(previous_group_records["sop_drafts"].get("input_signature") or "") == signatures["sop_drafts"]
        and output_pack_group_is_reusable(root, previous_sop_drafts)
    )
    if sop_reusable:
        sop_drafts = [dict(record) for record in previous_sop_drafts]
        clean_groups.append("sop_drafts")
        proposal_count = int(previous_state.get("counts", {}).get("execution_proposal_sops", 0) or 0)
    else:
        sop_drafts, proposal_count = build_output_pack_sop_drafts(
            root,
            ready_actions,
            execution_proposals,
            active_protocol=active_protocol,
            compiled_at=compiled_at,
        )
        dirty_groups.append("sop_drafts")

    counts = {
        "review_packs": len(review_packs),
        "decision_memos": len(decision_memos),
        "sop_drafts": len(sop_drafts),
        "execution_proposal_sops": proposal_count,
    }
    output_packs = {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "review_packs": review_packs,
        "decision_memos": decision_memos,
        "sop_drafts": sop_drafts,
        "lifecycle_summary": lifecycle_summary,
        "counts": counts,
    }
    state_document = {
        "version": 1,
        "generated_at": compiled_at,
        "active_protocol": active_protocol,
        "group_records": {
            group: {"input_signature": signature}
            for group, signature in signatures.items()
        },
        "lifecycle_summary": lifecycle_summary,
        "review_packs": output_pack_state_records(review_packs),
        "decision_memos": output_pack_state_records(decision_memos),
        "sop_drafts": output_pack_state_records(sop_drafts),
        "counts": counts,
    }
    return {
        "output_packs": output_packs,
        "state_document": state_document,
        "dirty_groups": dirty_groups,
        "clean_groups": clean_groups,
    }


def render_output_packs_index(output_packs: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    review_packs = output_packs.get("review_packs", [])
    decision_memos = output_packs.get("decision_memos", [])
    sop_drafts = output_packs.get("sop_drafts", [])
    lifecycle_summary = output_packs.get("lifecycle_summary", {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    counts = output_packs.get("counts", {})
    lines = [
        "# 输出 Pack 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Review packs：`{counts.get('review_packs', len(review_packs))}`",
        f"- Decision memos：`{counts.get('decision_memos', len(decision_memos))}`",
        f"- SOP drafts：`{counts.get('sop_drafts', len(sop_drafts))}`",
        f"- lifecycle concept backlog：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## Pack 目录",
        "- `output/packs/review/`：待审 / 漂移 / aging 页面",
        "- `output/packs/decision-memos/`：已审 decision / judgment",
        "- `output/packs/sop-drafts/`：ready action / execution proposal",
        "",
        "## Lifecycle Governance Summary",
        f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
        f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
        f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
        "",
        "## Lifecycle Concept Backlog",
    ]
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
        "## Review Packs",
        ]
    )
    if not review_packs:
        lines.append("- 当前没有 review packs。")
    else:
        for pack in review_packs[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reasons `{pack.get('reasons', 'manual review')}`"
            )
    lines.extend(["", "## Decision Memos"])
    if not decision_memos:
        lines.append("- 当前没有 decision memos。")
    else:
        for pack in decision_memos[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | target `{pack.get('target_path', '')}`"
                f" | reviewed `{pack.get('reviewed_at', '') or 'unknown'}`"
            )
    lines.extend(["", "## SOP Drafts"])
    if not sop_drafts:
        lines.append("- 当前没有 SOP drafts。")
    else:
        for pack in sop_drafts[:16]:
            lines.append(
                f"- {workspace_link(pack['path'], pack['title'])}"
                f" | action `{pack.get('action_id', '')}`"
                f" | risk `{pack.get('risk', 'medium')}`"
            )
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [判断资产](./judgment-assets.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def domain_pilots_index_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "domain-pilots.md"


def pilot_scorecards_dir(root: Path) -> Path:
    return root / "output" / "pilots"


def pilot_scorecard_path(root: Path, protocol: str) -> Path:
    return pilot_scorecards_dir(root) / f"{slugify(protocol)}.md"


def pilot_stage(metrics: dict[str, int]) -> tuple[str, str]:
    curated = metrics["decisions"] + metrics["judgments"]
    reviewed = metrics["reviewed"]
    outputs = metrics["outputs"]
    receipts = metrics["receipts"]
    packs = metrics["review_packs"] + metrics["decision_memos"] + metrics["sop_drafts"]
    if curated == 0 and outputs == 0:
        return ("seed", "尚未形成该协议的稳定判断资产。")
    if curated < 2 or reviewed == 0:
        return ("warming-up", "已经开始沉淀，但 reviewed judgment / decision 还偏少。")
    if reviewed < 3 or outputs < 3:
        return ("building", "协议已经起量，但还没进入明显复利。")
    if packs < 2 or receipts == 0:
        return ("active", "判断和 pack 已形成，但执行闭环还不够密。")
    return ("compounding", "已经出现判断、pack、执行和复审的复利迹象。")


def domain_pilot_state_scorecard(scorecard: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in scorecard.items() if key != "content"}


def domain_pilot_scorecard_is_reusable(root: Path, scorecard: dict[str, Any]) -> bool:
    path = str(scorecard.get("path") or "")
    return bool(path) and (root / path).exists()


def domain_pilot_protocol_inputs(
    protocol: str,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    memory: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any],
    material_routing: dict[str, Any],
    active_protocol: str,
) -> dict[str, Any]:
    lifecycle_summary = protocol_related_concept_lifecycle_summary(
        knowledge_lifecycle,
        material_routing,
        protocol=protocol,
    )
    receipt_counts = {
        str(row.get("protocol") or DEFAULT_PROTOCOL): int(row.get("count") or 0)
        for row in execution_audit.get("protocols", [])
        if isinstance(row, dict)
    }
    repair_plan = memory.get("health", {}).get("repair_plan", {})
    execution_proposals = [
        {
            "action_id": str(proposal.get("action_id") or ""),
            "title": str(proposal.get("title") or ""),
            "protocol": str(proposal.get("protocol") or DEFAULT_PROTOCOL),
            "proposal_kind": str(proposal.get("proposal_kind") or ""),
            "summary": str(proposal.get("summary") or ""),
        }
        for proposal in repair_plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == protocol
    ]
    return {
        "protocol": protocol,
        "active_protocol": active_protocol,
        "decisions": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in decisions
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "judgments": [
            {
                "title": str(page.get("title") or ""),
                "path": str(page.get("path") or ""),
                "status": str(page.get("status") or ""),
                "pending_review": str(page.get("pending_review") or ""),
                "overdue_review": str(page.get("overdue_review") or ""),
                "escalation_candidate": str(page.get("escalation_candidate") or ""),
                "reviewed_at": str(page.get("reviewed_at") or ""),
            }
            for page in judgments
            if str(page.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "all_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in all_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "recent_outputs": [
            {
                "title": str(artifact.get("title") or ""),
                "path": str(artifact.get("path") or ""),
                "format": str(artifact.get("format") or ""),
                "protocol": str(artifact.get("protocol") or DEFAULT_PROTOCOL),
                "created_at": str(artifact.get("created_at") or ""),
            }
            for artifact in recent_outputs
            if str(artifact.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ][:5],
        "review_packs": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("review_packs", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "decision_memos": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
            }
            for pack in output_packs.get("decision_memos", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "sop_drafts": [
            {
                "title": str(pack.get("title") or ""),
                "path": str(pack.get("path") or ""),
                "risk": str(pack.get("risk") or "medium"),
            }
            for pack in output_packs.get("sop_drafts", [])
            if str(pack.get("protocol") or DEFAULT_PROTOCOL) == protocol
        ],
        "receipt_count": receipt_counts.get(protocol, 0),
        "execution_proposals": execution_proposals,
        "lifecycle_summary": lifecycle_summary,
    }


def domain_pilot_protocol_input_signature(protocol_inputs: dict[str, Any]) -> str:
    return sha256_bytes(json.dumps(protocol_inputs, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_domain_pilot_scorecard(
    root: Path,
    protocol_inputs: dict[str, Any],
    *,
    compiled_at: str,
) -> dict[str, Any]:
    protocol = str(protocol_inputs.get("protocol") or DEFAULT_PROTOCOL)
    active_protocol = str(protocol_inputs.get("active_protocol") or DEFAULT_PROTOCOL)
    protocol_decisions = list(protocol_inputs.get("decisions", []) or [])
    protocol_judgments = list(protocol_inputs.get("judgments", []) or [])
    protocol_outputs = list(protocol_inputs.get("all_outputs", []) or [])
    protocol_recent_outputs = list(protocol_inputs.get("recent_outputs", []) or [])
    lifecycle_summary = dict(protocol_inputs.get("lifecycle_summary", {}) or {})
    lifecycle_counts = lifecycle_summary.get("counts", {})
    metrics = {
        "decisions": len(protocol_decisions),
        "judgments": len(protocol_judgments),
        "reviewed": sum(
            1
            for page in [*protocol_decisions, *protocol_judgments]
            if str(page.get("reviewed_at") or "") and str(page.get("pending_review") or "") != "true"
        ),
        "pending": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("pending_review") == "true"),
        "overdue": sum(1 for page in [*protocol_decisions, *protocol_judgments] if page.get("overdue_review") == "true"),
        "escalation": sum(
            1 for page in [*protocol_decisions, *protocol_judgments] if page.get("escalation_candidate") == "true"
        ),
        "outputs": len(protocol_outputs),
        "review_packs": len(list(protocol_inputs.get("review_packs", []) or [])),
        "decision_memos": len(list(protocol_inputs.get("decision_memos", []) or [])),
        "sop_drafts": len(list(protocol_inputs.get("sop_drafts", []) or [])),
        "receipts": int(protocol_inputs.get("receipt_count", 0) or 0),
        "execution_proposals": len(list(protocol_inputs.get("execution_proposals", []) or [])),
        "lifecycle_concept_backlog": int(lifecycle_counts.get("concept_backlog", 0) or 0),
        "lifecycle_retired_concepts": int(lifecycle_counts.get("retired_concepts", 0) or 0),
        "lifecycle_dominant_concepts": int(lifecycle_counts.get("dominant_related_concepts", 0) or 0),
        "lifecycle_mixed_concepts": int(lifecycle_counts.get("mixed_related_concepts", 0) or 0),
        "lifecycle_bridge_concepts": int(lifecycle_counts.get("ambiguity_bridge_concepts", 0) or 0),
    }
    stage, stage_summary = pilot_stage(metrics)
    gaps: list[str] = []
    if lifecycle_counts.get("concept_backlog", 0):
        gaps.append(
            f"有 `{lifecycle_counts.get('concept_backlog', 0)}` 个 protocol-related lifecycle concept backlog 尚未收敛。"
        )
    ambiguity_count = int(lifecycle_counts.get("mixed_related_concepts", 0)) + int(
        lifecycle_counts.get("ambiguity_bridge_concepts", 0)
    )
    if ambiguity_count:
        gaps.append(f"有 `{ambiguity_count}` 个 protocol-related concept 仍处于 mixed / bridge ambiguity，需要人工校准归属。")
    if metrics["decisions"] + metrics["judgments"] == 0:
        gaps.append("还没有该协议的 `decision / judgment` 资产。")
    if metrics["reviewed"] == 0:
        gaps.append("还没有 reviewed judgment / decision。")
    if metrics["outputs"] < 2:
        gaps.append("可回流 outputs 还不够密。")
    if metrics["pending"] > metrics["reviewed"]:
        gaps.append("待审页面多于已审资产。")
    if metrics["review_packs"] == 0 and metrics["pending"] > 0:
        gaps.append("需要先把 pending review 炼成 review packs。")
    if metrics["decision_memos"] == 0 and metrics["reviewed"] > 0:
        gaps.append("已审判断还没有形成 decision memos。")
    if metrics["sop_drafts"] == 0 and metrics["execution_proposals"] > 0:
        gaps.append("执行提案还没有形成 SOP drafts。")
    if metrics["receipts"] == 0 and metrics["sop_drafts"] > 0:
        gaps.append("还没有 execution receipt，可先从 dry-run / low-risk apply 开始。")
    next_moves = [
        PROTOCOL_LIBRARY[protocol]["focus"][0],
        PROTOCOL_LIBRARY[protocol]["review"][0],
        PROTOCOL_LIBRARY[protocol]["nightly"][0],
    ]
    if gaps:
        next_moves.insert(0, gaps[0])
    destination = pilot_scorecard_path(root, protocol)
    frontmatter_text = render_frontmatter(
        {
            "id": f"pilot-scorecard-{slugify(protocol)}",
            "kind": "pilot-scorecard",
            "title": f"{protocol_title(protocol)} Pilot Scorecard",
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter_text,
        "",
        f"# {protocol_title(protocol)} Pilot Scorecard",
        "",
        "## Overview",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Stage: `{stage}`",
        f"- Summary: {stage_summary}",
        f"- 当前协议是否 active：`{'yes' if protocol == active_protocol else 'no'}`",
        "",
        "## Density Snapshot",
        f"- Decisions / Judgments: `{metrics['decisions']}` / `{metrics['judgments']}`",
        f"- Reviewed / Pending: `{metrics['reviewed']}` / `{metrics['pending']}`",
        f"- Overdue / Escalation: `{metrics['overdue']}` / `{metrics['escalation']}`",
        f"- Outputs: `{metrics['outputs']}`",
        f"- Review packs / Decision memos / SOP drafts: `{metrics['review_packs']}` / `{metrics['decision_memos']}` / `{metrics['sop_drafts']}`",
        f"- Execution proposals / Receipts: `{metrics['execution_proposals']}` / `{metrics['receipts']}`",
        f"- Protocol-related lifecycle backlog / retired concepts: `{metrics['lifecycle_concept_backlog']}` / `{metrics['lifecycle_retired_concepts']}`",
        "",
        "## Protocol Focus",
        *[f"- {line}" for line in PROTOCOL_LIBRARY[protocol]["focus"]],
        "",
        "## Gaps",
    ]
    if not gaps:
        lines.append("- 当前没有明显结构性缺口。")
    else:
        lines.extend(f"- {gap}" for gap in gaps)
    lines.extend(
        [
            "",
            "## Lifecycle Governance",
            "- 以下 concept lifecycle 摘要优先统计 supporting sources 的 `material-routing top_protocols` 首位命中；若来源在当前协议仍是 `warm/hot evidence`，或属于 `cross_protocol_bridge` 且当前协议仍位于 top2，也会保守纳入。",
            f"- Inference mode: `{lifecycle_summary.get('inference_mode', 'unknown')}`",
            f"- Ambiguity mode: `{lifecycle_summary.get('ambiguity_mode', 'unknown')}`",
            f"- Related direct / secondary / bridge concepts: `{lifecycle_counts.get('direct_related_concepts', 0)}` / `{lifecycle_counts.get('secondary_related_concepts', 0)}` / `{lifecycle_counts.get('bridge_related_concepts', 0)}`",
            f"- Related dominant / mixed / bridge concepts: `{lifecycle_counts.get('dominant_related_concepts', 0)}` / `{lifecycle_counts.get('mixed_related_concepts', 0)}` / `{lifecycle_counts.get('ambiguity_bridge_concepts', 0)}`",
            f"- Related review concepts: `{lifecycle_counts.get('review_concepts', 0)}`",
            f"- Related revisit concepts: `{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- Related retired concepts: `{lifecycle_counts.get('retired_concepts', 0)}`",
            f"- Related active concepts: `{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Protocol Ambiguity Watchlist",
        ]
    )
    if not lifecycle_summary.get("ambiguity_watchlist"):
        lines.append("- 当前没有 mixed / bridge ambiguity concept。")
    else:
        lines.append("- 以下概念仍需要人工判断是当前协议主归属、混合归属，还是桥接归属。")
        for entry in lifecycle_summary.get("ambiguity_watchlist", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Lifecycle Concept Backlog"])
    if not lifecycle_summary.get("concept_backlog"):
        lines.append("- 当前没有 protocol-related lifecycle concept backlog。")
    else:
        for entry in lifecycle_summary.get("concept_backlog", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Protocol-Related Retired Concepts"])
    if not lifecycle_summary.get("retired_concepts"):
        lines.append("- 当前没有 protocol-related retired concept。")
    else:
        for entry in lifecycle_summary.get("retired_concepts", [])[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Next Moves"])
    lines.extend(f"- {item}" for item in next_moves[:5])
    lines.extend(["", "## Recent Outputs"])
    if not protocol_recent_outputs:
        lines.append("- 当前没有最近 output。")
    else:
        for artifact in protocol_recent_outputs:
            lines.append(
                f"- {pack_workspace_link(artifact['path'], artifact['title'])}"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )
    lines.extend(
        [
            "",
            "## Related Links",
            f"- {pack_workspace_link(f'schema/protocols/{protocol}/index.md', f'{protocol_title(protocol)} 协议规则')}",
            "- [协议总览](../../../wiki/indexes/protocols.md)",
            "- [输出 Pack 总览](../../../wiki/indexes/output-packs.md)",
            "- [审阅中心](../../../wiki/indexes/review-center.md)",
            "- [执行中心](../../../wiki/indexes/execution-center.md)",
        ]
    )
    return {
        "protocol": protocol,
        "title": f"{protocol_title(protocol)} Pilot Scorecard",
        "path": relative_path(root, destination),
        "content": "\n".join(lines) + "\n",
        "stage": stage,
        "summary": stage_summary,
        "metrics": metrics,
        "lifecycle_summary": lifecycle_summary,
    }


def build_domain_pilots(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    material_routing = material_routing or load_material_routing_state(root)
    scorecards = [
        build_domain_pilot_scorecard(
            root,
            domain_pilot_protocol_inputs(
                protocol,
                decisions,
                judgments,
                recent_outputs,
                all_outputs,
                output_packs,
                execution_audit,
                memory,
                knowledge_lifecycle=knowledge_lifecycle,
                material_routing=material_routing,
                active_protocol=active_protocol,
            ),
            compiled_at=compiled_at,
        )
        for protocol in sorted(PROTOCOL_LIBRARY)
    ]
    return {
        "compiled_at": compiled_at,
        "active_protocol": active_protocol,
        "scorecards": scorecards,
    }


def build_domain_pilots_incremental(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    all_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    execution_audit: dict[str, Any],
    compiled_at: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
    material_routing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_protocol = protocol_state["active_protocol"]
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    material_routing = material_routing or load_material_routing_state(root)
    previous_state = load_domain_pilot_build_state(root)
    previous_protocol_records = previous_state.get("protocol_records", {})
    previous_scorecards_by_protocol = {
        str(scorecard.get("protocol") or ""): scorecard
        for scorecard in previous_state.get("scorecards", [])
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "")
    }
    scorecards: list[dict[str, Any]] = []
    dirty_protocols: list[str] = []
    clean_protocols: list[str] = []
    protocol_records: dict[str, dict[str, str]] = {}
    for protocol in sorted(PROTOCOL_LIBRARY):
        protocol_inputs = domain_pilot_protocol_inputs(
            protocol,
            decisions,
            judgments,
            recent_outputs,
            all_outputs,
            output_packs,
            execution_audit,
            memory,
            knowledge_lifecycle=knowledge_lifecycle,
            material_routing=material_routing,
            active_protocol=active_protocol,
        )
        signature = domain_pilot_protocol_input_signature(protocol_inputs)
        protocol_records[protocol] = {"input_signature": signature}
        previous_record = previous_protocol_records.get(protocol, {})
        previous_scorecard = previous_scorecards_by_protocol.get(protocol, {})
        reusable = (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == signature
            and domain_pilot_scorecard_is_reusable(root, previous_scorecard)
        )
        if reusable:
            reused_scorecard = dict(previous_scorecard)
            scorecard_path = str(reused_scorecard.get("path") or "")
            if scorecard_path:
                reused_scorecard["content"] = (root / scorecard_path).read_text(encoding="utf-8", errors="replace")
            scorecards.append(reused_scorecard)
            clean_protocols.append(protocol)
        else:
            scorecards.append(
                build_domain_pilot_scorecard(
                    root,
                    protocol_inputs,
                    compiled_at=compiled_at,
                )
            )
            dirty_protocols.append(protocol)
    removed_protocols = sorted(set(previous_scorecards_by_protocol) - set(PROTOCOL_LIBRARY))
    return {
        "domain_pilots": {
            "compiled_at": compiled_at,
            "active_protocol": active_protocol,
            "scorecards": scorecards,
        },
        "state_document": {
            "version": 1,
            "generated_at": compiled_at,
            "active_protocol": active_protocol,
            "protocol_records": protocol_records,
            "scorecards": [domain_pilot_state_scorecard(scorecard) for scorecard in scorecards],
        },
        "dirty_protocols": dirty_protocols,
        "clean_protocols": clean_protocols,
        "removed_protocols": removed_protocols,
    }


def render_domain_pilots_index(domain_pilots: dict[str, Any], compiled_at: str, active_protocol: str) -> str:
    lines = [
        "# 领域 Pilot 总览",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 协议总数：`{len(domain_pilots.get('scorecards', []))}`",
        "",
        "## 协议 Scorecards",
    ]
    for scorecard in domain_pilots.get("scorecards", []):
        metrics = scorecard.get("metrics", {})
        lines.append(
            f"- {workspace_link(scorecard['path'], scorecard['title'])}"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | curated `{int(metrics.get('decisions', 0)) + int(metrics.get('judgments', 0))}`"
            f" | outputs `{metrics.get('outputs', 0)}`"
            f" | receipts `{metrics.get('receipts', 0)}`"
            f" | lifecycle backlog `{metrics.get('lifecycle_concept_backlog', 0)}`"
            f" | retired `{metrics.get('lifecycle_retired_concepts', 0)}`"
            f" | dominant/mixed/bridge `{metrics.get('lifecycle_dominant_concepts', 0)}/{metrics.get('lifecycle_mixed_concepts', 0)}/{metrics.get('lifecycle_bridge_concepts', 0)}`"
        )
        lines.append(f"  - {scorecard.get('summary', '')}")
    lines.extend(
        [
            "",
            "## 相关入口",
            "- [协议总览](./protocols.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_agent_pack(
    role: str,
    title: str,
    mission: str,
    protocol: str,
    compiled_at: str,
    focus: list[str],
    actions: list[str],
    links: list[str],
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": slugify(role),
            "kind": "agent-pack",
            "agent_role": role,
            "title": title,
            "protocol": protocol,
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {title}",
        "",
        f"- Agent role: `{role}`",
        f"- Protocol: `{protocol}` ({protocol_title(protocol)})",
        f"- Compiled at: `{compiled_at}`",
        "",
        "## Mission",
        f"- {mission}",
        "",
        "## Current Focus",
    ]
    if not focus:
        lines.append("- 当前没有额外焦点。")
    else:
        lines.extend(f"- {item}" for item in focus)
    lines.extend(["", "## Suggested Actions"])
    if not actions:
        lines.append("- 当前没有新的建议动作。")
    else:
        lines.extend(f"- {item}" for item in actions)
    lines.extend(["", "## Related Links"])
    if not links:
        lines.append("- 当前没有相关链接。")
    else:
        lines.extend(f"- {item}" for item in links)
    return "\n".join(lines) + "\n"


def render_agent_workbench(
    packs: list[dict[str, str]],
    compiled_at: str,
    active_protocol: str,
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    lifecycle_counts = lifecycle_summary.get("counts", {})
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    dispatch_hints: list[str] = []
    if concept_backlog:
        dispatch_hints.append(
            f"先调 [Review Agent](../../output/agents/review-agent.md)，处理 `{len(concept_backlog)}` 个 lifecycle concept backlog。"
        )
    if lifecycle_counts.get("review_concepts", 0) or lifecycle_counts.get("revisit_concepts", 0):
        dispatch_hints.append(
            f"需要概念整理时，再调 [Concept Agent](../../output/agents/concept-agent.md)，消化 `{lifecycle_counts.get('review_concepts', 0) + lifecycle_counts.get('revisit_concepts', 0)}` 个 review / revisit concept。"
        )
    if retired_concepts:
        dispatch_hints.append(
            f"确认 `{min(len(retired_concepts), 3)}` 个 retired concept 是否要恢复进入工作面，优先走 [Review Agent](../../output/agents/review-agent.md)。"
        )
    if not dispatch_hints:
        dispatch_hints.append("当前 lifecycle governance 较干净，按输出、执行或 ingest 压力决定要调度哪个角色。")
    lines = [
        "# Agent Workbench",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- Agent packs：`{len(packs)}`",
        f"- lifecycle concept backlog / retired：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        "",
        "## 角色总览",
    ]
    if not packs:
        lines.append("- 当前还没有 agent packs。")
    else:
        for pack in packs:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | role `{pack['role']}`"
                f" | {pack['mission']}"
            )
    lines.extend(
        [
            "",
            "## Lifecycle Governance Summary",
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "## Lifecycle Dispatch Hints",
        ]
    )
    lines.extend(f"- {hint}" for hint in dispatch_hints)
    lines.extend(["", "## Lifecycle Concept Backlog"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:10]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(
        [
            "",
            "## 如何使用",
            "1. Human Owner 先在炉心面板里决定今天要调度哪个角色。",
            "2. 进入对应 agent pack，看当前焦点、建议动作和相关链接。",
            "3. 角色之间共享同一个 `raw / wiki / machine memory / decision / judgment`，不维护私有真相。",
            "",
            "## 相关入口",
            "- [炉心面板](./furnace-center.md)",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [图谱视图](./graph-view.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_queue(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    concept_backlog = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"review", "revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# 审阅队列",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 待审决策：`{len(queue['pending_decisions'])}`",
        f"- 待审判断：`{len(queue['pending_judgments'])}`",
        f"- 最近已审项目：`{len(queue['recently_reviewed'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- lifecycle concept backlog：`{len(concept_backlog)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 协议审阅焦点",
        *[f"- {line}" for line in PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])],
        "",
        "## 待审决策",
    ]
    if not queue["pending_decisions"]:
        lines.append("- 当前没有待审决策。")
    else:
        for page in queue["pending_decisions"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 待审判断"])
    if not queue["pending_judgments"]:
        lines.append("- 当前没有待审判断。")
    else:
        for page in queue["pending_judgments"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期的决策或判断页面。")
    else:
        for page in aging["overdue"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 需要升级处理"])
    if not aging["escalated"]:
        lines.append("- 当前没有需要升级处理的页面。")
    else:
        for page in aging["escalated"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期概念待审"])
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle state 标记为 `review` / `revisit` 的 concept。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 最近已审"])
    if not queue["recently_reviewed"]:
        lines.append("- 还没有已审阅的决策或判断页面。")
    else:
        for page in queue["recently_reviewed"][:12]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


def render_aging_report(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    pages = decisions + judgments
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    retired_concepts = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            kinds={"concept"},
            states={"retired"},
        ),
        active_protocol=active_protocol,
    )
    lines = [
        "# Aging 报告",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 已排期复审：`{len(aging['scheduled'])}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- retired concepts：`{len(retired_concepts)}`",
        "",
        "## 需要升级处理",
    ]
    if not aging["escalated"]:
        lines.append("- 当前没有升级处理项。")
    else:
        for page in aging["escalated"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已到期待复审"])
    if not aging["overdue"]:
        lines.append("- 当前没有已到期页面。")
    else:
        for page in aging["overdue"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 已排期复审"])
    if not aging["scheduled"]:
        lines.append("- 当前没有已排期的复审页面。")
    else:
        for page in aging["scheduled"][:20]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 已退役概念"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:20]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 建议动作"])
    if aging["escalated"]:
        lines.append("- 优先处理升级项，补证据、更新状态或明确下一次复审窗口。")
    if aging["overdue"] and not aging["escalated"]:
        lines.append("- 先清理已到期页面，避免 review queue 长期堆积。")
    if lifecycle_revisit_entries:
        lines.append("- 把 lifecycle `revisit` 项和时间窗口型 overdue 项一起看，避免只盯 review date 而忽略证据失效。")
    if not aging["overdue"] and not aging["escalated"]:
        lines.append("- 当前 aging 状态健康，继续通过 nightly 跟踪。")
    stale_reviewed = [
        page
        for page in pages
        if page.get("pending_review") != "true" and page.get("revisit_after")
    ]
    if stale_reviewed:
        lines.append("- 已审页面如仍保留复审窗口，必要时在下一次 review 中收紧或清空。")
    return "\n".join(lines) + "\n"


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_candidates = concept_quality.get("rewrite_candidates", [])
    conflict_signals = concept_quality.get("conflict_signals", [])
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]

    def render_page_item(page: dict[str, str]) -> str:
        path = html.escape(f"../../{page['path']}")
        status = html.escape(display_curated_status(page.get("status", "") or "unknown"))
        revisit = html.escape(page.get("revisit_after", "") or "none")
        return (
            f'<li><a href="{path}">{html.escape(page["title"])}</a>'
            f" | status {status}"
            f" | revisit {revisit}</li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        primary = html.escape(str(action.get("primary_path") or ""))
        status = html.escape(display_action_status(str(action.get("status") or "proposed")))
        priority = html.escape(str(action.get("priority") or "medium"))
        detail = ""
        if action.get("secondary_path"):
            detail = f" | secondary <code>{html.escape(str(action['secondary_path']))}</code>"
        command = ""
        if action.get("command_hint"):
            command = f" | command <code>{html.escape(str(action['command_hint']))}</code>"
        return (
            f"<li>{html.escape(str(action.get('title') or 'unnamed action'))}"
            f" | priority {priority}"
            f" | status {status}"
            f" | primary <code>{primary}</code>{detail}{command}</li>"
        )

    def render_concept_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        issues = html.escape(", ".join(item.get("issues", [])) or "none")
        return (
            f'<li><a href="../../wiki/concepts/{slug}.md">{title}</a>'
            f" | issues {issues}"
            f" | sources {int(item.get('source_count', 0))}</li>"
        )

    def render_rewrite_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        status = html.escape(display_rewrite_proposal_status(str(item.get("status") or "proposed")))
        return (
            f'<li><a href="../../wiki/rewrite-proposals/{slug}.md">{title}</a>'
            f" | status {status}"
            f" | apply_ready {html.escape(str(bool(item.get('apply_ready'))).lower())}</li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{override}{invalidation}{active_corpora}</li>"

    pending_list = "".join(render_page_item(page) for page in pending_items[:12]) or "<li>当前没有待审项目。</li>"
    overdue_list = "".join(render_page_item(page) for page in aging.get("overdue", [])[:10]) or "<li>当前没有已到期待复审页面。</li>"
    escalated_list = "".join(render_page_item(page) for page in aging.get("escalated", [])[:10]) or "<li>当前没有需要升级处理的页面。</li>"
    lifecycle_backlog_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    ready_action_list = "".join(render_action_item(action) for action in ready_actions[:10]) or "<li>当前没有 ready repair action。</li>"
    apply_ready_action_list = (
        "".join(render_action_item(action) for action in apply_ready_actions[:8])
        or "<li>当前没有可直接 semi-auto apply 的低风险动作。</li>"
    )
    rewrite_list = "".join(render_concept_item(item) for item in rewrite_candidates[:10]) or "<li>当前没有高优先级弱概念页。</li>"
    conflict_list = "".join(render_concept_item(item) for item in conflict_signals[:10]) or "<li>当前没有显式概念冲突信号。</li>"
    rewrite_proposal_list = "".join(render_rewrite_item(item) for item in rewrite_proposals[:10]) or "<li>当前没有 rewrite proposal。</li>"

    summary_cards = [
        ("待审项目", str(len(pending_items))),
        ("已到期复审", str(len(aging.get("overdue", [])))),
        ("升级项", str(len(aging.get("escalated", [])))),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("ready actions", str(plan.get("counts", {}).get("ready", 0))),
        ("重写候选", str(concept_quality.get("counts", {}).get("rewrite_candidates", 0))),
        ("冲突信号", str(concept_quality.get("counts", {}).get("conflict_signals", 0))),
        ("rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可应用 rewrite", str(len(apply_ready_rewrites))),
        ("可应用动作", str(len(apply_ready_actions))),
    ]

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Review Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #fffaf0; --ink: #1f2937; --muted: #6b7280; --panel: #ffffff; --line: #e5e7eb; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #fffaf0 0%, #f3f4f6 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1120px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: rgba(255,255,255,0.94); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .lists { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin: 18px 0 24px; }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #b45309; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #92400e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    code { background: #f3f4f6; padding: 1px 5px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Review Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议焦点：<code>{html.escape(active_protocol)}</code>。这是炼丹炉的人用审阅 cockpit：把 review、aging、repair 和 concept rewrite 收在一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="lists">',
            '    <div class="panel"><h2>待审项目</h2><ul>',
            f"{pending_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已到期 / 需升级</h2><ul>',
            f"{overdue_list}",
            f"{escalated_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>生命周期概念待审</h2><ul>',
            f"{lifecycle_backlog_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已退役概念</h2><ul>',
            f"{retired_concept_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Ready Repair Actions</h2><ul>',
            f"{ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Safe Apply Actions</h2><ul>',
            f"{apply_ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念重写优先级</h2><ul>',
            f"{rewrite_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念冲突信号</h2><ul>',
            f"{conflict_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Rewrite Proposals</h2><ul>',
            f"{rewrite_proposal_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>相关入口</h2><ul>',
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '      <li><a href="../../wiki/indexes/review-center.md">Review Center Dashboard</a></li>',
            '      <li><a href="../../wiki/indexes/review-queue.md">审阅队列</a></li>',
            '      <li><a href="../../wiki/indexes/aging-report.md">Aging 报告</a></li>',
            '      <li><a href="../../wiki/indexes/cognitive-history.md">认知历史</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">机器记忆动作队列</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">机器记忆修复计划</a></li>',
            '      <li><a href="../../wiki/indexes/judgment-assets.md">判断资产</a></li>',
            '      <li><a href="../../wiki/indexes/execution-center.md">执行中心</a></li>',
            '      <li><a href="../../wiki/indexes/concept-quality.md">概念质量</a></li>',
            '      <li><a href="../../wiki/indexes/rewrite-proposals.md">Rewrite Proposals</a></li>',
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def protocol_scorecard(domain_pilots: dict[str, Any], protocol: str) -> dict[str, Any]:
    for scorecard in domain_pilots.get("scorecards", []):
        if isinstance(scorecard, dict) and str(scorecard.get("protocol") or "") == protocol:
            return scorecard
    return {}


def protocol_output_pack_rows(output_packs: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for pack in output_packs.get("review_packs", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Review Pack",
                "title": str(pack.get("title") or "Review Pack"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reasons") or "manual review"),
            }
        )
    for pack in output_packs.get("decision_memos", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "Decision Memo",
                "title": str(pack.get("title") or "Decision Memo"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("reviewed_at") or "reviewed"),
            }
        )
    for pack in output_packs.get("sop_drafts", []):
        if str(pack.get("protocol") or DEFAULT_PROTOCOL) != protocol:
            continue
        rows.append(
            {
                "kind": "SOP Draft",
                "title": str(pack.get("title") or "SOP Draft"),
                "path": str(pack.get("path") or ""),
                "meta": str(pack.get("risk") or "medium"),
            }
        )
    rows.sort(key=lambda item: (item["kind"], item["title"].lower()))
    return rows[:limit]


def protocol_execution_receipts(execution_audit: dict[str, Any], protocol: str, *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    protocol_buckets = execution_audit.get("recent_by_protocol", {})
    for bucket_name, label in (("recent_apply", "apply"), ("recent_revert", "revert")):
        bucket_rows = []
        if isinstance(protocol_buckets, dict):
            scoped = protocol_buckets.get(bucket_name, {})
            if isinstance(scoped, dict):
                protocol_rows = scoped.get(protocol, [])
                if isinstance(protocol_rows, list):
                    bucket_rows = protocol_rows
        if not bucket_rows:
            bucket_rows = execution_audit.get(bucket_name, [])
        for record in bucket_rows:
            if str(record.get("protocol") or DEFAULT_PROTOCOL) != protocol:
                continue
            rows.append(
                {
                    "kind": label,
                    "title": str(record.get("title") or record.get("action_id") or "receipt"),
                    "action_id": str(record.get("action_id") or ""),
                    "receipt_path": str(record.get("receipt_path") or ""),
                    "applied_at": str(record.get("applied_at") or ""),
                }
            )
    rows.sort(key=lambda item: (item["applied_at"], item["title"].lower()), reverse=True)
    return rows[:limit]


def furnace_quick_commands(
    active_protocol: str,
    apply_ready_actions: list[dict[str, Any]],
    apply_ready_rewrites: list[dict[str, Any]],
) -> list[str]:
    commands = [
        "PYTHONPATH=src python3 -m aiwiki.cli --root . protocol-status",
        f"PYTHONPATH=src python3 -m aiwiki.cli --root . ask \"对当前主题做协议化总结\" --format report --protocol {active_protocol}",
        "PYTHONPATH=src python3 -m aiwiki.cli --root . nightly",
    ]
    if apply_ready_actions:
        first_action = apply_ready_actions[0]
        action_id = str(first_action.get("id") or "")
        bundle_hint = str(first_action.get("bundle_path") or "")
        if action_id:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --dry-run"
            )
            if bundle_hint:
                commands.append(
                    f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-action {action_id} --bundle {bundle_hint}"
                )
    if apply_ready_rewrites:
        first_rewrite = apply_ready_rewrites[0]
        slug = str(first_rewrite.get("slug") or "")
        if slug:
            commands.append(
                f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
            )
    return commands[:6]


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lifecycle_counts = lifecycle_summary.get("counts", {})
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    citation_drift_count = sum(1 for page in decisions + judgments if page.get("citation_drift") == "true")
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:6]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)
    next_steps: list[str] = []
    if concept_backlog:
        next_steps.append(f"先处理 `{min(len(concept_backlog), 5)}` 个 lifecycle concept backlog。")
    if apply_ready_actions:
        next_steps.append(f"先处理 `{len(apply_ready_actions)}` 个可直接 `apply-action` 的低风险动作。")
    if apply_ready_rewrites:
        next_steps.append(f"应用 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal。")
    if aging.get("escalated"):
        next_steps.append(f"优先复查 `{len(aging.get('escalated', []))}` 个升级项。")
    if pending_items:
        next_steps.append(f"继续审 `{len(pending_items)}` 个 decision / judgment 页面。")
    if retired_concepts and not concept_backlog:
        next_steps.append(f"检查 `{min(len(retired_concepts), 3)}` 个 retired concept 是否需要重新激活。")
    if not next_steps:
        next_steps.append("当前没有紧急执行项，优先看最新输出和图谱漂移。")

    lines = [
        "# 炉心面板",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 来源节点：`{len(memory.get('source_nodes', []))}`",
        f"- 概念节点：`{len(memory.get('concept_nodes', []))}`",
        f"- 待审项目：`{len(pending_items)}`",
        f"- 已到期 / 升级：`{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
        f"- 生命周期概念待审 / 已退役：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- 证据漂移：`{citation_drift_count}`",
        f"- Ready repair actions：`{len(ready_actions)}`",
        f"- 可直接 apply 的动作：`{len(apply_ready_actions)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 可直接 apply 的 rewrite：`{len(apply_ready_rewrites)}`",
        f"- 页级 patch step：`{page_patch_steps}`",
        f"- 当前协议 stage：`{scorecard.get('stage', 'seed') if scorecard else 'unknown'}`",
        f"- 当前协议 outputs / receipts：`{scorecard_metrics.get('outputs', 0)}` / `{scorecard_metrics.get('receipts', 0)}`",
        f"- 当前协议 review packs / memos / SOP：`{scorecard_metrics.get('review_packs', 0)}` / `{scorecard_metrics.get('decision_memos', 0)}` / `{scorecard_metrics.get('sop_drafts', 0)}`",
        f"- 最近输出：`{len(recent_outputs)}`",
        "- 本地控制面板：`output/control/furnace-center.html`",
        "",
        "## 今天先做什么",
    ]
    for index, step in enumerate(next_steps, start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "## 即刻可执行",
        ]
    )
    if apply_ready_actions:
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['title']}` | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if apply_ready_rewrites:
        lines.append("")
        lines.append("### Apply-Ready Rewrites")
        for proposal in apply_ready_rewrites[:8]:
            lines.append(
                f"- `{proposal['target_path']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Page-Level Patch Plan")
        for proposal in execution_proposals[:4]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(f"- `{proposal['action_id']}` | patch step `{len(patch_plan)}`")
            for patch in patch_plan[:3]:
                lines.append(
                    f"  - `{patch.get('path', '')}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
    if not any((apply_ready_actions, apply_ready_rewrites, execution_proposals)):
        lines.append("- 当前没有即刻可执行项。")

    lines.extend(
        [
            "",
            "## 最近输出",
        ]
    )
    if not recent_outputs:
        lines.append("- 当前还没有 recent outputs。")
    else:
        for artifact in recent_outputs:
            lines.append(
                f"- [{artifact['title']}](../../{artifact['path']})"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )

    lines.extend(["", "## 当前协议 Pilot"])
    if not scorecard:
        lines.append("- 当前协议还没有 pilot scorecard。")
    else:
        lines.append(
            f"- [{scorecard['title']}](../../{scorecard['path']})"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | {scorecard.get('summary', '')}"
        )
        gaps = compact_section_lines(scorecard.get("content", ""), "Gaps", fallback="- 当前没有明显结构性缺口。", limit=4)
        lines.append("")
        lines.append("### 当前缺口")
        lines.extend(gaps)
        next_moves_lines = compact_section_lines(scorecard.get("content", ""), "Next Moves", fallback="- 当前没有额外 next moves。", limit=4)
        lines.append("")
        lines.append("### 下一动作")
        lines.extend(next_moves_lines)

    lines.extend(["", "## Lifecycle 治理摘要"])
    lines.extend(
        [
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            "",
            "### Lifecycle Concept Backlog",
        ]
    )
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))

    lines.extend(["", "## 最新输出 Packs"])
    if not pack_rows:
        lines.append("- 当前协议还没有 review pack / decision memo / SOP draft。")
    else:
        for pack in pack_rows:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | kind `{pack['kind']}`"
                f" | meta `{pack['meta'] or 'n/a'}`"
            )

    lines.extend(["", "## 最近执行回执"])
    if not receipt_rows:
        lines.append("- 当前协议还没有 execution receipt。")
    else:
        for receipt in receipt_rows:
            receipt_path = receipt["receipt_path"] or ".aiwiki/state/execution-receipts.jsonl"
            lines.append(
                f"- `{receipt['title']}`"
                f" | kind `{receipt['kind']}`"
                f" | action `{receipt['action_id']}`"
                f" | receipt `{receipt_path}`"
                f" | at `{receipt['applied_at'] or 'unknown'}`"
            )

    lines.extend(
        [
            "",
            "## 最近已审 / 已沉淀",
        ]
    )
    if recent_reviewed:
        for page in recent_reviewed:
            lines.append(
                f"- [{page['title']}](../../{page['path']})"
                f" | status `{display_curated_status(page.get('status', 'unknown'))}`"
                f" | reviewed `{page.get('reviewed_at', '') or 'unknown'}`"
            )
    else:
        lines.append("- 当前还没有最近已审项目。")

    lines.extend(["", "## 快速命令"])
    for command in quick_commands:
        lines.append(f"- `{command}`")

    lines.extend(
        [
            "",
            "## 快速跳转",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [Agent Workbench](./agent-workbench.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [领域 Pilot 总览](./domain-pilots.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [图谱视图](./graph-view.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [协议总览](./protocols.md)",
            "- [输出面板](./Outputs.md)",
            "- [本地审阅面板](../../output/review/review-center.html)",
            "- [本地图谱视图](../../output/graph/machine-memory.html)",
            "- [本地炉心面板](../../output/control/furnace-center.html)",
            "- [本地执行面板](../../output/control/execution-center.html)",
            "- [本地执行审计面板](../../output/control/execution-audit.html)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_furnace_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:8]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)

    def render_page_item(page: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(page["path"])}">{html.escape(page["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(display_curated_status(page.get('status', 'unknown')))}</span></li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        command = html.escape(str(action.get("command_hint") or ""))
        return (
            f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
            f" <span class=\"item-meta\">{html.escape(str(action.get('priority') or 'medium'))} / {html.escape(display_action_status(str(action.get('status') or 'proposed')))}</span>"
            f"<div><code>{html.escape(str(action.get('primary_path') or ''))}</code></div>"
            f"{f'<div><code>{command}</code></div>' if command else ''}</li>"
        )

    def render_rewrite_item(proposal: dict[str, Any]) -> str:
        slug = html.escape(str(proposal.get("slug") or ""))
        target = html.escape(str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"))
        command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
        return (
            f"<li><strong><a href=\"../../wiki/rewrite-proposals/{slug}.md\">{html.escape(str(proposal.get('title') or slug))}</a></strong>"
            f" <span class=\"item-meta\">{html.escape(display_rewrite_proposal_status(str(proposal.get('status') or 'proposed')))}</span>"
            f"<div><code>{target}</code></div><div><code>{html.escape(command)}</code></div></li>"
        )

    def render_output_item(artifact: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(artifact["path"])}">{html.escape(artifact["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(artifact['format'] or 'unknown')} / {html.escape(artifact['protocol'] or DEFAULT_PROTOCOL)} / {html.escape(artifact['created_at'] or 'unknown')}</span></li>"
        )

    def render_proposal_item(proposal: dict[str, Any]) -> str:
        patch_count = len(proposal.get("page_patch_plan", []))
        return (
            f"<li><strong>{html.escape(str(proposal.get('action_id') or 'proposal'))}</strong>"
            f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))}</span>"
            f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
            f"<div><code>{html.escape(', '.join(proposal.get('target_paths', [])) or 'none')}</code></div>"
            f"<div class=\"item-meta\">patch steps {patch_count}</div></li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{override}{invalidation}{active_corpora}</li>"

    summary_cards = [
        ("来源", str(len(memory.get("source_nodes", [])))),
        ("概念", str(len(memory.get("concept_nodes", [])))),
        ("待审", str(len(pending_items))),
        ("到期/升级", f"{len(aging.get('overdue', []))}/{len(aging.get('escalated', []))}"),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("Ready 动作", str(plan.get("counts", {}).get("ready", 0))),
        ("可 apply 动作", str(len(apply_ready_actions))),
        ("Rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可 apply rewrite", str(len(apply_ready_rewrites))),
        ("Patch Steps", str(page_patch_steps)),
        ("最近输出", str(len(recent_outputs))),
        ("Pilot Stage", str(scorecard.get("stage", "unknown") if scorecard else "unknown")),
        ("Review Packs", str(scorecard_metrics.get("review_packs", 0))),
        ("Decision Memos", str(scorecard_metrics.get("decision_memos", 0))),
        ("SOP Drafts", str(scorecard_metrics.get("sop_drafts", 0))),
        ("Receipts", str(scorecard_metrics.get("receipts", 0))),
    ]

    protocol_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])[:3]
    nightly_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly", [])[:3]
    pending_markup = "".join(render_page_item(page) for page in pending_items[:8]) or "<li>当前没有待审项目。</li>"
    aging_markup = "".join(render_page_item(page) for page in (aging.get("escalated", []) + aging.get("overdue", []))[:8]) or "<li>当前没有已到期或升级项目。</li>"
    apply_action_markup = "".join(render_action_item(action) for action in apply_ready_actions[:8]) or "<li>当前没有可直接 apply 的低风险动作。</li>"
    rewrite_markup = "".join(render_rewrite_item(proposal) for proposal in apply_ready_rewrites[:8]) or "<li>当前没有可直接 apply 的 rewrite proposal。</li>"
    proposal_markup = "".join(render_proposal_item(proposal) for proposal in execution_proposals[:8]) or "<li>当前没有 execution proposal。</li>"
    output_markup = "".join(render_output_item(artifact) for artifact in recent_outputs[:10]) or "<li>当前还没有 recent outputs。</li>"
    reviewed_markup = "".join(render_page_item(page) for page in recent_reviewed) or "<li>当前还没有最近已审项目。</li>"
    focus_markup = "".join(f"<li>{html.escape(item)}</li>" for item in protocol_focus + nightly_focus) or "<li>当前协议没有额外焦点。</li>"
    lifecycle_backlog_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    pack_markup = "".join(
        f"<li><strong><a href=\"../../{html.escape(row['path'])}\">{html.escape(row['title'])}</a></strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['meta'] or 'n/a')}</span></li>"
        for row in pack_rows[:10]
    ) or "<li>当前协议还没有 review pack / decision memo / SOP draft。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(row['title'])}</strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['action_id'])}</span>"
        f"<div><code>{html.escape(row['receipt_path'] or '.aiwiki/state/execution-receipts.jsonl')}</code></div>"
        f"<div class=\"item-meta\">{html.escape(row['applied_at'] or 'unknown')}</div></li>"
        for row in receipt_rows[:10]
    ) or "<li>当前协议还没有 execution receipt。</li>"
    quick_command_markup = "".join(
        f"<li><code>{html.escape(command)}</code></li>" for command in quick_commands
    ) or "<li>当前没有额外快速命令。</li>"
    scorecard_markup = (
        "\n".join(
            [
                f'<p><strong><a href="../../{html.escape(str(scorecard.get("path") or ""))}">{html.escape(str(scorecard.get("title") or "Pilot Scorecard"))}</a></strong></p>',
                f'<p class="item-meta">stage {html.escape(str(scorecard.get("stage") or "seed"))} · {html.escape(str(scorecard.get("summary") or ""))}</p>',
                '<ul>'
                + "".join(
                    f"<li>{html.escape(line.lstrip('- ').strip())}</li>"
                    for line in compact_section_lines(
                        str(scorecard.get("content") or ""),
                        "Next Moves",
                        fallback="- 当前没有额外 next moves。",
                        limit=4,
                    )
                )
                + "</ul>",
            ]
        )
        if scorecard
        else "<p>当前协议还没有 pilot scorecard。</p>"
    )

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Furnace Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: radial-gradient(circle at top right, #dbeafe 0%, #f8fafc 40%, #fefce8 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1180px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; }",
            "    .hero { margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "    .quick-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }",
            "    .quick-links a { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; background: #ffffff; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel hero">',
            "    <h1>Furnace Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code> ({html.escape(protocol_title(active_protocol))})。这是炼丹炉的统一入口：把 review、graph、execution 和 recent outputs 收到一个地方。</p>",
            '    <div class="quick-links">',
            '      <a href="../../wiki/indexes/furnace-center.md">Markdown 面板</a>',
            '      <a href="../../wiki/indexes/review-center.md">审阅中心</a>',
            '      <a href="../../wiki/indexes/execution-center.md">执行中心</a>',
            '      <a href="../../wiki/indexes/execution-audit.md">执行审计</a>',
            '      <a href="../../wiki/indexes/agent-workbench.md">Agent Workbench</a>',
            '      <a href="../../wiki/indexes/cognitive-history.md">认知历史</a>',
            '      <a href="../../wiki/indexes/output-packs.md">输出 Packs</a>',
            '      <a href="../../wiki/indexes/domain-pilots.md">领域 Pilots</a>',
            '      <a href="../../wiki/indexes/judgment-assets.md">判断资产</a>',
            '      <a href="../../wiki/indexes/graph-view.md">图谱视图</a>',
            '      <a href="../../wiki/indexes/repair-backlog.md">修复待办</a>',
            '      <a href="../../wiki/indexes/protocols.md">协议总览</a>',
            '      <a href="../../output/review/review-center.html">审阅 HTML</a>',
            '      <a href="../../output/graph/machine-memory.html">图谱 HTML</a>',
            '      <a href="../../output/control/execution-center.html">执行 HTML</a>',
            '      <a href="../../output/control/execution-audit.html">审计 HTML</a>',
            "    </div>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>待审 / 已到期</h2><ul>{pending_markup}{aging_markup}</ul></div>',
            '    <div class="panel"><h2>生命周期治理</h2>'
            f'<p class="item-meta">review {html.escape(str(lifecycle_summary.get("counts", {}).get("review_concepts", 0)))}'
            f' · revisit {html.escape(str(lifecycle_summary.get("counts", {}).get("revisit_concepts", 0)))}'
            f' · active {html.escape(str(lifecycle_summary.get("counts", {}).get("active_concepts", 0)))}</p>'
            f"<ul>{lifecycle_backlog_markup}</ul></div>",
            f'    <div class="panel"><h2>已退役概念</h2><ul>{retired_concept_markup}</ul></div>',
            f'    <div class="panel"><h2>Safe Apply</h2><ul>{apply_action_markup}</ul></div>',
            f'    <div class="panel"><h2>Apply-Ready Rewrites</h2><ul>{rewrite_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>最近输出</h2><ul>{output_markup}</ul></div>',
            f'    <div class="panel"><h2>协议焦点</h2><ul>{focus_markup}</ul></div>',
            f'    <div class="panel"><h2>最近已审 / 已沉淀</h2><ul>{reviewed_markup}</ul></div>',
            f'    <div class="panel"><h2>当前协议 Pilot</h2>{scorecard_markup}</div>',
            f'    <div class="panel"><h2>最新输出 Packs</h2><ul>{pack_markup}</ul></div>',
            f'    <div class="panel"><h2>最近执行回执</h2><ul>{receipt_markup}</ul></div>',
            f'    <div class="panel"><h2>快速命令</h2><ul>{quick_command_markup}</ul></div>',
            '    <div class="panel"><h2>系统状态</h2><ul>'
            f'<li>graph components <code>{html.escape(str(health.get("component_count", 0)))}</code></li>'
            f'<li>bridge concepts <code>{html.escape(str(len(health.get("bridge_concept_slugs", []))))}</code></li>'
            f'<li>conflict signals <code>{html.escape(str(concept_quality.get("counts", {}).get("conflict_signals", 0)))}</code></li>'
            f'<li>gap signals <code>{html.escape(str(concept_quality.get("counts", {}).get("gap_signals", 0)))}</code></li>'
            f'<li>rewrite candidates <code>{html.escape(str(concept_quality.get("counts", {}).get("rewrite_candidates", 0)))}</code></li>'
            f'<li>ready batches <code>{html.escape(str(plan.get("counts", {}).get("batches", 0)))}</code></li>'
            "</ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
    *,
    compile_state: dict[str, Any] | None = None,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    compile_state = compile_state or default_compile_state()
    phase_summary = [
        phase
        for phase in compile_state.get("phase_summary", [])
        if isinstance(phase, dict) and str(phase.get("name") or "")
    ]
    dirty_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_source_ids", [])
        if str(entry_id)
    ]
    clean_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_concept_source_ids", [])
        if str(entry_id)
    ]
    clean_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_concept_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_concept_slugs", [])
        if str(slug)
    ]
    clean_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_concept_slugs", [])
        if str(slug)
    ]
    dirty_machine_memory_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_machine_memory_source_ids", [])
        if str(entry_id)
    ]
    clean_machine_memory_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_machine_memory_source_ids", [])
        if str(entry_id)
    ]
    dirty_machine_memory_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_machine_memory_concept_slugs", [])
        if str(slug)
    ]
    clean_machine_memory_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_machine_memory_concept_slugs", [])
        if str(slug)
    ]
    machine_memory_core_reused = bool(compile_state.get("machine_memory_core_reused", False))
    dirty_ranking_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_ranking_source_ids", [])
        if str(entry_id)
    ]
    clean_ranking_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_ranking_source_ids", [])
        if str(entry_id)
    ]
    dirty_ranking_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_ranking_concept_slugs", [])
        if str(slug)
    ]
    clean_ranking_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_ranking_concept_slugs", [])
        if str(slug)
    ]
    dirty_output_pack_groups = [
        str(group)
        for group in compile_state.get("dirty_output_pack_groups", [])
        if str(group)
    ]
    clean_output_pack_groups = [
        str(group)
        for group in compile_state.get("clean_output_pack_groups", [])
        if str(group)
    ]
    dirty_domain_pilot_protocols = [
        str(protocol)
        for protocol in compile_state.get("dirty_domain_pilot_protocols", [])
        if str(protocol)
    ]
    clean_domain_pilot_protocols = [
        str(protocol)
        for protocol in compile_state.get("clean_domain_pilot_protocols", [])
        if str(protocol)
    ]
    dirty_index_artifacts = [
        str(path)
        for path in compile_state.get("dirty_index_artifacts", [])
        if str(path)
    ]
    clean_index_artifacts = [
        str(path)
        for path in compile_state.get("clean_index_artifacts", [])
        if str(path)
    ]
    dirty_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("dirty_maintenance_artifacts", [])
        if str(path)
    ]
    clean_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("clean_maintenance_artifacts", [])
        if str(path)
    ]
    entry_by_id = {
        str(entry.get("id") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    concept_by_slug = {
        str(record.get("slug") or ""): record
        for record in concepts
        if isinstance(record, dict) and str(record.get("slug") or "")
    }
    detail_labels = {
        "manifest_entries": "entries",
        "changed_entries": "changed",
        "added_entries": "added",
        "updated_entries": "updated",
        "removed_entries": "removed",
        "source_pages": "sources",
        "dirty_sources": "dirty",
        "clean_sources": "clean",
        "updated_pages": "updated_pages",
        "skipped_pages": "skipped_pages",
        "concept_sources": "concept_sources",
        "dirty_concept_sources": "dirty_concept_sources",
        "clean_concept_sources": "clean_concept_sources",
        "concept_pages": "concepts",
        "dirty_concepts": "dirty_concepts",
        "clean_concepts": "clean_concepts",
        "machine_memory_sources": "machine_memory_sources",
        "dirty_machine_memory_sources": "dirty_machine_memory_sources",
        "clean_machine_memory_sources": "clean_machine_memory_sources",
        "machine_memory_concepts": "machine_memory_concepts",
        "dirty_machine_memory_concepts": "dirty_machine_memory_concepts",
        "clean_machine_memory_concepts": "clean_machine_memory_concepts",
        "reused_core": "reused_core",
        "ranking_sources": "ranking_sources",
        "dirty_ranking_sources": "dirty_ranking_sources",
        "clean_ranking_sources": "clean_ranking_sources",
        "ranking_concepts": "ranking_concepts",
        "dirty_ranking_concepts": "dirty_ranking_concepts",
        "clean_ranking_concepts": "clean_ranking_concepts",
        "pack_groups": "pack_groups",
        "dirty_pack_groups": "dirty_pack_groups",
        "clean_pack_groups": "clean_pack_groups",
        "review_packs": "review_packs",
        "decision_memos": "decision_memos",
        "sop_drafts": "sop_drafts",
        "pilot_protocols": "pilot_protocols",
        "dirty_protocols": "dirty_protocols",
        "clean_protocols": "clean_protocols",
        "tracked_artifacts": "tracked_artifacts",
        "dirty_artifacts": "dirty_artifacts",
        "clean_artifacts": "clean_artifacts",
        "updated_artifacts": "updated_artifacts",
        "skipped_artifacts": "skipped_artifacts",
        "removed_generated_pages": "removed_generated_pages",
        "material_state_entries": "material_state_entries",
        "archive_candidates": "archive_candidates",
        "active_corpora": "active_corpora",
        "knowledge_lifecycle_entries": "knowledge_lifecycle_entries",
    }
    lines = [
        "# 编译状态",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "- Compile state：`.aiwiki/state/compile-state.json`",
        "- Concept build state：`.aiwiki/state/concept-build-state.json`",
        "- Machine memory build state：`.aiwiki/state/machine-memory-build-state.json`",
        "- Ranking build state：`.aiwiki/state/ranking-build-state.json`",
        "- Output pack build state：`.aiwiki/state/output-pack-build-state.json`",
        "- Domain pilot build state：`.aiwiki/state/domain-pilot-build-state.json`",
        f"- Dirty source：`{len(dirty_source_ids)}`",
        f"- Clean source：`{len(clean_source_ids)}`",
        f"- Dirty concept source：`{len(dirty_concept_source_ids)}`",
        f"- Clean concept source：`{len(clean_concept_source_ids)}`",
        f"- Dirty concept：`{len(dirty_concept_slugs)}`",
        f"- Clean concept：`{len(clean_concept_slugs)}`",
        f"- Dirty machine-memory source：`{len(dirty_machine_memory_source_ids)}`",
        f"- Clean machine-memory source：`{len(clean_machine_memory_source_ids)}`",
        f"- Dirty machine-memory concept：`{len(dirty_machine_memory_concept_slugs)}`",
        f"- Clean machine-memory concept：`{len(clean_machine_memory_concept_slugs)}`",
        f"- Machine-memory core reused：`{machine_memory_core_reused}`",
        f"- Dirty ranking source：`{len(dirty_ranking_source_ids)}`",
        f"- Clean ranking source：`{len(clean_ranking_source_ids)}`",
        f"- Dirty ranking concept：`{len(dirty_ranking_concept_slugs)}`",
        f"- Clean ranking concept：`{len(clean_ranking_concept_slugs)}`",
        f"- Dirty output pack group：`{len(dirty_output_pack_groups)}`",
        f"- Clean output pack group：`{len(clean_output_pack_groups)}`",
        f"- Dirty domain pilot protocol：`{len(dirty_domain_pilot_protocols)}`",
        f"- Clean domain pilot protocol：`{len(clean_domain_pilot_protocols)}`",
        f"- Dirty index artifact：`{len(dirty_index_artifacts)}`",
        f"- Clean index artifact：`{len(clean_index_artifacts)}`",
        f"- Dirty maintenance artifact：`{len(dirty_maintenance_artifacts)}`",
        f"- Clean maintenance artifact：`{len(clean_maintenance_artifacts)}`",
        "- 总索引位于 `index.md`。",
        "- 运行时规则位于 `schema/`。",
        "- 协议规则位于 `schema/protocols/`。",
        "- 协议总览位于 `protocols.md`。",
        "- 炉心面板位于 `furnace-center.md`。",
        "- 执行中心位于 `execution-center.md`。",
        "- 输出 Pack 总览位于 `output-packs.md`。",
        "- 领域 Pilot 总览位于 `domain-pilots.md`。",
        "- 操作日志位于 `log.md`。",
        "- Agent Workbench 位于 `agent-workbench.md`。",
        "- 决策索引位于 `decisions.md`。",
        "- 判断索引位于 `judgments.md`。",
        "- 判断资产盘点位于 `judgment-assets.md`。",
        "- 认知历史位于 `cognitive-history.md`。",
        "- 审阅队列位于 `review-queue.md`。",
        "- 审阅中心位于 `review-center.md`。",
        "- aging 报告位于 `aging-report.md`。",
        "- 机器记忆摘要位于 `machine-memory.md`。",
        "- 图谱视图位于 `graph-view.md`。",
        "- 机器记忆拓扑位于 `machine-memory-topology.md`。",
        "- 机器记忆动作队列位于 `machine-memory-actions.md`。",
        "- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。",
        "- Rewrite 提案队列位于 `rewrite-proposals.md`。",
        "- 图谱健康页位于 `graph-health.md`。",
        "- 漂移报告位于 `drift-report.md`。",
        "- 修复待办位于 `repair-backlog.md`。",
        "- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。",
        "- lint 结果输出在 `output/lint/`。",
    ]
    lines.extend(["", "## Compile Phases"])
    if not phase_summary:
        lines.append("- 当前还没有 compile phase summary。")
    else:
        for phase in phase_summary:
            details = phase.get("details", {})
            detail_chunks = []
            if isinstance(details, dict):
                for key, value in details.items():
                    if key not in detail_labels:
                        continue
                    detail_chunks.append(f"{detail_labels[key]}={value}")
            label = str(phase.get("label") or phase.get("name") or "")
            mode = str(phase.get("mode") or "full")
            status = str(phase.get("status") or "completed")
            detail_suffix = f" | {', '.join(detail_chunks)}" if detail_chunks else ""
            lines.append(f"- `{phase['name']}` `{label}` [{mode}/{status}]{detail_suffix}")
    lines.extend(["", "## Dirty Sources"])
    if not dirty_source_ids:
        lines.append("- 当前没有 dirty source page。")
    else:
        for entry_id in dirty_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_source_ids) > 8:
            lines.append(f"- 其余 dirty source：`{len(dirty_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concept Sources"])
    if not dirty_concept_source_ids:
        lines.append("- 当前没有 dirty concept source。")
    else:
        for entry_id in dirty_concept_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_concept_source_ids) > 8:
            lines.append(f"- 其余 dirty concept source：`{len(dirty_concept_source_ids) - 8}`")
    lines.extend(["", "## Dirty Machine Memory Sources"])
    if not dirty_machine_memory_source_ids:
        lines.append("- 当前没有 dirty machine-memory source input。")
    else:
        for entry_id in dirty_machine_memory_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_machine_memory_source_ids) > 8:
            lines.append(f"- 其余 dirty machine-memory source：`{len(dirty_machine_memory_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concepts"])
    if not dirty_concept_slugs:
        lines.append("- 当前没有 dirty concept page。")
    else:
        for slug in dirty_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_concept_slugs) > 8:
            lines.append(f"- 其余 dirty concept：`{len(dirty_concept_slugs) - 8}`")
    lines.extend(["", "## Dirty Machine Memory Concepts"])
    if not dirty_machine_memory_concept_slugs:
        lines.append("- 当前没有 dirty machine-memory concept input。")
    else:
        for slug in dirty_machine_memory_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_machine_memory_concept_slugs) > 8:
            lines.append(
                f"- 其余 dirty machine-memory concept：`{len(dirty_machine_memory_concept_slugs) - 8}`"
            )
    lines.extend(["", "## Dirty Ranking Sources"])
    if not dirty_ranking_source_ids:
        lines.append("- 当前没有 dirty ranking source record。")
    else:
        for entry_id in dirty_ranking_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_ranking_source_ids) > 8:
            lines.append(f"- 其余 dirty ranking source：`{len(dirty_ranking_source_ids) - 8}`")
    lines.extend(["", "## Clean Ranking Sources"])
    if not clean_ranking_source_ids:
        lines.append("- 当前没有 clean ranking source record。")
    else:
        for entry_id in clean_ranking_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(clean_ranking_source_ids) > 8:
            lines.append(f"- 其余 clean ranking source：`{len(clean_ranking_source_ids) - 8}`")
    lines.extend(["", "## Dirty Ranking Concepts"])
    if not dirty_ranking_concept_slugs:
        lines.append("- 当前没有 dirty ranking concept record。")
    else:
        for slug in dirty_ranking_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_ranking_concept_slugs) > 8:
            lines.append(f"- 其余 dirty ranking concept：`{len(dirty_ranking_concept_slugs) - 8}`")
    lines.extend(["", "## Clean Ranking Concepts"])
    if not clean_ranking_concept_slugs:
        lines.append("- 当前没有 clean ranking concept record。")
    else:
        for slug in clean_ranking_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(clean_ranking_concept_slugs) > 8:
            lines.append(f"- 其余 clean ranking concept：`{len(clean_ranking_concept_slugs) - 8}`")
    lines.extend(["", "## Dirty Output Pack Groups"])
    if not dirty_output_pack_groups:
        lines.append("- 当前没有 dirty output pack group。")
    else:
        for group in dirty_output_pack_groups:
            lines.append(f"- `{group}`")
    lines.extend(["", "## Clean Output Pack Groups"])
    if not clean_output_pack_groups:
        lines.append("- 当前没有 clean output pack group。")
    else:
        for group in clean_output_pack_groups:
            lines.append(f"- `{group}`")
    lines.extend(["", "## Dirty Domain Pilot Protocols"])
    if not dirty_domain_pilot_protocols:
        lines.append("- 当前没有 dirty domain pilot protocol。")
    else:
        for protocol in dirty_domain_pilot_protocols:
            lines.append(f"- `{protocol}`")
    lines.extend(["", "## Clean Domain Pilot Protocols"])
    if not clean_domain_pilot_protocols:
        lines.append("- 当前没有 clean domain pilot protocol。")
    else:
        for protocol in clean_domain_pilot_protocols:
            lines.append(f"- `{protocol}`")
    lines.extend(["", "## Dirty Index Artifacts"])
    if not dirty_index_artifacts:
        lines.append("- 当前没有 dirty index artifact。")
    else:
        for relative in dirty_index_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_index_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_index_artifacts) - 12}`")
    lines.extend(["", "## Dirty Maintenance Artifacts"])
    if not dirty_maintenance_artifacts:
        lines.append("- 当前没有 dirty maintenance artifact。")
    else:
        for relative in dirty_maintenance_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_maintenance_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_maintenance_artifacts) - 12}`")
    return "\n".join(lines) + "\n"


def render_master_index(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    lines = [
        "# 知识库总索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级处理：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "",
        "## 核心页面",
        "- [来源索引](./sources.md)",
        "- [概念索引](./concepts.md)",
        "- [概念质量](./concept-quality.md)",
        "- [决策索引](./decisions.md)",
        "- [判断索引](./judgments.md)",
        "- [判断资产](./judgment-assets.md)",
        "- [Agent Workbench](./agent-workbench.md)",
        "- [认知历史](./cognitive-history.md)",
        "- [协议总览](./protocols.md)",
        "- [炉心面板](./furnace-center.md)",
        "- [执行中心](./execution-center.md)",
        "- [输出 Pack 总览](./output-packs.md)",
        "- [领域 Pilot 总览](./domain-pilots.md)",
        "- [审阅队列](./review-queue.md)",
        "- [审阅中心](./review-center.md)",
        "- [Aging 报告](./aging-report.md)",
        "- [编译状态](./compile-status.md)",
        "- [机器记忆](./machine-memory.md)",
        "- [图谱视图](./graph-view.md)",
        "- [机器记忆拓扑](./machine-memory-topology.md)",
        "- [机器记忆动作队列](./machine-memory-actions.md)",
        "- [机器记忆修复计划](./machine-memory-repair-plan.md)",
        "- [Rewrite Proposals](./rewrite-proposals.md)",
        "- [图谱健康](./graph-health.md)",
        "- [漂移报告](./drift-report.md)",
        "- [修复待办](./repair-backlog.md)",
        "- [操作日志](./log.md)",
        "- [运行时规则](../../schema/index.md)",
        "- [协议规则](../../schema/protocols/index.md)",
        "",
        "## 最近来源",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in sorted(entries, key=lambda item: item["imported_at"], reverse=True)[:8]:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md)")
    lines.extend(["", "## 重点概念"])
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts[:10]:
            lines.append(f"- [{concept['title']}](../concepts/{concept['slug']}.md)")
    lines.extend(["", "## 待审项目"])
    if not queue["pending_decisions"] and not queue["pending_judgments"]:
        lines.append("- 当前没有等待审阅的决策或判断页面。")
    else:
        for page in (queue["pending_decisions"] + queue["pending_judgments"])[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近决策"])
    if not decisions:
        lines.append("- 还没有回流的决策页面。")
    else:
        for page in decisions[:8]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 最近判断"])
    if not judgments:
        lines.append("- 还没有回流的判断页面。")
    else:
        for page in judgments[:8]:
            lines.append(render_curated_page_summary(page))
    return "\n".join(lines) + "\n"


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
            for field in ("sha256", "title", "kind", "source_type", "original_path")
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
    return summary.startswith("- This concept currently appears in `")


def concept_quality_tokens(label: str) -> set[str]:
    return {token for token in tokenize(label) if token not in STOP_WORDS}


def load_source_page_context(root: Path, relative: str) -> dict[str, str]:
    path = root / relative
    if not path.exists():
        return {"path": relative, "title": relative.rsplit("/", 1)[-1], "summary": "", "status": "missing"}
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    summary = preserved_section(content, "Summary", "").strip()
    status = "placeholder" if summary == "- Pending LLM summary." else "ready"
    return {
        "path": relative,
        "title": str(frontmatter.get("title") or path.stem),
        "summary": summary,
        "status": status,
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


def concept_rewrite_priority(score: int, issues: list[str], conflicts: list[dict[str, Any]]) -> str:
    if score >= 6 or conflicts or "placeholder-summary" in issues:
        return "high"
    if score >= 3:
        return "medium"
    if score > 0:
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
        }
        proposal["page_patch_plan"] = build_page_patch_plan(root, action, active_protocol=proposal_protocol)
        proposal["proposal_path"] = relative_path(root, execution_proposal_path(root, action_id))
        proposal["bundle_path"] = relative_path(root, execution_bundle_path(root, action_id))
        proposal["safe_apply_preview"] = safe_apply_preview(root, action)
        proposals.append(proposal)
    proposals.sort(
        key=lambda item: (
            action_status_rank(item["status"]),
            -int(item.get("focus_score", 0)),
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
        source_contexts = [load_source_page_context(root, relative) for relative in source_pages]
        conflict_signals = detect_concept_conflict_signals(source_contexts)
        gap_signals = detect_concept_gap_signals(source_contexts)
        issues: list[str] = []
        score = 0
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
        concept_records[slug] = {
            "slug": slug,
            "title": title,
            "path": f"wiki/concepts/{slug}.md",
            "source_pages": source_pages,
            "source_signature": str(node.get("source_signature") or ""),
            "source_count": len(source_pages),
            "related_count": len(related_slugs),
            "issues": issues,
            "score": score,
            "conflict_signals": conflict_signals[:4],
            "gap_signals": gap_signals[:4],
            "quality_state": "stable" if score == 0 else ("rewrite-now" if score >= 3 else "watch"),
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
            -len(item.get("conflict_signals", [])),
            int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    stable_concepts.sort(key=lambda item: (-int(item.get("source_count", 0)), item.get("title", "").lower()))
    rewrite_candidates.sort(
        key=lambda item: (
            action_priority_rank(item.get("priority", "")),
            -int(item.get("score", 0)),
            -int(item.get("conflict_count", 0)),
            item.get("title", "").lower(),
        )
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
        key=lambda item: (-int(item.get("score", 0)), item.get("title", "").lower()),
    )
    return {
        "all_concepts": all_concepts,
        "weak_concepts": weak_concepts[:20],
        "stable_concepts": stable_concepts[:12],
        "merge_candidates": merge_candidates[:12],
        "rewrite_candidates": rewrite_candidates[:12],
        "conflict_signals": all_conflict_signals[:12],
        "gap_signals": all_gap_signals[:12],
        "placeholder_slugs": sorted(placeholder_slugs),
        "counts": {
            "weak": len(weak_concepts),
            "stable": len(stable_concepts),
            "merge_candidates": len(merge_candidates),
            "placeholders": len(placeholder_slugs),
            "rewrite_candidates": len(rewrite_candidates),
            "conflict_signals": len(all_conflict_signals),
            "gap_signals": len(all_gap_signals),
        },
    }
