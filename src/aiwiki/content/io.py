"""IO/source-page/rendering/runtime-event symbols extracted in EP-017C step 1."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..execution.history import append_runtime_history
from ..input_router import is_obsidian_open_link
from ..protocol.runtime_config import AUTO_PROMOTION_FORMATS
from ..protocol.scaffold import ensure_layout
from ..state.constants import DEFAULT_PROTOCOL
from ..state.manifest import load_manifest
from ..utils.hash import compiled_source_sha, sha256_bytes, sha256_file
from ..utils.io import atomic_copy_file, atomic_write_text, is_atomic_write_tmp_path, runtime_write_operation
from ..utils.markdown import (
    build_citation_snapshots,
    extract_provenance_paths,
    first_markdown_heading,
    parse_frontmatter,
    raw_note_metadata,
    render_frontmatter,
    replace_first_markdown_heading,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..utils.path import next_identifier, normalize_workspace_path, relative_path
from ..utils.text import detect_kind, slugify, tokenize
from ..utils.time import parse_iso_datetime, utc_now
from .material import load_manual_link_state
from .outputs import normalize_query_signature


def sync_manifest_with_raw(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = load_manifest(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    existing_entries = [entry for entry in entries if (root / str(entry.get("stored_path") or "")).is_file()]
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
        # Skip orphan atomic-write temp files (atomic_write_text /
        # atomic_copy_file pattern: `<name>.tmp.<pid>.<monotonic_ns>`).
        # If a writer crashed mid-write the tmp may persist; it is NOT a
        # fact source and must never be registered into the manifest.
        if is_atomic_write_tmp_path(path):
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
                entry.update(
                    {
                        "sha256": current_sha,
                        "kind": current_kind,
                        "title": current_title,
                        "source_type": current_source_type,
                        "note_kind": current_note_kind,
                        "original_path": current_original_path,
                        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                        .replace(microsecond=0)
                        .isoformat(),
                    }
                )
                changed = True
            continue
        seed_label = metadata.get("title") or path.stem
        slug = slugify(seed_label)
        if slug and slug != "item":
            seed = f"source-{slug}"
        else:
            seed = f"source-{hashlib.sha256(seed_label.encode()).hexdigest()[:12]}"
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
                "imported_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
            }
        )
        known_paths.add(stored_path)
        changed = True
    if changed:
        from ..state.manifest import save_manifest

        save_manifest(root, manifest)
    return manifest


def _next_available_raw_path(directory: Path, stem: str, suffix: str) -> Path:
    """Return a non-existing raw path; caller must hold the single-writer lock."""
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


@runtime_write_operation
def ingest_source(root: Path, source: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    existing_ids = {entry["id"] for entry in manifest["entries"]}
    label = title or Path(source).stem or source
    display_title = title or label
    slug = slugify(label)
    if slug and slug != "item":
        seed = slug
    else:
        seed = hashlib.sha256(label.encode()).hexdigest()[:12]
    entry_id = next_identifier(existing_ids, seed)
    if source.startswith(("http://", "https://")):
        from ..drop import drop_url

        result = drop_url(root, source, title=title)
        manifest = load_manifest(root)
        stored_path = str(result.get("note_path") or "")
        for entry in manifest["entries"]:
            if entry.get("stored_path") == stored_path:
                return entry
        if manifest["entries"]:
            return manifest["entries"][-1]
        raise RuntimeError(f"drop url succeeded but manifest entry missing for {stored_path}")
    else:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"Source not found: {source}")
        suffix = source_path.suffix.lower()
        raw_stem = (
            f"source-{entry_id}" if (root / "raw" / "inbox" / f"source-{entry_id}{suffix}").exists() else entry_id
        )
        destination = _next_available_raw_path(root / "raw" / "inbox", raw_stem, suffix)
        entry_id = destination.stem
        atomic_copy_file(source_path, destination)
        original_path = str(source_path)
        source_type = "file"
    imported_at = utc_now()
    entry = {
        "id": entry_id,
        "title": display_title,
        "source_type": source_type,
        "original_path": original_path,
        "stored_path": relative_path(root, destination),
        "kind": detect_kind(destination),
        "sha256": sha256_file(destination),
        "imported_at": imported_at,
    }
    manifest["entries"].append(entry)
    from ..state.manifest import save_manifest

    save_manifest(root, manifest)
    append_runtime_history(
        root,
        {
            "event_type": "raw-added",
            "occurred_at": imported_at,
            "protocol": DEFAULT_PROTOCOL,
            "entry_id": entry_id,
            "source_ids": [entry_id],
            "stored_path": entry["stored_path"],
            "original_path": original_path,
            "source_type": source_type,
            "title": display_title,
        },
    )
    from ..render.paths import append_wiki_log as _append_wiki_log

    _append_wiki_log(
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


def deterministic_source_summary(preview: str, *, max_bullets: int = 3) -> str:
    bullets: list[str] = []
    skip_exact = {
        "capture metadata",
        "captured note",
        "source record",
        "summary",
        "concept links",
        "enrichment todo",
        "preview",
        "citation anchor",
    }
    for raw_line in preview.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        normalized = line.strip("# ").strip().lower()
        if normalized in skip_exact:
            continue
        if line.startswith("- Captured at:") or line.startswith("- Capture mode:") or line.startswith("- Note kind:"):
            continue
        cleaned = re.sub(r"^#{1,6}\s*", "", line)
        cleaned = re.sub(r"^[-*]\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            continue
        bullets.append(f"- Deterministic preview: {cleaned[:220]}")
        if len(bullets) >= max_bullets:
            break
    if not bullets:
        return "- Pending LLM summary."
    return "\n".join(["- Pending LLM summary.", *bullets])


def render_source_page_with_state(
    entry: dict[str, Any], preview: str, compiled_at: str, *, concepts: list[str], existing_page: str
) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = compiled_source_sha(existing_page) not in ("", entry["sha256"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "low") if not source_changed else "low"
    if not isinstance(confidence, str) or not confidence:
        confidence = "low"
    deterministic_summary = deterministic_source_summary(preview)
    if source_changed:
        summary = deterministic_summary
    else:
        summary = preserved_section(existing_page, "Summary", deterministic_summary)
        if summary.strip() == "- Pending LLM summary.":
            summary = deterministic_summary
    from ..vault_obsidian_graph import render_plain_concept_link_lines

    concept_links = render_plain_concept_link_lines(concepts)
    stored_path = str(entry.get("stored_path") or "").replace("\\", "/").strip()
    raw_material_lines = (
        [f"- [[{stored_path}|{entry['title']}]]"] if stored_path.startswith("raw/") else ["- 暂无 raw 原料路径。"]
    )
    frontmatter = render_frontmatter(
        {
            "id": entry["id"],
            "kind": "source",
            "status": "compiled",
            "title": entry["title"],
            "source_files": [entry["stored_path"]],
            "source_sha256": entry["sha256"],
            "source_updated_at": entry.get("updated_at") or entry["imported_at"],
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
            "## 来源记录",
            f"- 来源类型：`{entry['source_type']}`",
            f"- 原始路径：`{entry['original_path']}`",
            f"- 存储路径：`{entry['stored_path']}`",
            f"- 入库时间：`{entry['imported_at']}`",
            f"- 更新时间：`{entry.get('updated_at') or entry['imported_at']}`",
            f"- SHA256：`{entry['sha256']}`",
            "",
            "## 原料文件",
            *raw_material_lines,
            "",
            "## 摘要",
            summary,
            "",
            "## 概念链接",
            *concept_links,
            "",
            "## 充实待办",
            "- 有新来源改变综合判断时，刷新概念链接。",
            "- 为引用本页的派生输出补上反向链接。",
            "- 替换占位正文时保留 provenance。",
            "",
            "## 预览",
            "```text",
            preview,
            "```",
            "",
            "## 引用锚点",
            f"- 引用本页请写 `wiki/sources/{entry['id']}.md`。",
        ]
    )
    return body + "\n"


def preserved_section(markdown: str, heading: str, fallback: str) -> str:
    if not markdown:
        return fallback
    from .page_sections import section_candidates

    for name in section_candidates(heading):
        match = re.search(rf"(?ms)^## {re.escape(name)}\n(.*?)(?=^## |\Z)", markdown)
        if not match:
            continue
        section = match.group(1).strip()
        return section or fallback
    return fallback


def normalized_markdown_section_lines(markdown: str, heading: str) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    return [line.strip() for line in section.splitlines() if line.strip()] if section else []


def curated_asset_placeholder_lines(heading: str, *, revisit_after: str = "", escalate_after: str = "") -> list[str]:
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
    section_overrides: dict[str, list[str]] | None = None,
) -> list[str]:
    sections: list[str] = []
    from ..protocol.templates import CURATED_ASSET_SECTION_ORDER

    for heading in CURATED_ASSET_SECTION_ORDER:
        if heading == "Review History":
            continue
        override_lines = (section_overrides or {}).get(heading)
        body_lines = (
            override_lines
            if override_lines
            else curated_asset_placeholder_lines(heading, revisit_after=revisit_after, escalate_after=escalate_after)
        )
        sections.extend(["", f"## {heading}", *body_lines])
    return sections


def render_review_history_section() -> list[str]:
    return ["", "## Review History", *curated_asset_placeholder_lines("Review History")]


def curated_asset_section_snapshot(
    markdown: str, heading: str, *, revisit_after: str = "", escalate_after: str = ""
) -> dict[str, Any]:
    lines = normalized_markdown_section_lines(markdown, heading)
    placeholders = curated_asset_placeholder_lines(heading, revisit_after=revisit_after, escalate_after=escalate_after)
    meaningful_lines = [line for line in lines if line not in placeholders]
    review_history_entries = (
        sum(1 for line in meaningful_lines if line.startswith("- `")) if heading == "Review History" else 0
    )
    return {
        "present": bool(lines),
        "meaningful": bool(meaningful_lines),
        "placeholder_only": bool(lines) and not meaningful_lines,
        "review_history_entries": review_history_entries,
    }


def append_review_history_entry(
    markdown: str, *, reviewed_at: str, status: str, note: str | None = None, confidence: str | None = None
) -> str:
    """No-op: do not append unbounded Review History into Obsidian pages.

    Page-local history grew without bound (same failure mode as retired
    ``wiki/indexes/log.md``). Canonical review events live in
    ``.aiwiki/state/runtime-history.jsonl`` and execution receipts.
    ``reviewed_at`` / ``status`` / ``note`` / ``confidence`` are kept for
    call-site compatibility.
    """

    _ = (reviewed_at, status, note, confidence)
    return markdown


def review_history_entries(markdown: str) -> list[str]:
    return [
        line
        for line in normalized_markdown_section_lines(markdown, "Review History")
        if line != "- No review history yet."
    ]


def source_summary_or_preview(root: Path, entry: dict[str, Any], preview: str) -> str:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if page.exists():
        content = page.read_text(encoding="utf-8", errors="replace")
        summary = preserved_section(content, "Summary", "")
        if compiled_source_sha(content) in ("", entry["sha256"]) and summary and "Pending LLM summary." not in summary:
            non_preview_lines = [
                line for line in summary.splitlines() if not line.strip().startswith("- Deterministic preview:")
            ]
            cleaned_summary = "\n".join(line for line in non_preview_lines if line.strip()).strip()
            return cleaned_summary or summary
    return preview


def active_manual_source_concept_links(root: Path) -> dict[str, set[str]]:
    state = load_manual_link_state(root)
    mapping: dict[str, set[str]] = {}
    for item in state.get("source_to_concept", []):
        source_id = str(item.get("source_id") or "").strip()
        concept_slug = str(item.get("concept_slug") or "").strip()
        if source_id and concept_slug and bool(item.get("active", True)):
            mapping.setdefault(source_id, set()).add(concept_slug)
    return mapping


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
            if is_obsidian_open_link(query):
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
            if frontmatter.get("kind") == "output":
                query = str(frontmatter.get("query") or "").strip()
                if is_obsidian_open_link(query):
                    continue
                artifacts.append(
                    {
                        "path": relative_path(root, path),
                        "query": query,
                        "format": str(frontmatter.get("format") or "").strip(),
                        "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                        "created_at": str(frontmatter.get("created_at") or ""),
                        "title": first_markdown_heading(content) or path.stem,
                        "run_id": str(frontmatter.get("run_id") or ""),
                        "run_notes_path": str(frontmatter.get("run_notes_path") or ""),
                    }
                )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]))


def collect_recent_output_artifacts(root: Path, *, limit: int = 12) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") == "output" and str(frontmatter.get("generated_by") or "") != "aiwiki-compile":
                background_status = str(frontmatter.get("background_status") or "")
                if background_status in {"submitted", "running"}:
                    continue
                title = first_markdown_heading(content) or path.stem
                delivery_mode = str(frontmatter.get("delivery_mode") or "")
                llm_status = str(frontmatter.get("llm_status") or "")
                contains_placeholder = "_LLM:" in content
                query = str(frontmatter.get("query") or "").strip()
                background_job_id = str(frontmatter.get("background_job_id") or "")
                if is_obsidian_open_link(query) or (
                    contains_placeholder
                    and (background_job_id or delivery_mode == "background-pending" or llm_status == "pending")
                ):
                    continue
                degraded = (
                    delivery_mode == "deterministic-fallback"
                    or llm_status in {"timeout_or_unavailable", "validation_failed", "pending", "failed", "degraded"}
                    or background_status == "degraded"
                    or title.startswith("LLM 未完成")
                )
                artifact_quality = "degraded" if degraded else "deliverable"
                artifacts.append(
                    {
                        "path": relative_path(root, path),
                        "query": query,
                        "format": str(frontmatter.get("format") or "").strip(),
                        "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                        "created_at": str(frontmatter.get("created_at") or ""),
                        "title": title,
                        "run_id": str(frontmatter.get("run_id") or ""),
                        "run_notes_path": str(frontmatter.get("run_notes_path") or ""),
                        "delivery_mode": delivery_mode,
                        "llm_status": llm_status,
                        "llm_backend": str(frontmatter.get("llm_backend") or ""),
                        "llm_model": str(frontmatter.get("llm_model") or ""),
                        "llm_failure_reason": str(frontmatter.get("llm_failure_reason") or ""),
                        "background_job_id": background_job_id,
                        "background_status": background_status,
                        "artifact_quality": artifact_quality,
                        "contains_llm_placeholder": "true" if contains_placeholder else "false",
                    }
                )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]), reverse=True)[:limit]


def find_promoted_curated_page(root: Path, kind: str, query_signature: str, protocol: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if (
            frontmatter.get("kind") == kind
            and str(frontmatter.get("promotion_query_signature") or "") == query_signature
        ):
            page_protocol = str(frontmatter.get("protocol") or "")
            if page_protocol == protocol or (not page_protocol and protocol == DEFAULT_PROTOCOL):
                return path
    return None


def recurring_promotion_needs_refresh(page_path: Path, artifacts: list[dict[str, str]]) -> bool:
    frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8", errors="replace"))
    current_count = str(frontmatter.get("promotion_count") or "")
    current_last_artifact = str(frontmatter.get("promotion_last_artifact") or "")
    current_sources = {
        str(path) for path in frontmatter.get("source_files", []) if isinstance(path, str) and path.strip()
    }
    desired_count = str(len(artifacts))
    desired_last_artifact = artifacts[-1]["path"]
    desired_sources = {artifact["path"] for artifact in artifacts}
    return (
        current_count != desired_count
        or current_last_artifact != desired_last_artifact
        or not desired_sources.issubset(current_sources)
    )


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
    source_files = [str(path) for path in frontmatter.get("source_files", []) if isinstance(path, str) and path.strip()]
    for artifact in artifacts:
        if artifact["path"] not in source_files:
            source_files.append(artifact["path"])
    citations = [str(path) for path in frontmatter.get("citations", []) if isinstance(path, str) and path.strip()]
    seen_citations = set(citations)
    for artifact in artifacts:
        artifact_path = root / artifact["path"]
        if artifact_path.exists():
            for citation in extract_provenance_paths(root, artifact_path.read_text(encoding="utf-8", errors="replace")):
                if citation not in seen_citations:
                    seen_citations.add(citation)
                    citations.append(citation)
    formats = sorted({artifact["format"] for artifact in artifacts})
    from .outputs import promotion_page_title

    title = promotion_page_title(kind, query, protocol)
    citation_snapshots = build_citation_snapshots(root, citations)
    frontmatter.update(
        {
            "title": title,
            "protocol": protocol,
            "source_files": source_files,
            "citations": citations,
            "citation_snapshots": citation_snapshots,
            "promotion_origin": "nightly-recurring-output",
            "promotion_query": query,
            "promotion_query_signature": query_signature,
            "promotion_count": str(len(artifacts)),
            "promotion_formats": formats,
            "promotion_last_artifact": artifacts[-1]["path"],
            "last_compiled_at": generated_at,
        }
    )
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
    section = upsert_markdown_section(body, "Auto Promotion", "\n".join(auto_lines)).strip()
    atomic_write_text(page_path, f"{render_frontmatter(frontmatter)}\n\n{section}\n")


def manifest_change_summary(
    previous_entries: list[dict[str, Any]], current_entries: list[dict[str, Any]]
) -> dict[str, int]:
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
    added_paths = set(current_by_path) - set(previous_by_path)
    removed_paths = set(previous_by_path) - set(current_by_path)
    updated_paths = sum(
        1
        for stored_path in set(current_by_path) & set(previous_by_path)
        if any(
            previous_by_path[stored_path].get(field) != current_by_path[stored_path].get(field)
            for field in ("sha256", "title", "kind", "source_type", "note_kind", "original_path")
        )
    )
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
        focus_ref = str(event.get("focus_ref") or "")
        summary.update(
            {
                "title": focus_ref or "Query",
                "output_path": str(event.get("output_ref") or ""),
                "corpus_id": str(event.get("corpus_id") or ""),
                "output_format": str(event.get("output_format") or ""),
                "run_id": str(event.get("run_id") or ""),
                "run_notes_path": str(event.get("run_notes_path") or ""),
                "ignored_by_shell": is_obsidian_open_link(focus_ref),
            }
        )
    elif event_type == "review":
        summary.update(
            {
                "title": str(event.get("page_path") or "Review"),
                "page_path": str(event.get("page_path") or ""),
                "status": str(event.get("status") or ""),
                "page_kind": str(event.get("page_kind") or ""),
            }
        )
    elif event_type == "knowledge-lifecycle-override":
        summary.update(
            {
                "title": str(event.get("slug") or event.get("page_id") or "Lifecycle override"),
                "operation": str(event.get("operation") or ""),
                "path": str(event.get("path") or ""),
                "lifecycle_state": str(event.get("lifecycle_state") or ""),
            }
        )
    elif event_type in {"rewrite-review", "rewrite-apply", "rewrite-verify", "rewrite-revert"}:
        summary.update(
            {
                "title": str(event.get("slug") or event.get("target_path") or "Concept rewrite"),
                "path": str(event.get("target_path") or ""),
                "status": str(event.get("status") or ""),
                "verification_status": str(event.get("verification_status") or ""),
            }
        )
    elif event_type in {"archive-apply", "archive-revert"}:
        entry_id = str(event.get("source_ids", ["archive"])[0] if event.get("source_ids") else "Archive")
        summary.update(
            {
                "title": entry_id,
                "entry_id": entry_id,
                "receipt_path": str(event.get("receipt_path") or ""),
                "source_ids": [str(item) for item in event.get("source_ids", []) if item],
            }
        )
    elif event_type == "nightly":
        summary.update(
            {
                "title": "Nightly health",
                "active_corpus_ids": [str(item) for item in event.get("active_corpus_ids", []) if item],
                "cooled_corpus_ids": [str(item) for item in event.get("cooled_corpus_ids", []) if item],
                "expired_corpus_ids": [str(item) for item in event.get("expired_corpus_ids", []) if item],
            }
        )
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
        path_to_entry_id[f"wiki/sources/{entry_id}.md"] = entry_id
    return by_id, path_to_entry_id


def entry_ids_from_paths(path_to_entry_id: dict[str, str], paths: list[str]) -> list[str]:
    entry_ids: list[str] = []
    seen: set[str] = set()
    for candidate in paths:
        normalized = normalize_workspace_path(candidate)
        entry_id = path_to_entry_id.get(normalized, "")
        if not entry_id and normalized.startswith("wiki/sources/") and normalized.endswith(".md"):
            entry_id = Path(normalized).stem
        if entry_id and entry_id not in seen:
            seen.add(entry_id)
            entry_ids.append(entry_id)
    return entry_ids


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
    return {
        "path": relative,
        "title": str(frontmatter.get("title") or path.stem),
        "summary": summary,
        "status": "placeholder" if summary == "- Pending LLM summary." else "ready",
        "last_compiled_at": str(frontmatter.get("last_compiled_at") or ""),
    }


def source_ids_for_citations(root: Path, entries: list[dict[str, Any]], markdown: str) -> list[str]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    return entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, markdown))


def scan_material_reference_state(
    root: Path,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    _by_id, path_to_entry_id = entry_lookup_maps(entries)
    citation_count_by_entry: dict[str, int] = {}
    supports_judgment_ids: dict[str, set[str]] = {}
    active_judgment_ids: set[str] = set()

    for relative in ("wiki/derived", "wiki/decisions", "wiki/judgments"):
        directory = root / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            cited_entry_ids = entry_ids_from_paths(path_to_entry_id, extract_provenance_paths(root, content))
            for entry_id in cited_entry_ids:
                citation_count_by_entry[entry_id] = citation_count_by_entry.get(entry_id, 0) + 1
            if relative != "wiki/judgments":
                continue
            frontmatter = parse_frontmatter(content)
            judgment_id = str(frontmatter.get("id") or path.stem)
            if str(frontmatter.get("status") or "") != "rejected":
                active_judgment_ids.add(judgment_id)
            for entry_id in cited_entry_ids:
                supports_judgment_ids.setdefault(entry_id, set()).add(judgment_id)

    return {
        "citation_count_by_entry": citation_count_by_entry,
        "supports_judgment_ids": {entry_id: sorted(ids) for entry_id, ids in supports_judgment_ids.items()},
        "active_judgment_ids": sorted(active_judgment_ids),
    }
