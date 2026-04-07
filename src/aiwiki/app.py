"""Core application logic for the aiwiki MVP."""

from __future__ import annotations

from collections import deque
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LAYOUT_DIRS = (
    "raw/inbox",
    "raw/normalized",
    "raw/assets",
    "schema",
    "wiki/sources",
    "wiki/concepts",
    "wiki/indexes",
    "wiki/derived",
    "output/reports",
    "output/slides",
    "output/figures",
    "output/lint",
    "prompts",
    ".aiwiki/state",
    ".aiwiki/cache",
    ".aiwiki/logs",
)

DEFAULT_SCHEMA_FILES = {
    "schema/index.md": "\n".join(
        [
            "# Runtime Schema",
            "",
            "This directory contains runtime policy for `aiwiki`.",
            "",
            "It is product-facing policy, not developer governance.",
            "",
            "## Core Policy Files",
            "",
            "- [Ingest Rules](./ingest.md)",
            "- [Citation Rules](./citations.md)",
            "- [Conflict Rules](./conflicts.md)",
            "- [Writeback Rules](./writeback.md)",
            "- [Taxonomy Rules](./taxonomy.md)",
            "",
            "## Boundary",
            "",
            "- `AGENTS.md` and `CLAUDE.md` are repository/developer files.",
            "- Runtime behavior should be driven by this directory plus `prompts/`.",
        ]
    )
    + "\n",
    "schema/ingest.md": "\n".join(
        [
            "# Ingest Rules",
            "",
            "- Preserve original assets when available.",
            "- Record original path or URL in capture notes.",
            "- Keep ingest-generated notes in `raw/` linked back to their evidence.",
            "- Never treat URL stubs or partial captures as strong evidence without saying so.",
        ]
    )
    + "\n",
    "schema/citations.md": "\n".join(
        [
            "# Citation Rules",
            "",
            "- Prefer `wiki/sources/*.md` citations in compiled and output layers.",
            "- Preserve file-path provenance back to `raw/` whenever possible.",
            "- Do not present unsupported synthesis as fact.",
            "- If evidence is weak, partial, or conflicting, state that explicitly.",
        ]
    )
    + "\n",
    "schema/conflicts.md": "\n".join(
        [
            "# Conflict Rules",
            "",
            "- Keep contradictions explicit instead of smoothing them away.",
            "- Prefer uncertainty over invented reconciliation.",
            "- When sources disagree, point to both source pages.",
            "- Track repeated drift or ambiguity in lint and future repair loops.",
        ]
    )
    + "\n",
    "schema/writeback.md": "\n".join(
        [
            "# Writeback Rules",
            "",
            "- High-value outputs may be filed back into `wiki/derived/`.",
            "- Filed-back notes must not overwrite source pages or raw evidence.",
            "- Derived pages should cite their source pages or raw evidence.",
            "- Writeback is compounding knowledge, not silent mutation of facts.",
        ]
    )
    + "\n",
    "schema/taxonomy.md": "\n".join(
        [
            "# Taxonomy Rules",
            "",
            "- Keep concept names stable and human-readable.",
            "- Prefer concept pages over repeating the same synthesis in many source pages.",
            "- Separate source pages, concept pages, derived pages, and outputs by role.",
            "- Promote repeated patterns into schema or decision pages when they become stable.",
        ]
    )
    + "\n",
}

TEXT_EXTENSIONS = {
    ".csv",
    ".json",
    ".markdown",
    ".md",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}

STOP_WORDS = {
    "about",
    "article",
    "articles",
    "after",
    "against",
    "brief",
    "browser",
    "compare",
    "compiled",
    "file",
    "files",
    "figure",
    "from",
    "image",
    "images",
    "into",
    "must",
    "note",
    "notes",
    "page",
    "pages",
    "question",
    "report",
    "rendered",
    "smoke",
    "source",
    "sources",
    "slides",
    "that",
    "their",
    "there",
    "these",
    "this",
    "with",
    "wiki",
}


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema(root)


def ensure_runtime_schema(root: Path) -> None:
    for relative, content in DEFAULT_SCHEMA_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "item"


def detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".txt", ".rst"}:
        return "text"
    if suffix in {".json", ".yaml", ".yml", ".csv", ".tsv", ".toml"}:
        return "data"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if not suffix:
        return "file"
    return suffix.lstrip(".")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "manifest.json"


def default_manifest() -> dict[str, Any]:
    return {"version": 1, "entries": []}


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    if not path.exists():
        return default_manifest()
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    ensure_layout(root)
    path = manifest_path(root)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def next_identifier(existing_ids: set[str], seed: str) -> str:
    candidate = seed
    index = 2
    while candidate in existing_ids:
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def read_text_preview(path: Path, limit_lines: int = 12, limit_chars: int = 1600) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return f"Preview unavailable for {path.suffix or 'unknown'} files."
    text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    preview = "\n".join(text.splitlines()[:limit_lines]).strip()
    if len(preview) > limit_chars:
        preview = preview[:limit_chars].rstrip() + "..."
    return preview or "(empty text file)"


def raw_note_metadata(path: Path) -> dict[str, str]:
    if path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return {}
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    result: dict[str, str] = {}
    for key in ("title", "source_type", "original_path"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def render_scalar(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def render_frontmatter(mapping: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in mapping.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {render_scalar(item)}")
        else:
            lines.append(f"{key}: {render_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def parse_scalar(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    return value


def parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - ") and current_key is not None:
            data.setdefault(current_key, []).append(parse_scalar(line[4:]))
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw:
            data[key] = parse_scalar(raw)
            current_key = None
        else:
            data[key] = []
            current_key = key
    return data


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip()
    return text


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
    path.write_text(content, encoding="utf-8")
    return True


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
                "## Source URL",
                f"- {source}",
                "",
                "## Capture Status",
                "- This URL was registered as a stub.",
                "- Replace it with clipped markdown or an attached asset before trusting it as a fact source.",
                "",
                "## Notes",
                "- The compiler will treat this file as a placeholder source until richer material is ingested.",
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


def compiled_source_sha(markdown: str) -> str:
    if not markdown:
        return ""
    frontmatter = parse_frontmatter(markdown)
    sha = frontmatter.get("source_sha256")
    if isinstance(sha, str) and sha:
        return sha
    match = re.search(r"(?m)^- SHA256: `([^`]+)`", markdown)
    if match:
        return match.group(1)
    return ""


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


def build_concept_records(
    root: Path,
    entries: list[dict[str, Any]],
    previews: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    concept_map: dict[str, dict[str, Any]] = {}
    entry_terms: dict[str, list[str]] = {}
    for entry in entries:
        context = source_summary_or_preview(root, entry, previews[entry["id"]])
        terms = entry_concept_terms(entry, context)
        entry_terms[entry["id"]] = terms
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
                },
            )
            record["entries"].append(entry)
            record["score"] += 1

    ranked_records = sorted(concept_map.values(), key=lambda item: (-item["score"], item["title"].lower()))[:30]
    allowed = {record["slug"] for record in ranked_records}
    filtered_entry_terms: dict[str, list[str]] = {}
    for entry_id, labels in entry_terms.items():
        filtered = [label for label in labels if concept_label_to_slug(label) in allowed]
        filtered_entry_terms[entry_id] = filtered[:5]

    by_slug = {record["slug"]: record for record in ranked_records}
    for record in ranked_records:
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
    return ranked_records, filtered_entry_terms


def concept_source_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": record["slug"],
        "entry_ids": sorted(record["entry_ids"]),
        "entry_sources": sorted(f"{entry['id']}:{entry['sha256']}" for entry in record["entries"]),
        "related_slugs": sorted(record.get("related_slugs", [])),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
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
    frontmatter = render_frontmatter(
        {
            "id": f"concept-{record['slug']}",
            "kind": "concept",
            "status": "compiled",
            "title": record["title"],
            "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
            "source_signature": record["source_signature"],
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
        "## Maintenance Notes",
        "- Promote stable findings here instead of repeating the same synthesis across source pages.",
        "- Keep contradictions and missing evidence explicit.",
    ]
    return "\n".join(lines) + "\n"


def render_sources_index(entries: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# Sources Index",
        "",
        f"- Last compiled at: `{compiled_at}`",
        f"- Total sources: `{len(entries)}`",
        "",
        "## Sources",
    ]
    if not entries:
        lines.append("- No sources registered yet.")
    else:
        for entry in entries:
            lines.append(
                f"- [{entry['title']}](../sources/{entry['id']}.md) "
                f"({entry['kind']}, {entry['source_type']})"
            )
    return "\n".join(lines) + "\n"


def render_concepts_index(concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# Concepts Index",
        "",
        f"- Last compiled at: `{compiled_at}`",
        f"- Total concept pages: `{len(concepts)}`",
        "",
        "## Concepts",
    ]
    if not concepts:
        lines.append("- No concept pages compiled yet.")
    else:
        for concept in concepts:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md) "
                f"({len(concept['entries'])} source(s))"
            )
    return "\n".join(lines) + "\n"


def render_compile_status(entries: list[dict[str, Any]], concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# Compile Status",
        "",
        f"- Last compiled at: `{compiled_at}`",
        f"- Source pages: `{len(entries)}`",
        f"- Concept pages: `{len(concepts)}`",
        "- Content index lives in `index.md`.",
        "- Runtime schema lives under `schema/`.",
        "- Operation log lives in `log.md`.",
        "- Machine memory summary lives in `machine-memory.md`.",
        "- Graph health lives in `graph-health.md`.",
        "- Drift report lives in `drift-report.md`.",
        "- Repair backlog lives in `repair-backlog.md`.",
        "- Derived pages are filed back explicitly via `aiwiki file-back`.",
        "- Lint findings land under `output/lint/`.",
    ]
    return "\n".join(lines) + "\n"


def render_master_index(entries: list[dict[str, Any]], concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# Wiki Index",
        "",
        f"- Last compiled at: `{compiled_at}`",
        f"- Sources: `{len(entries)}`",
        f"- Concepts: `{len(concepts)}`",
        "",
        "## Core Files",
        "- [Sources Index](./sources.md)",
        "- [Concepts Index](./concepts.md)",
        "- [Compile Status](./compile-status.md)",
        "- [Machine Memory](./machine-memory.md)",
        "- [Graph Health](./graph-health.md)",
        "- [Drift Report](./drift-report.md)",
        "- [Repair Backlog](./repair-backlog.md)",
        "- [Operation Log](./log.md)",
        "- [Runtime Schema](../../schema/index.md)",
        "",
        "## Recent Sources",
    ]
    if not entries:
        lines.append("- No sources registered yet.")
    else:
        for entry in sorted(entries, key=lambda item: item["imported_at"], reverse=True)[:8]:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md)")
    lines.extend(["", "## Top Concepts"])
    if not concepts:
        lines.append("- No concept pages compiled yet.")
    else:
        for concept in concepts[:10]:
            lines.append(f"- [{concept['title']}](../concepts/{concept['slug']}.md)")
    return "\n".join(lines) + "\n"


def ensure_wiki_log(root: Path) -> Path:
    ensure_layout(root)
    path = root / "wiki" / "indexes" / "log.md"
    if not path.exists():
        path.write_text("# Wiki Log\n\n", encoding="utf-8")
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


def machine_memory_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory.json"


def machine_memory_graph_path(root: Path) -> Path:
    return root / ".aiwiki" / "cache" / "machine-memory-graph.json"


def machine_memory_history_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "machine-memory-history.jsonl"


def machine_memory_drift_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "drift-report.md"


def graph_health_report_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "graph-health.md"


def repair_backlog_path(root: Path) -> Path:
    return root / "wiki" / "indexes" / "repair-backlog.md"


def nightly_health_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "nightly-health.json"


def load_json_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_machine_memory(root: Path) -> dict[str, Any]:
    memory = load_json_document(machine_memory_state_path(root))
    return memory if isinstance(memory, dict) else {}


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    term_index: dict[str, dict[str, set[str]]] = {}
    source_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    source_to_concept: list[dict[str, str]] = []
    concept_to_concept: list[dict[str, str]] = []
    citation_map: list[dict[str, Any]] = []

    def index_term(term: str, *, source_id: str | None = None, concept_slug: str | None = None) -> None:
        bucket = term_index.setdefault(term, {"source_ids": set(), "concept_slugs": set()})
        if source_id:
            bucket["source_ids"].add(source_id)
        if concept_slug:
            bucket["concept_slugs"].add(concept_slug)

    for entry in entries:
        concept_slugs = [concept_label_to_slug(label) for label in entry_terms.get(entry["id"], [])]
        source_page = f"wiki/sources/{entry['id']}.md"
        summary = source_summary_or_preview(root, entry, previews[entry["id"]])
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "source_type": entry["source_type"],
                "kind": entry["kind"],
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
                "source_page": source_page,
                "concept_slugs": concept_slugs,
            }
        )
        citation_map.append(
            {
                "source_page": source_page,
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
            }
        )
        for slug in concept_slugs:
            source_to_concept.append({"source_id": entry["id"], "concept_slug": slug})
        for token in tokenize(f"{entry['title']}\n{summary}"):
            index_term(token, source_id=entry["id"])

    for record in concepts:
        concept_nodes.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
                "related_slugs": record.get("related_slugs", []),
                "source_signature": record["source_signature"],
            }
        )
        for related_slug in record.get("related_slugs", []):
            concept_to_concept.append({"from": record["slug"], "to": related_slug})
        for token in tokenize(record["title"]):
            index_term(token, concept_slug=record["slug"])

    drift = {
        "missing_raw_files": [
            entry["stored_path"] for entry in entries if not (root / entry["stored_path"]).exists()
        ],
        "missing_source_pages": [
            f"wiki/sources/{entry['id']}.md"
            for entry in entries
            if not (root / "wiki" / "sources" / f"{entry['id']}.md").exists()
        ],
        "missing_concept_pages": [
            f"wiki/concepts/{record['slug']}.md"
            for record in concepts
            if not (root / "wiki" / "concepts" / f"{record['slug']}.md").exists()
        ],
        "sources_without_concepts": [entry["id"] for entry in entries if not entry_terms.get(entry["id"])],
    }

    return {
        "version": 1,
        "compiled_at": compiled_at,
        "source_nodes": sorted(source_nodes, key=lambda item: item["id"]),
        "concept_nodes": sorted(concept_nodes, key=lambda item: item["slug"]),
        "edges": {
            "source_to_concept": sorted(source_to_concept, key=lambda item: (item["source_id"], item["concept_slug"])),
            "concept_to_concept": sorted(concept_to_concept, key=lambda item: (item["from"], item["to"])),
        },
        "citation_map": sorted(citation_map, key=lambda item: item["source_page"]),
        "term_index": {
            term: {
                "source_ids": sorted(payload["source_ids"]),
                "concept_slugs": sorted(payload["concept_slugs"]),
            }
            for term, payload in sorted(term_index.items())
        },
        "drift": drift,
    }


def build_machine_memory_health(memory: dict[str, Any]) -> dict[str, Any]:
    source_nodes = memory.get("source_nodes", [])
    concept_nodes = memory.get("concept_nodes", [])
    edges = memory.get("edges", {})

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    concept_related: dict[str, set[str]] = {}

    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        concept_related.setdefault(left, set()).add(right)
        concept_related.setdefault(right, set()).add(left)

    isolated_source_ids = sorted(node["id"] for node in source_nodes if not source_to_concepts.get(node["id"]))
    singleton_concept_slugs = sorted(
        node["slug"]
        for node in concept_nodes
        if len(concept_to_sources.get(node["slug"], set())) <= 1 and not concept_related.get(node["slug"])
    )
    bridge_concept_slugs = [
        node["slug"]
        for node in sorted(
            concept_nodes,
            key=lambda item: (
                -len(concept_to_sources.get(item["slug"], set())),
                -len(concept_related.get(item["slug"], set())),
                item["title"].lower(),
            ),
        )
        if len(concept_to_sources.get(node["slug"], set())) >= 2 and concept_related.get(node["slug"])
    ]
    overloaded_concept_slugs = sorted(
        node["slug"] for node in concept_nodes if len(concept_to_sources.get(node["slug"], set())) >= 4
    )

    adjacency = build_machine_memory_adjacency(memory)

    visited: set[str] = set()
    component_sizes: list[int] = []
    component_records: list[dict[str, Any]] = []
    for node_key in sorted(adjacency):
        if node_key in visited:
            continue
        stack = [node_key]
        members: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            members.add(current)
            stack.extend(sorted(set(adjacency.get(current, {})) - visited))
        component_sizes.append(len(members))
        source_ids = sorted(member.removeprefix("source:") for member in members if member.startswith("source:"))
        concept_slugs = sorted(member.removeprefix("concept:") for member in members if member.startswith("concept:"))
        component_records.append(
            {
                "source_ids": source_ids,
                "concept_slugs": concept_slugs,
                "size": len(members),
                "sort_key": (
                    -len(members),
                    source_ids[0] if source_ids else "~",
                    concept_slugs[0] if concept_slugs else "~",
                ),
            }
        )
    component_sizes.sort(reverse=True)
    component_records.sort(key=lambda item: item["sort_key"])
    components: list[dict[str, Any]] = []
    source_component_ids: dict[str, str] = {}
    concept_component_ids: dict[str, str] = {}
    for index, record in enumerate(component_records, start=1):
        component_id = f"component-{index}"
        components.append(
            {
                "id": component_id,
                "size": record["size"],
                "source_ids": record["source_ids"],
                "concept_slugs": record["concept_slugs"],
            }
        )
        for source_id in record["source_ids"]:
            source_component_ids[source_id] = component_id
        for concept_slug in record["concept_slugs"]:
            concept_component_ids[concept_slug] = component_id

    return {
        "isolated_source_ids": isolated_source_ids,
        "singleton_concept_slugs": singleton_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs[:10],
        "overloaded_concept_slugs": overloaded_concept_slugs,
        "component_count": len(component_sizes),
        "component_sizes": component_sizes,
        "components": components,
        "source_component_ids": source_component_ids,
        "concept_component_ids": concept_component_ids,
    }


def machine_memory_digest(memory: dict[str, Any]) -> str:
    payload = {
        "source_nodes": memory.get("source_nodes", []),
        "concept_nodes": memory.get("concept_nodes", []),
        "edges": memory.get("edges", {}),
        "citation_map": memory.get("citation_map", []),
        "term_index": memory.get("term_index", {}),
        "drift": memory.get("drift", {}),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def build_machine_memory_graph(memory: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for node in memory.get("source_nodes", []):
        nodes.append(
            {
                "id": f"source:{node['id']}",
                "kind": "source",
                "title": node["title"],
                "source_type": node["source_type"],
                "source_page": node["source_page"],
                "stored_path": node["stored_path"],
            }
        )
    for node in memory.get("concept_nodes", []):
        nodes.append(
            {
                "id": f"concept:{node['slug']}",
                "kind": "concept",
                "title": node["title"],
                "source_pages": node["source_pages"],
            }
        )
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        edges.append(
            {
                "source": f"source:{edge['source_id']}",
                "target": f"concept:{edge['concept_slug']}",
                "type": "HAS_CONCEPT",
            }
        )
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        edges.append(
            {
                "source": f"concept:{edge['from']}",
                "target": f"concept:{edge['to']}",
                "type": "RELATED_CONCEPT",
            }
        )
    graph = {
        "version": 1,
        "compiled_at": memory["compiled_at"],
        "nodes": sorted(nodes, key=lambda item: (item["kind"], item["id"])),
        "edges": sorted(edges, key=lambda item: (item["type"], item["source"], item["target"])),
    }
    graph["digest"] = sha256_bytes(json.dumps({"nodes": graph["nodes"], "edges": graph["edges"]}, sort_keys=True).encode("utf-8"))
    return graph


def build_machine_memory_adjacency(memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    adjacency: dict[str, dict[str, str]] = {}
    for node in memory.get("source_nodes", []):
        adjacency.setdefault(f"source:{node['id']}", {})
    for node in memory.get("concept_nodes", []):
        adjacency.setdefault(f"concept:{node['slug']}", {})
    for edge in memory.get("edges", {}).get("source_to_concept", []):
        source_key = f"source:{edge['source_id']}"
        concept_key = f"concept:{edge['concept_slug']}"
        adjacency.setdefault(source_key, {})[concept_key] = "HAS_CONCEPT"
        adjacency.setdefault(concept_key, {})[source_key] = "HAS_CONCEPT"
    for edge in memory.get("edges", {}).get("concept_to_concept", []):
        left_key = f"concept:{edge['from']}"
        right_key = f"concept:{edge['to']}"
        adjacency.setdefault(left_key, {})[right_key] = "RELATED_CONCEPT"
        adjacency.setdefault(right_key, {})[left_key] = "RELATED_CONCEPT"
    return adjacency


def build_machine_memory_query(memory: dict[str, Any], question: str) -> dict[str, Any]:
    term_index = memory.get("term_index", {})
    edges = memory.get("edges", {})
    source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    question_tokens = tokenize(question)
    health = memory.get("health", {})
    adjacency = build_machine_memory_adjacency(memory)

    direct_source_scores: dict[str, int] = {}
    direct_concept_scores: dict[str, int] = {}
    matched_terms: list[str] = []

    source_to_concepts: dict[str, set[str]] = {}
    concept_to_sources: dict[str, set[str]] = {}
    for edge in edges.get("source_to_concept", []):
        source_id = edge.get("source_id")
        concept_slug = edge.get("concept_slug")
        if not isinstance(source_id, str) or not isinstance(concept_slug, str):
            continue
        source_to_concepts.setdefault(source_id, set()).add(concept_slug)
        concept_to_sources.setdefault(concept_slug, set()).add(source_id)

    related_concepts: dict[str, set[str]] = {}
    for edge in edges.get("concept_to_concept", []):
        left = edge.get("from")
        right = edge.get("to")
        if not isinstance(left, str) or not isinstance(right, str):
            continue
        related_concepts.setdefault(left, set()).add(right)
        related_concepts.setdefault(right, set()).add(left)

    for token in question_tokens:
        payload = term_index.get(token)
        if not isinstance(payload, dict):
            continue
        matched_terms.append(token)
        for source_id in payload.get("source_ids", []):
            if source_id in source_nodes:
                direct_source_scores[source_id] = direct_source_scores.get(source_id, 0) + 3
        for concept_slug in payload.get("concept_slugs", []):
            if concept_slug in concept_nodes:
                direct_concept_scores[concept_slug] = direct_concept_scores.get(concept_slug, 0) + 4

    expanded_source_scores = dict(direct_source_scores)
    expanded_concept_scores = dict(direct_concept_scores)
    supporting_edges: set[tuple[str, str, str]] = set()

    for source_id in list(direct_source_scores):
        for concept_slug in sorted(source_to_concepts.get(source_id, set())):
            expanded_concept_scores[concept_slug] = expanded_concept_scores.get(concept_slug, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))

    for concept_slug in list(direct_concept_scores):
        for source_id in sorted(concept_to_sources.get(concept_slug, set())):
            expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 2
            supporting_edges.add(("HAS_CONCEPT", source_id, concept_slug))
        for related_slug in sorted(related_concepts.get(concept_slug, set())):
            expanded_concept_scores[related_slug] = expanded_concept_scores.get(related_slug, 0) + 1
            supporting_edges.add(("RELATED_CONCEPT", concept_slug, related_slug))
            for source_id in sorted(concept_to_sources.get(related_slug, set())):
                expanded_source_scores[source_id] = expanded_source_scores.get(source_id, 0) + 1
                supporting_edges.add(("HAS_CONCEPT", source_id, related_slug))

    query_routes = build_machine_memory_query_routes(
        memory,
        adjacency,
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    for route in query_routes:
        for node in route["nodes"]:
            if node["kind"] == "source":
                expanded_source_scores[node["id"]] = expanded_source_scores.get(node["id"], 0) + 2
            else:
                expanded_concept_scores[node["slug"]] = expanded_concept_scores.get(node["slug"], 0) + 2
        for edge in route["edges"]:
            if edge["type"] == "HAS_CONCEPT":
                supporting_edges.add(("HAS_CONCEPT", edge["left"], edge["right"]))
            elif edge["type"] == "RELATED_CONCEPT":
                supporting_edges.add(("RELATED_CONCEPT", edge["left"], edge["right"]))

    ranked_source_ids = [
        source_id
        for source_id, _score in sorted(
            expanded_source_scores.items(),
            key=lambda item: (-item[1], source_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    ranked_concept_slugs = [
        concept_slug
        for concept_slug, _score in sorted(
            expanded_concept_scores.items(),
            key=lambda item: (-item[1], concept_nodes.get(item[0], {}).get("title", item[0]).lower()),
        )[:8]
    ]
    bridge_concept_slugs = [
        slug for slug in ranked_concept_slugs if slug in set(health.get("bridge_concept_slugs", []))
    ]
    query_subgraph_sources = [
        {
            "id": source_id,
            "title": source_nodes[source_id]["title"],
            "path": source_nodes[source_id]["source_page"],
        }
        for source_id in ranked_source_ids
        if source_id in source_nodes
    ]
    query_subgraph_concepts = [
        {
            "slug": concept_slug,
            "title": concept_nodes[concept_slug]["title"],
            "path": f"wiki/concepts/{concept_slug}.md",
        }
        for concept_slug in ranked_concept_slugs
        if concept_slug in concept_nodes
    ]
    query_subgraph_edges = [
        {"type": edge_type, "left": left, "right": right}
        for edge_type, left, right in sorted(supporting_edges)
        if (edge_type == "HAS_CONCEPT" and left in ranked_source_ids and right in ranked_concept_slugs)
        or (edge_type == "RELATED_CONCEPT" and left in ranked_concept_slugs and right in ranked_concept_slugs)
    ]
    touched_component_ids = sorted(
        {
            component_id
            for component_id in (
                [health.get("source_component_ids", {}).get(source_id) for source_id in ranked_source_ids]
                + [health.get("concept_component_ids", {}).get(slug) for slug in ranked_concept_slugs]
            )
            if component_id
        }
    )
    touched_components = [
        component
        for component in health.get("components", [])
        if component.get("id") in touched_component_ids
    ]

    return {
        "matched_terms": matched_terms,
        "direct_source_ids": sorted(direct_source_scores),
        "direct_concept_slugs": sorted(direct_concept_scores),
        "ranked_source_ids": ranked_source_ids,
        "ranked_concept_slugs": ranked_concept_slugs,
        "bridge_concept_slugs": bridge_concept_slugs,
        "supporting_edges": [
            {"type": edge_type, "left": left, "right": right}
            for edge_type, left, right in sorted(supporting_edges)
        ],
        "query_routes": query_routes,
        "touched_component_ids": touched_component_ids,
        "touched_components": touched_components,
        "query_subgraph": {
            "sources": query_subgraph_sources,
            "concepts": query_subgraph_concepts,
            "edges": query_subgraph_edges,
        },
    }


def build_machine_memory_query_routes(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[dict[str, Any]]:
    anchor_nodes = ranked_machine_memory_anchor_nodes(
        direct_source_scores,
        direct_concept_scores,
        expanded_source_scores,
        expanded_concept_scores,
    )
    routes: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, ...]] = set()
    for index, start in enumerate(anchor_nodes):
        for goal in anchor_nodes[index + 1 :]:
            path = shortest_machine_memory_path(adjacency, start, goal)
            if len(path) < 2:
                continue
            route_key = tuple(path)
            if route_key in seen_routes:
                continue
            seen_routes.add(route_key)
            routes.append(render_machine_memory_route(memory, adjacency, path))
            if len(routes) >= 4:
                return routes
    return routes


def ranked_machine_memory_anchor_nodes(
    direct_source_scores: dict[str, int],
    direct_concept_scores: dict[str, int],
    expanded_source_scores: dict[str, int],
    expanded_concept_scores: dict[str, int],
) -> list[str]:
    anchors: list[str] = []
    for concept_slug, _score in sorted(direct_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
        anchors.append(f"concept:{concept_slug}")
    for source_id, _score in sorted(direct_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
        anchors.append(f"source:{source_id}")
    if len(anchors) < 2:
        for concept_slug, _score in sorted(expanded_concept_scores.items(), key=lambda item: (-item[1], item[0]))[:4]:
            key = f"concept:{concept_slug}"
            if key not in anchors:
                anchors.append(key)
        for source_id, _score in sorted(expanded_source_scores.items(), key=lambda item: (-item[1], item[0]))[:3]:
            key = f"source:{source_id}"
            if key not in anchors:
                anchors.append(key)
    return anchors[:4]


def shortest_machine_memory_path(adjacency: dict[str, dict[str, str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    if start not in adjacency or goal not in adjacency:
        return []
    queue: deque[str] = deque([start])
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency.get(current, {})):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parents:
        return []
    path: list[str] = []
    current: str | None = goal
    while current is not None:
        path.append(current)
        current = parents[current]
    return list(reversed(path))


def render_machine_memory_route(
    memory: dict[str, Any],
    adjacency: dict[str, dict[str, str]],
    path: list[str],
) -> dict[str, Any]:
    nodes = [machine_memory_node_metadata(memory, node_key) for node_key in path]
    edges: list[dict[str, str]] = []
    for left, right in zip(path, path[1:]):
        edge_type = adjacency.get(left, {}).get(right, "")
        if edge_type == "HAS_CONCEPT":
            if left.startswith("source:"):
                edges.append(
                    {
                        "type": edge_type,
                        "left": left.removeprefix("source:"),
                        "right": right.removeprefix("concept:"),
                    }
                )
            else:
                edges.append(
                    {
                        "type": edge_type,
                        "left": right.removeprefix("source:"),
                        "right": left.removeprefix("concept:"),
                    }
                )
        else:
            edges.append(
                {
                    "type": "RELATED_CONCEPT",
                    "left": left.removeprefix("concept:"),
                    "right": right.removeprefix("concept:"),
                }
            )
    return {
        "start": nodes[0],
        "goal": nodes[-1],
        "length": max(0, len(path) - 1),
        "nodes": nodes,
        "edges": edges,
    }


def machine_memory_node_metadata(memory: dict[str, Any], node_key: str) -> dict[str, Any]:
    if node_key.startswith("source:"):
        source_id = node_key.removeprefix("source:")
        source_nodes = {node["id"]: node for node in memory.get("source_nodes", [])}
        node = source_nodes.get(source_id, {})
        return {
            "kind": "source",
            "id": source_id,
            "title": node.get("title", source_id),
            "path": node.get("source_page", f"wiki/sources/{source_id}.md"),
        }
    concept_slug = node_key.removeprefix("concept:")
    concept_nodes = {node["slug"]: node for node in memory.get("concept_nodes", [])}
    node = concept_nodes.get(concept_slug, {})
    return {
        "kind": "concept",
        "slug": concept_slug,
        "title": node.get("title", concept_slug),
        "path": f"wiki/concepts/{concept_slug}.md",
    }


def summarize_machine_memory_transition(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_source_ids = {node["id"] for node in previous.get("source_nodes", [])}
    current_source_ids = {node["id"] for node in current.get("source_nodes", [])}
    previous_concept_slugs = {node["slug"] for node in previous.get("concept_nodes", [])}
    current_concept_slugs = {node["slug"] for node in current.get("concept_nodes", [])}
    previous_terms = set(previous.get("term_index", {}).keys())
    current_terms = set(current.get("term_index", {}).keys())
    previous_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in previous.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in previous.get("edges", {}).get("concept_to_concept", [])
    }
    current_edges = {
        ("HAS_CONCEPT", edge["source_id"], edge["concept_slug"])
        for edge in current.get("edges", {}).get("source_to_concept", [])
    } | {
        ("RELATED_CONCEPT", edge["from"], edge["to"])
        for edge in current.get("edges", {}).get("concept_to_concept", [])
    }
    previous_digest = previous.get("digest", "")
    current_digest = current["digest"]
    return {
        "has_previous_snapshot": bool(previous_digest),
        "changed": previous_digest != current_digest,
        "previous_digest": previous_digest,
        "current_digest": current_digest,
        "added_source_ids": sorted(current_source_ids - previous_source_ids),
        "removed_source_ids": sorted(previous_source_ids - current_source_ids),
        "added_concept_slugs": sorted(current_concept_slugs - previous_concept_slugs),
        "removed_concept_slugs": sorted(previous_concept_slugs - current_concept_slugs),
        "added_terms": sorted(current_terms - previous_terms)[:25],
        "removed_terms": sorted(previous_terms - current_terms)[:25],
        "added_edges": len(current_edges - previous_edges),
        "removed_edges": len(previous_edges - current_edges),
    }


def append_machine_memory_history(root: Path, memory: dict[str, Any], transition: dict[str, Any]) -> None:
    path = machine_memory_history_path(root)
    if transition["has_previous_snapshot"] and not transition["changed"]:
        return
    entry = {
        "compiled_at": memory["compiled_at"],
        "digest": memory["digest"],
        "sources": len(memory.get("source_nodes", [])),
        "concepts": len(memory.get("concept_nodes", [])),
        "terms": len(memory.get("term_index", {})),
        "added_source_ids": transition["added_source_ids"],
        "removed_source_ids": transition["removed_source_ids"],
        "added_concept_slugs": transition["added_concept_slugs"],
        "removed_concept_slugs": transition["removed_concept_slugs"],
        "added_edges": transition["added_edges"],
        "removed_edges": transition["removed_edges"],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def render_drift_report(memory: dict[str, Any], transition: dict[str, Any]) -> str:
    drift = memory["drift"]
    lines = [
        "# Drift Report",
        "",
        f"- Compiled at: `{memory['compiled_at']}`",
        f"- Current digest: `{memory['digest']}`",
        f"- Graph digest: `{memory['graph_digest']}`",
        "",
        "## Transition Summary",
    ]
    if not transition["has_previous_snapshot"]:
        lines.append("- No previous machine-memory snapshot was available.")
    elif not transition["changed"]:
        lines.append("- No structural drift detected since the previous snapshot.")
    else:
        lines.extend(
            [
                f"- Previous digest: `{transition['previous_digest']}`",
                f"- Added source nodes: `{len(transition['added_source_ids'])}`",
                f"- Removed source nodes: `{len(transition['removed_source_ids'])}`",
                f"- Added concept nodes: `{len(transition['added_concept_slugs'])}`",
                f"- Removed concept nodes: `{len(transition['removed_concept_slugs'])}`",
                f"- Added edges: `{transition['added_edges']}`",
                f"- Removed edges: `{transition['removed_edges']}`",
                f"- Added indexed terms (sample): `{', '.join(transition['added_terms']) or 'none'}`",
                f"- Removed indexed terms (sample): `{', '.join(transition['removed_terms']) or 'none'}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Current Drift Checks",
            f"- Missing raw files: `{len(drift['missing_raw_files'])}`",
            f"- Missing source pages: `{len(drift['missing_source_pages'])}`",
            f"- Missing concept pages: `{len(drift['missing_concept_pages'])}`",
            f"- Sources without concepts: `{len(drift['sources_without_concepts'])}`",
            "",
            "## Machine Memory Artifacts",
            "- State: `.aiwiki/state/machine-memory.json`",
            "- Graph export: `.aiwiki/cache/machine-memory-graph.json`",
            "- History: `.aiwiki/state/machine-memory-history.jsonl`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_graph_health(memory: dict[str, Any]) -> str:
    health = memory.get("health", {})
    lines = [
        "# Graph Health",
        "",
        f"- Compiled at: `{memory['compiled_at']}`",
        f"- Connected components: `{health.get('component_count', 0)}`",
        f"- Component sizes: `{', '.join(str(size) for size in health.get('component_sizes', [])) or 'none'}`",
        f"- Isolated sources: `{len(health.get('isolated_source_ids', []))}`",
        f"- Singleton concepts: `{len(health.get('singleton_concept_slugs', []))}`",
        f"- Bridge concepts: `{len(health.get('bridge_concept_slugs', []))}`",
        f"- Overloaded concepts: `{len(health.get('overloaded_concept_slugs', []))}`",
        "",
        "## Repair Signals",
        f"- Isolated sources: `{', '.join(health.get('isolated_source_ids', [])[:10]) or 'none'}`",
        f"- Singleton concepts: `{', '.join(health.get('singleton_concept_slugs', [])[:10]) or 'none'}`",
        f"- Bridge concepts: `{', '.join(health.get('bridge_concept_slugs', [])[:10]) or 'none'}`",
        f"- Overloaded concepts: `{', '.join(health.get('overloaded_concept_slugs', [])[:10]) or 'none'}`",
        "",
        "## Largest Components",
    ]
    components = health.get("components", [])
    if not components:
        lines.append("- No component data available yet.")
    else:
        for component in components[:5]:
            lines.append(
                f"- `{component['id']}` size `{component['size']}`"
                f" | sources `{', '.join(component.get('source_ids', [])[:4]) or 'none'}`"
                f" | concepts `{', '.join(component.get('concept_slugs', [])[:4]) or 'none'}`"
            )
    lines.extend(
        [
            "",
        "## Links",
        "- [Machine Memory](./machine-memory.md)",
        "- [Drift Report](./drift-report.md)",
        "- [Repair Backlog](./repair-backlog.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_machine_memory_index(memory: dict[str, Any]) -> str:
    concept_nodes = memory["concept_nodes"]
    edges = memory["edges"]
    drift = memory["drift"]
    health = memory.get("health", {})
    lines = [
        "# Machine Memory",
        "",
        f"- Last compiled at: `{memory['compiled_at']}`",
        "- Runtime state file: `.aiwiki/state/machine-memory.json`",
        "- Graph export: `.aiwiki/cache/machine-memory-graph.json`",
        "- Drift report: `wiki/indexes/drift-report.md`",
        f"- Source nodes: `{len(memory['source_nodes'])}`",
        f"- Concept nodes: `{len(concept_nodes)}`",
        f"- Source-to-concept edges: `{len(edges['source_to_concept'])}`",
        f"- Concept-to-concept edges: `{len(edges['concept_to_concept'])}`",
        f"- Indexed terms: `{len(memory['term_index'])}`",
        f"- Machine digest: `{memory['digest']}`",
        f"- Graph digest: `{memory['graph_digest']}`",
        "",
        "## Graph Health",
        f"- Connected components: `{health.get('component_count', 0)}`",
        f"- Isolated sources: `{len(health.get('isolated_source_ids', []))}`",
        f"- Singleton concepts: `{len(health.get('singleton_concept_slugs', []))}`",
        f"- Bridge concepts: `{len(health.get('bridge_concept_slugs', []))}`",
        f"- Overloaded concepts: `{len(health.get('overloaded_concept_slugs', []))}`",
        f"- Indexed components: `{len(health.get('components', []))}`",
        "",
        "## Drift Summary",
        f"- Missing raw files: `{len(drift['missing_raw_files'])}`",
        f"- Missing source pages: `{len(drift['missing_source_pages'])}`",
        f"- Missing concept pages: `{len(drift['missing_concept_pages'])}`",
        f"- Sources without concepts: `{len(drift['sources_without_concepts'])}`",
        "",
        "## Links",
        "- [Graph Health](./graph-health.md)",
        "- [Drift Report](./drift-report.md)",
        "- [Repair Backlog](./repair-backlog.md)",
        "",
        "## Query Acceleration",
        "- `ask` and `run-ask` use the machine-memory term index as a first-pass query planner.",
        "- Source-to-concept and concept-to-concept edges expand related candidates before prompt assembly.",
        "- Query planning also extracts shortest graph routes and touched components for deeper retrieval.",
        "- The graph export is for agent/tool consumption, not for direct human editing.",
        "",
        "## Top Concepts",
    ]
    if not concept_nodes:
        lines.append("- No concept nodes compiled yet.")
    else:
        for node in sorted(
            concept_nodes,
            key=lambda item: (-len(item["source_pages"]), item["title"].lower()),
        )[:10]:
            lines.append(
                f"- [{node['title']}](../concepts/{node['slug']}.md) "
                f"({len(node['source_pages'])} source(s), {len(node['related_slugs'])} related concept(s))"
            )
    lines.extend(
        [
            "",
            "## Runtime Schema",
            "- [Schema Index](../../schema/index.md)",
            "- [Citation Rules](../../schema/citations.md)",
            "- [Conflict Rules](../../schema/conflicts.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def compile_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    compiled_at = utc_now()
    previous_memory = load_json_document(machine_memory_state_path(root))
    changed_pages = 0
    previews: dict[str, str] = {}
    existing_pages: dict[str, str] = {}
    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file)
        previews[entry["id"]] = preview
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        existing_pages[entry["id"]] = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
    concepts, entry_terms = build_concept_records(root, entries, previews)
    for entry in entries:
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        content = render_source_page_with_state(
            entry,
            previews[entry["id"]],
            compiled_at,
            concepts=entry_terms.get(entry["id"], []),
            existing_page=existing_pages[entry["id"]],
        )
        changed_pages += int(write_if_changed(destination, content))

    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "sources.md", render_sources_index(entries, compiled_at))
    )
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "concepts.md", render_concepts_index(concepts, compiled_at))
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(entries, concepts, compiled_at),
        )
    )
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "index.md", render_master_index(entries, concepts, compiled_at))
    )
    ensure_wiki_log(root)

    concept_lookup = {record["slug"]: record for record in concepts}
    for record in concepts:
        record["record_lookup"] = concept_lookup
        destination = root / "wiki" / "concepts" / f"{record['slug']}.md"
        existing_page = destination.read_text(encoding="utf-8", errors="replace") if destination.exists() else ""
        changed_pages += int(write_if_changed(destination, render_concept_page(record, compiled_at, existing_page)))

    removed_pages = remove_stale_generated_concept_pages(root, {record["slug"] for record in concepts})
    memory = build_machine_memory(root, entries, concepts, previews, entry_terms, compiled_at)
    memory["health"] = build_machine_memory_health(memory)
    memory["digest"] = machine_memory_digest(memory)
    graph = build_machine_memory_graph(memory)
    memory["graph_digest"] = graph["digest"]
    memory["graph_path"] = relative_path(root, machine_memory_graph_path(root))
    memory["history_path"] = relative_path(root, machine_memory_history_path(root))
    transition = summarize_machine_memory_transition(previous_memory, memory)
    memory["transition"] = transition
    changed_pages += int(
        write_if_changed(machine_memory_state_path(root), json.dumps(memory, indent=2, sort_keys=True) + "\n")
    )
    changed_pages += int(write_if_changed(machine_memory_graph_path(root), json.dumps(graph, indent=2, sort_keys=True) + "\n"))
    append_machine_memory_history(root, memory, transition)
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "machine-memory.md", render_machine_memory_index(memory))
    )
    changed_pages += int(write_if_changed(graph_health_report_path(root), render_graph_health(memory)))
    changed_pages += int(write_if_changed(machine_memory_drift_report_path(root), render_drift_report(memory, transition)))
    append_wiki_log(
        root,
        "compile",
        "wiki refresh",
        [
            f"compiled_at: `{compiled_at}`",
            f"source_pages: `{len(entries)}`",
            f"concept_pages: `{len(concepts)}`",
            f"machine_memory_terms: `{len(memory['term_index'])}`",
            f"graph_components: `{memory['health']['component_count']}`",
            f"machine_memory_changed: `{transition['changed']}`",
            f"changed_pages: `{changed_pages}`",
            f"removed_concept_pages: `{removed_pages}`",
        ],
    )

    return {
        "compiled_at": compiled_at,
        "sources": len(entries),
        "concepts": len(concepts),
        "machine_memory_terms": len(memory["term_index"]),
        "machine_memory_changed": transition["changed"],
        "changed_pages": changed_pages,
    }


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def rank_concepts(root: Path, question: str, boost_concept_slugs: set[str] | None = None) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    boost_concept_slugs = boost_concept_slugs or set()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for path in sorted((root / "wiki" / "concepts").glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        title = frontmatter.get("title") or path.stem
        haystack = f"{title}\n{strip_frontmatter(content)}".lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        if path.stem in boost_concept_slugs:
            score += 5
        if score:
            ranked.append(
                (
                    score,
                    {
                        "slug": path.stem,
                        "title": str(title),
                        "path": relative_path(root, path),
                        "source_pages": frontmatter.get("source_pages", []),
                    },
                )
            )
    ranked.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [item for _score, item in ranked[:5]]


def source_page_is_stale(root: Path, entry: dict[str, Any]) -> bool:
    page = root / "wiki" / "sources" / f"{entry['id']}.md"
    if not page.exists():
        return True
    return compiled_source_sha(page.read_text(encoding="utf-8", errors="replace")) != entry["sha256"]


def wiki_requires_compile(root: Path, entries: list[dict[str, Any]]) -> bool:
    if not entries:
        return False
    if not (root / "wiki" / "indexes" / "index.md").exists():
        return True
    if any(source_page_is_stale(root, entry) for entry in entries):
        return True
    concept_dir = root / "wiki" / "concepts"
    return not any(concept_dir.glob("*.md"))


def rank_sources(
    root: Path,
    entries: list[dict[str, Any]],
    question: str,
    boost_source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    boost_source_ids = boost_source_ids or set()
    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file, limit_lines=8)
        summary_or_preview = source_summary_or_preview(root, entry, preview)
        haystack = " ".join([entry["title"], summary_or_preview]).lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        for concept in entry_concept_terms(entry, summary_or_preview, max_terms=4):
            for token in question_tokens:
                score += concept.lower().count(token)
        if entry["id"] in boost_source_ids:
            score += 5
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [entry for _score, entry in scored[:5]]


def render_report(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "report",
            "query": question,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# {question}",
        "",
        "## Answer Contract",
        "- Ground every non-trivial claim in `wiki/sources/*.md`.",
        "- Call out uncertainty instead of filling gaps.",
        "- Prefer file-path citations over vague prose references.",
        "",
        "## Recommended Index Pages",
        "- [Wiki Index](../../wiki/indexes/index.md)",
        "- [Sources Index](../../wiki/indexes/sources.md)",
        "- [Concepts Index](../../wiki/indexes/concepts.md)",
        "- [Machine Memory](../../wiki/indexes/machine-memory.md)",
        "- [Graph Health](../../wiki/indexes/graph-health.md)",
        "- [Drift Report](../../wiki/indexes/drift-report.md)",
        "- [Repair Backlog](../../wiki/indexes/repair-backlog.md)",
        "- [Runtime Schema](../../schema/index.md)",
        "",
        "## Machine Memory Query Plan",
    ]
    matched_terms = machine_query.get("matched_terms", [])
    if matched_terms:
        lines.append(f"- Matched terms: `{', '.join(matched_terms)}`")
    else:
        lines.append("- No direct machine-memory term hits were available yet.")
    lines.append(
        f"- Boosted source candidates: `{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`"
    )
    lines.append(
        f"- Boosted concept candidates: `{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`"
    )
    lines.append(
        f"- Bridge concepts: `{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`"
    )
    lines.append(
        f"- Query subgraph edges: `{len(machine_query.get('query_subgraph', {}).get('edges', []))}`"
    )
    lines.append(f"- Query routes: `{len(machine_query.get('query_routes', []))}`")
    lines.append(f"- Touched components: `{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`")
    lines.extend(
        [
            "",
        "## Recommended Concepts",
        ]
    )
    if not concepts:
        lines.append("- No ranked concept pages yet.")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
        "## Recommended Sources",
        ]
    )
    if not entries:
        lines.append("- No ranked sources yet. Run `aiwiki compile` after ingesting material.")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
            "## Draft Outline",
            "1. Restate the research question.",
            "2. Compare the strongest relevant sources.",
            "3. Note disagreements, missing evidence, and next questions.",
            "",
            "## Citations",
            "- Add source-page citations inline in the final answer.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_slides(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    lines = [
        "---",
        "marp: true",
        f"title: {render_scalar(question)}",
        f"description: {render_scalar(f'Generated at {created_at}')}",
        "---",
        "",
        f"# {question}",
        "",
        "## Use This Deck",
        "- Convert ranked source pages into 5-7 slides.",
        "- Keep citations on each content slide.",
        "",
        "## Ranked Indexes",
        "- `wiki/indexes/index.md`",
        "- `wiki/indexes/sources.md`",
        "- `wiki/indexes/concepts.md`",
        "- `wiki/indexes/machine-memory.md`",
        "- `wiki/indexes/graph-health.md`",
        "- `wiki/indexes/drift-report.md`",
        "- `wiki/indexes/repair-backlog.md`",
        "- `schema/index.md`",
        "",
        "## Machine Memory Query Plan",
        f"- Matched terms: `{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- Boosted sources: `{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- Boosted concepts: `{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- Bridge concepts: `{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- Query subgraph edges: `{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- Query routes: `{len(machine_query.get('query_routes', []))}`",
        f"- Touched components: `{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        "",
        "## Ranked Concepts",
    ]
    if not concepts:
        lines.append("- No ranked concept pages available yet.")
    else:
        for concept in concepts:
            lines.append(f"- `{concept['path']}`")
    lines.extend(
        [
            "",
        "## Ranked Sources",
        ]
    )
    if not entries:
        lines.append("- No ranked sources available yet.")
    else:
        for entry in entries:
            lines.append(f"- `wiki/sources/{entry['id']}.md`")
    lines.extend(
        [
            "",
            "---",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
            "# Findings",
            "",
            "- Replace this slide with grounded content.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_figure_brief(
    question: str,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    machine_query: dict[str, Any],
    created_at: str,
    artifact_id: str,
) -> str:
    frontmatter = render_frontmatter(
        {
            "id": artifact_id,
            "kind": "output",
            "format": "figure",
            "query": question,
            "generated_by": "aiwiki-ask",
            "created_at": created_at,
        }
    )
    lines = [
        frontmatter,
        "",
        f"# Figure Brief: {question}",
        "",
        "## Goal",
        "- Describe the figure the agent should produce.",
        "",
        "## Recommended Index Pages",
        "- [Wiki Index](../../wiki/indexes/index.md)",
        "- [Sources Index](../../wiki/indexes/sources.md)",
        "- [Concepts Index](../../wiki/indexes/concepts.md)",
        "- [Machine Memory](../../wiki/indexes/machine-memory.md)",
        "- [Graph Health](../../wiki/indexes/graph-health.md)",
        "- [Drift Report](../../wiki/indexes/drift-report.md)",
        "- [Repair Backlog](../../wiki/indexes/repair-backlog.md)",
        "- [Runtime Schema](../../schema/index.md)",
        "",
        "## Machine Memory Query Plan",
        f"- Matched terms: `{', '.join(machine_query.get('matched_terms', [])) or 'none'}`",
        f"- Boosted sources: `{', '.join(machine_query.get('ranked_source_ids', [])) or 'none'}`",
        f"- Boosted concepts: `{', '.join(machine_query.get('ranked_concept_slugs', [])) or 'none'}`",
        f"- Bridge concepts: `{', '.join(machine_query.get('bridge_concept_slugs', [])) or 'none'}`",
        f"- Query subgraph edges: `{len(machine_query.get('query_subgraph', {}).get('edges', []))}`",
        f"- Query routes: `{len(machine_query.get('query_routes', []))}`",
        f"- Touched components: `{', '.join(machine_query.get('touched_component_ids', [])) or 'none'}`",
        "",
        "## Recommended Concepts",
    ]
    if not concepts:
        lines.append("- No ranked concept pages available yet.")
    else:
        for concept in concepts:
            lines.append(f"- [{concept['title']}](../../{concept['path']})")
    lines.extend(
        [
            "",
        "## Recommended Sources",
        ]
    )
    if not entries:
        lines.append("- No ranked sources available yet.")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../../wiki/sources/{entry['id']}.md)")
    lines.extend(
        [
            "",
            "## Figure Requirements",
            "- State the intended chart type.",
            "- List the variables or comparison axes.",
            "- Include source-page citations in the caption.",
            "",
            f"<!-- artifact_id: {artifact_id} -->",
        ]
    )
    return "\n".join(lines) + "\n"


def ask_question(root: Path, question: str, output_format: str) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    if wiki_requires_compile(root, entries):
        compile_wiki(root)
        manifest = load_manifest(root)
        entries = manifest["entries"]
    machine_query = build_machine_memory_query(load_machine_memory(root), question)
    ranked_concepts = rank_concepts(root, question, boost_concept_slugs=set(machine_query["ranked_concept_slugs"]))
    boosted_ids: set[str] = set(machine_query["ranked_source_ids"])
    for concept in ranked_concepts:
        for source_page in concept.get("source_pages", []):
            if isinstance(source_page, str) and source_page.startswith("wiki/sources/") and source_page.endswith(".md"):
                boosted_ids.add(Path(source_page).stem)
    ranked = rank_sources(root, entries, question, boost_source_ids=boosted_ids)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_id = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        destination = root / "output" / "reports" / f"{artifact_id}.md"
        content = render_report(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    elif output_format == "slides":
        destination = root / "output" / "slides" / f"{artifact_id}.md"
        content = render_slides(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    elif output_format == "figure":
        destination = root / "output" / "figures" / f"{artifact_id}.md"
        content = render_figure_brief(question, ranked, ranked_concepts, machine_query, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.write_text(content, encoding="utf-8")
    append_wiki_log(
        root,
        "query",
        question,
        [
            f"format: `{output_format}`",
            f"artifact: `{relative_path(root, destination)}`",
            f"ranked_sources: `{len(ranked)}`",
            f"ranked_concepts: `{len(ranked_concepts)}`",
            f"machine_terms: `{len(machine_query['matched_terms'])}`",
            f"machine_hits: `{len(machine_query['ranked_source_ids'])}/{len(machine_query['ranked_concept_slugs'])}`",
            f"bridge_concepts: `{len(machine_query['bridge_concept_slugs'])}`",
            f"query_routes: `{len(machine_query['query_routes'])}`",
        ],
    )
    return {
        "path": relative_path(root, destination),
        "format": output_format,
        "ranked_sources": [entry["id"] for entry in ranked],
        "ranked_concepts": [concept["slug"] for concept in ranked_concepts],
        "machine_memory_query": machine_query,
        "index_pages": [
            "wiki/indexes/index.md",
            "wiki/indexes/sources.md",
            "wiki/indexes/concepts.md",
            "wiki/indexes/compile-status.md",
            "wiki/indexes/machine-memory.md",
            "wiki/indexes/graph-health.md",
            "wiki/indexes/drift-report.md",
            "wiki/indexes/repair-backlog.md",
            "wiki/indexes/log.md",
            "schema/index.md",
        ],
    }


def file_back(root: Path, artifact: str, title: str | None = None) -> dict[str, Any]:
    ensure_layout(root)
    candidate = Path(artifact)
    artifact_path = candidate if candidate.is_absolute() else (root / candidate)
    artifact_path = artifact_path.resolve()
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")

    filed_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root) else str(artifact_path)
    )
    entry_id = f"derived-{stamp}-{slugify(title or artifact_path.stem)[:48]}"
    destination = root / "wiki" / "derived" / f"{entry_id}.md"
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    payload = "\n".join(
        [
            render_frontmatter(
                {
                    "id": entry_id,
                    "kind": "derived",
                    "status": "filed",
                    "title": title or artifact_path.stem,
                    "source_files": [artifact_ref],
                    "citations": [],
                    "generated_by": "aiwiki-file-back",
                    "last_compiled_at": filed_at,
                    "confidence": "medium",
                }
            ),
            "",
            f"# {title or artifact_path.stem}",
            "",
            "## Origin",
            f"- Filed from: `{artifact_ref}`",
            f"- Filed at: `{filed_at}`",
            "",
            "## Filed Content",
            strip_frontmatter(original).strip(),
        ]
    ).rstrip() + "\n"
    destination.write_text(payload, encoding="utf-8")
    append_wiki_log(
        root,
        "file-back",
        title or artifact_path.stem,
        [
            f"from: `{artifact_ref}`",
            f"destination: `{relative_path(root, destination)}`",
        ],
    )
    return {"path": relative_path(root, destination)}


def pending_source_summary_ids(root: Path, entries: list[dict[str, Any]]) -> list[str]:
    pending: list[str] = []
    for entry in entries:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        if "Pending LLM summary." in content:
            pending.append(entry["id"])
    return pending


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


def lint_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    findings: list[Finding] = []

    for entry in manifest["entries"]:
        page = root / "wiki" / "sources" / f"{entry['id']}.md"
        if not page.exists():
            findings.append(
                Finding("error", relative_path(root, page), f"Missing source page for manifest entry `{entry['id']}`.")
            )
            continue
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        for key in ("id", "kind", "source_files", "generated_by"):
            if key not in frontmatter or frontmatter[key] in ("", []):
                findings.append(
                    Finding("error", relative_path(root, page), f"Frontmatter is missing required key `{key}`.")
                )
        for source_file in frontmatter.get("source_files", []):
            candidate = root / source_file
            if not candidate.exists():
                findings.append(
                    Finding("error", relative_path(root, page), f"Referenced source file does not exist: `{source_file}`.")
                )
        if "Pending LLM summary." in content:
            findings.append(
                Finding("warn", relative_path(root, page), "Source page still contains the placeholder summary.")
            )
        if not frontmatter.get("concepts"):
            findings.append(
                Finding("warn", relative_path(root, page), "Source page has no compiled concept links.")
            )

    required_indexes = {
        "wiki/indexes/index.md": "Missing master wiki index page.",
        "wiki/indexes/sources.md": "Missing sources index page.",
        "wiki/indexes/concepts.md": "Missing concepts index page.",
        "wiki/indexes/compile-status.md": "Missing compile status page.",
        "wiki/indexes/machine-memory.md": "Missing machine memory index page.",
        "wiki/indexes/graph-health.md": "Missing machine memory graph health page.",
        "wiki/indexes/drift-report.md": "Missing machine memory drift report.",
        "wiki/indexes/log.md": "Missing wiki operation log.",
    }
    for relative, message in required_indexes.items():
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, message))

    required_schema = {
        "schema/index.md": "Missing runtime schema index.",
        "schema/ingest.md": "Missing runtime ingest rules.",
        "schema/citations.md": "Missing runtime citation rules.",
        "schema/conflicts.md": "Missing runtime conflict rules.",
        "schema/writeback.md": "Missing runtime writeback rules.",
    }
    for relative, message in required_schema.items():
        page = root / relative
        if not page.exists():
            findings.append(Finding("error", relative, message))

    memory_state = machine_memory_state_path(root)
    if manifest["entries"] and not memory_state.exists():
        findings.append(Finding("error", relative_path(root, memory_state), "Missing machine memory state file."))
    elif memory_state.exists():
        try:
            memory = json.loads(memory_state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(Finding("error", relative_path(root, memory_state), "Machine memory state is not valid JSON."))
        else:
            if "source_nodes" not in memory or "concept_nodes" not in memory:
                findings.append(
                    Finding("error", relative_path(root, memory_state), "Machine memory state is missing required indexes.")
                )
            if "health" not in memory:
                findings.append(
                    Finding("warn", relative_path(root, memory_state), "Machine memory state is missing graph health data.")
                )
            if not memory.get("digest"):
                findings.append(
                    Finding("warn", relative_path(root, memory_state), "Machine memory state is missing a stable digest.")
                )

    graph_export = machine_memory_graph_path(root)
    if manifest["entries"] and not graph_export.exists():
        findings.append(Finding("error", relative_path(root, graph_export), "Missing machine memory graph export."))
    elif graph_export.exists():
        try:
            graph = json.loads(graph_export.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append(Finding("error", relative_path(root, graph_export), "Machine memory graph export is not valid JSON."))
        else:
            if "nodes" not in graph or "edges" not in graph:
                findings.append(
                    Finding("error", relative_path(root, graph_export), "Machine memory graph export is missing nodes or edges.")
                )

    history_path = machine_memory_history_path(root)
    if manifest["entries"] and not history_path.exists():
        findings.append(Finding("warn", relative_path(root, history_path), "Machine memory history file has not been initialized."))

    concept_pages = sorted((root / "wiki" / "concepts").glob("*.md"))
    if manifest["entries"] and not concept_pages:
        findings.append(Finding("warn", "wiki/concepts", "No concept pages have been compiled yet."))

    for page in concept_pages:
        content = page.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if frontmatter.get("kind") != "concept":
            findings.append(Finding("warn", relative_path(root, page), "Concept page kind is missing or incorrect."))
        if concept_summary_is_placeholder(content):
            findings.append(Finding("warn", relative_path(root, page), "Concept page still contains the fallback summary."))
        source_pages = frontmatter.get("source_pages", [])
        if not source_pages:
            findings.append(Finding("warn", relative_path(root, page), "Concept page has no source-page references."))
        for source_page in source_pages:
            candidate = root / source_page
            if not candidate.exists():
                findings.append(
                    Finding("error", relative_path(root, page), f"Concept page references missing source page: `{source_page}`.")
                )

    for page in sorted((root / "wiki" / "derived").glob("*.md")):
        content = page.read_text(encoding="utf-8", errors="replace")
        if "wiki/sources/" not in content and "raw/" not in content:
            findings.append(
                Finding("warn", relative_path(root, page), "Derived page has no explicit source-page reference.")
            )

    generated_at = utc_now()
    report_name = f"lint-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    report_path = root / "output" / "lint" / report_name
    error_count = sum(1 for finding in findings if finding.severity == "error")
    warn_count = sum(1 for finding in findings if finding.severity == "warn")
    lines = [
        "# Lint Report",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Errors: `{error_count}`",
        f"- Warnings: `{warn_count}`",
        "",
        "## Findings",
    ]
    if not findings:
        lines.append("- No findings.")
    else:
        for finding in findings:
            lines.append(f"- `{finding.severity}` {finding.path}: {finding.message}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_wiki_log(
        root,
        "lint",
        "wiki health check",
        [
            f"errors: `{error_count}`",
            f"warnings: `{warn_count}`",
            f"report: `{relative_path(root, report_path)}`",
        ],
    )
    return {
        "path": relative_path(root, report_path),
        "counts": {"errors": error_count, "warnings": warn_count},
        "findings": [
            {"severity": finding.severity, "path": finding.path, "message": finding.message}
            for finding in findings
        ],
    }


def render_repair_backlog(
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    memory: dict[str, Any],
    pending_sources: list[str],
    placeholder_concepts: list[str],
    semantic_report: str,
    generated_at: str,
) -> str:
    drift = memory.get("drift", {})
    health = memory.get("health", {})
    transition = memory.get("transition", {})
    findings = lint_result.get("findings", [])
    error_findings = [finding for finding in findings if finding["severity"] == "error"]
    warn_findings = [finding for finding in findings if finding["severity"] == "warn"]
    sources_without_concepts = drift.get("sources_without_concepts", [])
    isolated_sources = health.get("isolated_source_ids", [])
    singleton_concepts = health.get("singleton_concept_slugs", [])
    bridge_concepts = health.get("bridge_concept_slugs", [])
    overloaded_concepts = health.get("overloaded_concept_slugs", [])
    lines = [
        "# Repair Backlog",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Compile changed pages: `{compile_result.get('changed_pages', 0)}`",
        f"- Machine memory changed: `{compile_result.get('machine_memory_changed', False)}`",
        f"- Lint errors: `{lint_result['counts']['errors']}`",
        f"- Lint warnings: `{lint_result['counts']['warnings']}`",
        f"- Pending source summaries: `{len(pending_sources)}`",
        f"- Placeholder concept summaries: `{len(placeholder_concepts)}`",
        f"- Sources without concepts: `{len(sources_without_concepts)}`",
        f"- Graph components: `{health.get('component_count', 0)}`",
        f"- Isolated sources: `{len(isolated_sources)}`",
        f"- Singleton concepts: `{len(singleton_concepts)}`",
        f"- Bridge concepts: `{len(bridge_concepts)}`",
        f"- Overloaded concepts: `{len(overloaded_concepts)}`",
        "",
        "## Priority Queue",
    ]
    if error_findings:
        lines.append(f"1. Resolve `{len(error_findings)}` lint error(s) before trusting downstream outputs.")
    if pending_sources:
        lines.append(f"2. Enrich `{len(pending_sources)}` source page(s) that still have placeholder summaries.")
    if placeholder_concepts:
        lines.append(f"3. Revisit `{len(placeholder_concepts)}` concept page(s) that still use fallback summaries.")
    if sources_without_concepts:
        lines.append(f"4. Investigate `{len(sources_without_concepts)}` source(s) with no concept coverage.")
    if isolated_sources:
        lines.append(f"5. Connect `{len(isolated_sources)}` isolated source node(s) into the concept graph.")
    if singleton_concepts:
        lines.append(f"6. Revisit `{len(singleton_concepts)}` singleton concept(s) that do not yet connect wider context.")
    if overloaded_concepts:
        lines.append(f"7. Consider splitting `{len(overloaded_concepts)}` overloaded concept(s).")
    if transition.get("changed"):
        lines.append("8. Review the latest machine-memory drift before the next research pass.")
    if not any(
        (
            error_findings,
            pending_sources,
            placeholder_concepts,
            sources_without_concepts,
            isolated_sources,
            singleton_concepts,
            overloaded_concepts,
            transition.get("changed"),
        )
    ):
        lines.append("1. No immediate repair items. Keep monitoring nightly drift and lint output.")
    lines.extend(
        [
            "",
            "## Actionable Items",
        ]
    )
    if error_findings:
        lines.append("### Lint Errors")
        for finding in error_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if warn_findings:
        lines.append("")
        lines.append("### Lint Warnings")
        for finding in warn_findings[:10]:
            lines.append(f"- `{finding['path']}`: {finding['message']}")
    if pending_sources:
        lines.append("")
        lines.append("### Pending Source Summaries")
        for source_id in pending_sources[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    if placeholder_concepts:
        lines.append("")
        lines.append("### Placeholder Concept Summaries")
        for slug in placeholder_concepts[:10]:
            lines.append(f"- `wiki/concepts/{slug}.md`")
    if sources_without_concepts:
        lines.append("")
        lines.append("### Sources Without Concepts")
        for source_id in sources_without_concepts[:10]:
            lines.append(f"- `wiki/sources/{source_id}.md`")
    lines.append("")
    lines.append("### Graph Repair Suggestions")
    if isolated_sources:
        for source_id in isolated_sources[:10]:
            lines.append(f"- Connect isolated source `wiki/sources/{source_id}.md` to at least one stable concept.")
    if singleton_concepts:
        for slug in singleton_concepts[:10]:
            lines.append(f"- Review singleton concept `wiki/concepts/{slug}.md` for missing related concepts or missing source links.")
    if overloaded_concepts:
        for slug in overloaded_concepts[:10]:
            lines.append(f"- Consider splitting broad concept `wiki/concepts/{slug}.md` into narrower pages.")
    if bridge_concepts:
        lines.append(f"- Preserve bridge concepts: `{', '.join(bridge_concepts[:10])}` because they connect multiple clusters.")
    if not any((isolated_sources, singleton_concepts, overloaded_concepts, bridge_concepts)):
        lines.append("- No graph-specific repair items right now.")
    if transition.get("changed"):
        lines.append("")
        lines.append("### Structural Drift")
        lines.append(f"- Previous digest: `{transition.get('previous_digest', '') or 'none'}`")
        lines.append(f"- Current digest: `{transition.get('current_digest', '') or 'none'}`")
        lines.append(f"- Added source nodes: `{len(transition.get('added_source_ids', []))}`")
        lines.append(f"- Added concept nodes: `{len(transition.get('added_concept_slugs', []))}`")
        lines.append(f"- Added edges: `{transition.get('added_edges', 0)}`")
        lines.append(f"- Removed edges: `{transition.get('removed_edges', 0)}`")
    lines.extend(
        [
            "",
            "## Artifacts",
            f"- Lint report: `{lint_result['path']}`",
            "- Machine memory: `wiki/indexes/machine-memory.md`",
            "- Graph health: `wiki/indexes/graph-health.md`",
            "- Drift report: `wiki/indexes/drift-report.md`",
            "- Schema index: `schema/index.md`",
        ]
    )
    if semantic_report:
        lines.append(f"- Semantic lint: `{semantic_report}`")
    return "\n".join(lines) + "\n"


def write_nightly_health(
    root: Path,
    compile_result: dict[str, Any],
    lint_result: dict[str, Any],
    *,
    semantic_report: str = "",
    llm_used: bool = False,
) -> dict[str, Any]:
    ensure_layout(root)
    manifest = load_manifest(root)
    memory = load_machine_memory(root)
    pending_sources = pending_source_summary_ids(root, manifest["entries"])
    placeholder_concepts = placeholder_concept_slugs(root)
    generated_at = utc_now()
    state = {
        "generated_at": generated_at,
        "llm_used": llm_used,
        "compile": compile_result,
        "lint": {
            "path": lint_result["path"],
            "counts": lint_result["counts"],
        },
        "semantic_report": semantic_report,
        "machine_memory": {
            "digest": memory.get("digest", ""),
            "graph_digest": memory.get("graph_digest", ""),
            "transition": memory.get("transition", {}),
            "drift": memory.get("drift", {}),
            "health": memory.get("health", {}),
        },
        "repair_backlog": {
            "path": relative_path(root, repair_backlog_path(root)),
            "pending_source_summaries": pending_sources,
            "placeholder_concepts": placeholder_concepts,
        },
    }
    repair_backlog = render_repair_backlog(
        compile_result,
        lint_result,
        memory,
        pending_sources,
        placeholder_concepts,
        semantic_report,
        generated_at,
    )
    repair_backlog_path(root).write_text(repair_backlog, encoding="utf-8")
    nightly_health_state_path(root).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_wiki_log(
        root,
        "nightly",
        "health and repair pass",
        [
            f"llm_used: `{llm_used}`",
            f"lint_errors: `{lint_result['counts']['errors']}`",
            f"lint_warnings: `{lint_result['counts']['warnings']}`",
            f"pending_source_summaries: `{len(pending_sources)}`",
            f"placeholder_concepts: `{len(placeholder_concepts)}`",
            f"repair_backlog: `{relative_path(root, repair_backlog_path(root))}`",
        ],
    )
    return state


def nightly_health(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    compile_result = compile_wiki(root)
    lint_result = lint_wiki(root)
    state = write_nightly_health(root, compile_result, lint_result, semantic_report="", llm_used=False)
    return {
        "compile": compile_result,
        "lint": lint_result,
        "repair_backlog": state["repair_backlog"]["path"],
        "state_path": relative_path(root, nightly_health_state_path(root)),
    }
