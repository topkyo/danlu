"""IO/source-page/rendering/runtime-event symbols extracted in EP-017C step 1."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..app_protocol import AUTO_PROMOTION_FORMATS, ensure_layout
from ..app_state import DEFAULT_PROTOCOL, load_manifest, load_manual_link_state
from ..app_utils import (
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
            if (entry.get("sha256") != current_sha or entry.get("kind") != current_kind or entry.get("title") != current_title or entry.get("source_type") != current_source_type or entry.get("note_kind") != current_note_kind or entry.get("original_path") != current_original_path):
                entry.update({"sha256": current_sha, "kind": current_kind, "title": current_title, "source_type": current_source_type, "note_kind": current_note_kind, "original_path": current_original_path, "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()})
                changed = True
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        seed_label = metadata.get("title") or path.stem
        seed = f"discovered-{stamp}-{slugify(seed_label)}"
        entry_id = next_identifier(existing_ids, seed)
        existing_ids.add(entry_id)
        entries.append({"id": entry_id, "title": metadata.get("title") or path.stem, "source_type": metadata.get("source_type") or "raw-drop", "note_kind": metadata.get("note_kind") or "", "original_path": metadata.get("original_path") or stored_path, "stored_path": stored_path, "kind": detect_kind(path), "sha256": sha256_file(path), "imported_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(), "updated_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()})
        known_paths.add(stored_path)
        changed = True
    if changed:
        from .. import app_content as _facade
        _facade.save_manifest(root, manifest)
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
    if source.startswith(("http://", "https://")):
        destination = root / "raw" / "inbox" / f"{entry_id}.md"
        stub_title = title or source
        destination.write_text("\n".join([f"# {stub_title}", "", "## 来源 URL", f"- {source}", "", "## 采集状态", "- 这个 URL 目前只是一个占位 stub。", "- 在把它当作事实来源前，请先用剪藏 markdown 或本地附件替换成更完整材料。", "", "## 备注", "- 在补充更完整材料之前，编译器会把这个文件视为占位来源。", ""]) + "\n", encoding="utf-8")
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
    entry = {"id": entry_id, "title": display_title, "source_type": source_type, "original_path": original_path, "stored_path": relative_path(root, destination), "kind": detect_kind(destination), "sha256": sha256_file(destination), "imported_at": utc_now()}
    manifest["entries"].append(entry)
    from .. import app_content as _facade
    _facade.save_manifest(root, manifest)
    from ..app_render import append_wiki_log as _append_wiki_log
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


def render_source_page_with_state(entry: dict[str, Any], preview: str, compiled_at: str, *, concepts: list[str], existing_page: str) -> str:
    from .. import app_content as _facade
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = compiled_source_sha(existing_page) not in ("", entry["sha256"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "low") if not source_changed else "low"
    if not isinstance(confidence, str) or not confidence:
        confidence = "low"
    summary = preserved_section(existing_page, "Summary", "- Pending LLM summary.") if not source_changed else "- Pending LLM summary."
    concept_links = ["- No concept links yet."] if not concepts else [f"- [{_facade.concept_label_to_title(label)}](../concepts/{_facade.concept_label_to_slug(label)}.md)" for label in concepts]
    frontmatter = render_frontmatter({"id": entry["id"], "kind": "source", "status": "compiled", "title": entry["title"], "source_files": [entry["stored_path"]], "source_sha256": entry["sha256"], "citations": citations, "concepts": concepts, "generated_by": "aiwiki-compile", "last_compiled_at": compiled_at, "confidence": confidence})
    body = "\n".join([frontmatter, "", f"# {entry['title']}", "", "## Source Record", f"- Source type: `{entry['source_type']}`", f"- Original path: `{entry['original_path']}`", f"- Stored path: `{entry['stored_path']}`", f"- Imported at: `{entry['imported_at']}`", f"- SHA256: `{entry['sha256']}`", "", "## Summary", summary, "", "## Concept Links", *concept_links, "", "## Enrichment TODO", "- Refresh concept links when new sources shift the synthesis.", "- Add backlinks from derived outputs that cite this page.", "- Preserve provenance when replacing placeholder text.", "", "## Preview", "```text", preview, "```", "", "## Citation Anchor", f"- Cite this page as `wiki/sources/{entry['id']}.md`."])
    return body + "\n"


def preserved_section(markdown: str, heading: str, fallback: str) -> str:
    if not markdown:
        return fallback
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown)
    if not match:
        return fallback
    section = match.group(1).strip()
    return section or fallback


def normalized_markdown_section_lines(markdown: str, heading: str) -> list[str]:
    section = preserved_section(markdown, heading, "").strip()
    return [line.strip() for line in section.splitlines() if line.strip()] if section else []


def curated_asset_placeholder_lines(heading: str, *, revisit_after: str = "", escalate_after: str = "") -> list[str]:
    placeholders = {"Counter Evidence": ["- Pending counter evidence."], "Invalidation": ["- Pending invalidation conditions."], "Next Signals": ["- Pending next signals.", f"- Default revisit window: `{revisit_after or 'none'}`", f"- Default escalation window: `{escalate_after or 'none'}`"], "Review History": ["- No review history yet."]}
    return placeholders.get(heading, [])


def render_curated_asset_sections(*, revisit_after: str, escalate_after: str) -> list[str]:
    sections: list[str] = []
    from ..app_protocol import CURATED_ASSET_SECTION_ORDER
    for heading in CURATED_ASSET_SECTION_ORDER:
        if heading == "Review History":
            continue
        sections.extend(["", f"## {heading}", *curated_asset_placeholder_lines(heading, revisit_after=revisit_after, escalate_after=escalate_after)])
    return sections


def render_review_history_section() -> list[str]:
    return ["", "## Review History", *curated_asset_placeholder_lines("Review History")]


def curated_asset_section_snapshot(markdown: str, heading: str, *, revisit_after: str = "", escalate_after: str = "") -> dict[str, Any]:
    lines = normalized_markdown_section_lines(markdown, heading)
    placeholders = curated_asset_placeholder_lines(heading, revisit_after=revisit_after, escalate_after=escalate_after)
    meaningful_lines = [line for line in lines if line not in placeholders]
    review_history_entries = sum(1 for line in meaningful_lines if line.startswith("- `")) if heading == "Review History" else 0
    return {"present": bool(lines), "meaningful": bool(meaningful_lines), "placeholder_only": bool(lines) and not meaningful_lines, "review_history_entries": review_history_entries}


def append_review_history_entry(markdown: str, *, reviewed_at: str, status: str, note: str | None = None, confidence: str | None = None) -> str:
    existing_lines = normalized_markdown_section_lines(markdown, "Review History")
    history_lines = [line for line in existing_lines if line != "- No review history yet."]
    entry_parts = [f"- `{reviewed_at}` | status `{status}`"]
    if confidence:
        entry_parts.append(f"confidence `{confidence}`")
    entry_parts.append(f"note {note}" if note else "note none")
    history_lines.insert(0, " | ".join(entry_parts))
    return upsert_markdown_section(markdown, "Review History", "\n".join(history_lines))


def review_history_entries(markdown: str) -> list[str]:
    return [line for line in normalized_markdown_section_lines(markdown, "Review History") if line != "- No review history yet."]


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
            artifacts.append({"path": relative_path(root, path), "query": query, "query_signature": normalize_query_signature(query), "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL), "format": output_format, "created_at": str(frontmatter.get("created_at") or ""), "title": first_markdown_heading(content) or path.stem})
    return sorted(artifacts, key=lambda item: (item["query_signature"], item["created_at"], item["path"]))


def collect_output_density_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") == "output":
                artifacts.append({"path": relative_path(root, path), "query": str(frontmatter.get("query") or "").strip(), "format": str(frontmatter.get("format") or "").strip(), "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL), "created_at": str(frontmatter.get("created_at") or ""), "title": first_markdown_heading(content) or path.stem})
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]))


def collect_recent_output_artifacts(root: Path, *, limit: int = 12) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") == "output" and str(frontmatter.get("generated_by") or "") != "aiwiki-compile":
                artifacts.append({"path": relative_path(root, path), "query": str(frontmatter.get("query") or "").strip(), "format": str(frontmatter.get("format") or "").strip(), "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL), "created_at": str(frontmatter.get("created_at") or ""), "title": first_markdown_heading(content) or path.stem})
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]), reverse=True)[:limit]


def find_promoted_curated_page(root: Path, kind: str, query_signature: str, protocol: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if frontmatter.get("kind") == kind and str(frontmatter.get("promotion_query_signature") or "") == query_signature:
            page_protocol = str(frontmatter.get("protocol") or "")
            if page_protocol == protocol or (not page_protocol and protocol == DEFAULT_PROTOCOL):
                return path
    return None


def recurring_promotion_needs_refresh(page_path: Path, artifacts: list[dict[str, str]]) -> bool:
    frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8", errors="replace"))
    current_count = str(frontmatter.get("promotion_count") or "")
    current_last_artifact = str(frontmatter.get("promotion_last_artifact") or "")
    current_sources = {str(path) for path in frontmatter.get("source_files", []) if isinstance(path, str) and path.strip()}
    desired_count = str(len(artifacts))
    desired_last_artifact = artifacts[-1]["path"]
    desired_sources = {artifact["path"] for artifact in artifacts}
    return current_count != desired_count or current_last_artifact != desired_last_artifact or not desired_sources.issubset(current_sources)


def annotate_recurring_promotion(root: Path, page_path: Path, *, kind: str, protocol: str, query: str, query_signature: str, artifacts: list[dict[str, str]], generated_at: str) -> None:
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
    from .. import app_content as _facade
    title = _facade.promotion_page_title(kind, query, protocol)
    citation_snapshots = build_citation_snapshots(root, citations)
    frontmatter.update({"title": title, "protocol": protocol, "source_files": source_files, "citations": citations, "citation_snapshots": citation_snapshots, "promotion_origin": "nightly-recurring-output", "promotion_query": query, "promotion_query_signature": query_signature, "promotion_count": str(len(artifacts)), "promotion_formats": formats, "promotion_last_artifact": artifacts[-1]["path"], "last_compiled_at": generated_at})
    body = replace_first_markdown_heading(strip_frontmatter(content).strip(), title).strip()
    auto_lines = ["- Rule: `nightly-recurring-output`", f"- Protocol: `{protocol}`", f"- Query: `{query}`", f"- Signature: `{query_signature}`", f"- Matching outputs: `{len(artifacts)}`", f"- Latest artifact: `{artifacts[-1]['path']}`", f"- Formats: `{', '.join(formats)}`"]
    for artifact in artifacts[-5:]:
        auto_lines.append(f"- Supporting artifact: `{artifact['path']}`")
    section = upsert_markdown_section(body, "Auto Promotion", "\n".join(auto_lines)).strip()
    page_path.write_text(f"{render_frontmatter(frontmatter)}\n\n{section}\n", encoding="utf-8")


def manifest_change_summary(previous_entries: list[dict[str, Any]], current_entries: list[dict[str, Any]]) -> dict[str, int]:
    previous_by_path = {str(entry.get("stored_path") or ""): entry for entry in previous_entries if isinstance(entry, dict) and str(entry.get("stored_path") or "")}
    current_by_path = {str(entry.get("stored_path") or ""): entry for entry in current_entries if isinstance(entry, dict) and str(entry.get("stored_path") or "")}
    added_paths = set(current_by_path) - set(previous_by_path)
    removed_paths = set(previous_by_path) - set(current_by_path)
    updated_paths = sum(1 for stored_path in set(current_by_path) & set(previous_by_path) if any(previous_by_path[stored_path].get(field) != current_by_path[stored_path].get(field) for field in ("sha256", "title", "kind", "source_type", "note_kind", "original_path")))
    return {"manifest_entries": len(current_entries), "added_entries": len(added_paths), "updated_entries": updated_paths, "removed_entries": len(removed_paths), "changed_entries": len(added_paths) + updated_paths + len(removed_paths)}


def summarize_runtime_event_for_shell(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or "")
    summary = {"event_type": event_type, "occurred_at": str(event.get("occurred_at") or ""), "protocol": str(event.get("protocol") or ""), "title": ""}
    if event_type == "query":
        summary.update({"title": str(event.get("focus_ref") or "Query"), "output_path": str(event.get("output_ref") or ""), "corpus_id": str(event.get("corpus_id") or ""), "output_format": str(event.get("output_format") or "")})
    elif event_type == "review":
        summary.update({"title": str(event.get("page_path") or "Review"), "page_path": str(event.get("page_path") or ""), "status": str(event.get("status") or ""), "page_kind": str(event.get("page_kind") or "")})
    elif event_type == "knowledge-lifecycle-override":
        summary.update({"title": str(event.get("slug") or event.get("page_id") or "Lifecycle override"), "operation": str(event.get("operation") or ""), "path": str(event.get("path") or ""), "lifecycle_state": str(event.get("lifecycle_state") or "")})
    elif event_type in {"rewrite-review", "rewrite-apply", "rewrite-verify", "rewrite-revert"}:
        summary.update({"title": str(event.get("slug") or event.get("target_path") or "Concept rewrite"), "path": str(event.get("target_path") or ""), "status": str(event.get("status") or ""), "verification_status": str(event.get("verification_status") or "")})
    elif event_type in {"archive-apply", "archive-revert"}:
        entry_id = str(event.get("source_ids", ["archive"])[0] if event.get("source_ids") else "Archive")
        summary.update({"title": entry_id, "entry_id": entry_id, "receipt_path": str(event.get("receipt_path") or ""), "source_ids": [str(item) for item in event.get("source_ids", []) if item]})
    elif event_type == "nightly":
        summary.update({"title": "Nightly health", "active_corpus_ids": [str(item) for item in event.get("active_corpus_ids", []) if item], "cooled_corpus_ids": [str(item) for item in event.get("cooled_corpus_ids", []) if item], "expired_corpus_ids": [str(item) for item in event.get("expired_corpus_ids", []) if item]})
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
        return {"path": relative, "title": relative.rsplit("/", 1)[-1], "summary": "", "status": "missing", "last_compiled_at": ""}
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    summary = preserved_section(content, "Summary", "").strip()
    return {"path": relative, "title": str(frontmatter.get("title") or path.stem), "summary": summary, "status": "placeholder" if summary == "- Pending LLM summary." else "ready", "last_compiled_at": str(frontmatter.get("last_compiled_at") or "")}
