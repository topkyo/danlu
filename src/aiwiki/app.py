"""Core application logic for the aiwiki MVP."""

from __future__ import annotations

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
    "after",
    "against",
    "brief",
    "compare",
    "figure",
    "from",
    "into",
    "must",
    "question",
    "report",
    "slides",
    "that",
    "their",
    "there",
    "these",
    "this",
    "with",
}


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)


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
    known_paths = {entry["stored_path"] for entry in entries}
    existing_ids = {entry["id"] for entry in entries}
    changed = False

    for path in sorted((root / "raw" / "inbox").iterdir()):
        if not path.is_file():
            continue
        stored_path = relative_path(root, path)
        if stored_path in known_paths:
            continue
        metadata = raw_note_metadata(path)
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
    return entry


def render_source_page(entry: dict[str, Any], preview: str, compiled_at: str) -> str:
    frontmatter = render_frontmatter(
        {
            "id": entry["id"],
            "kind": "source",
            "status": "compiled",
            "title": entry["title"],
            "source_files": [entry["stored_path"]],
            "citations": [],
            "generated_by": "aiwiki-compile",
            "last_compiled_at": compiled_at,
            "confidence": "low",
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
            "- Pending LLM summary.",
            "",
            "## Enrichment TODO",
            "- Add concept links after semantic synthesis.",
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


def render_concepts_index(entries: list[dict[str, Any]], compiled_at: str) -> str:
    seeds = concept_candidates(entries)
    lines = [
        "# Concepts Index",
        "",
        f"- Last compiled at: `{compiled_at}`",
        "- Concept pages are not synthesized automatically in this MVP.",
        "- Use `prompts/compile.md` with an external agent to enrich this layer.",
        "",
        "## Seed Terms",
    ]
    if not seeds:
        lines.append("- Not enough source material yet.")
    else:
        for seed in seeds:
            lines.append(f"- {seed}")
    return "\n".join(lines) + "\n"


def render_compile_status(entries: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# Compile Status",
        "",
        f"- Last compiled at: `{compiled_at}`",
        f"- Source pages: `{len(entries)}`",
        "- Derived pages are filed back explicitly via `aiwiki file-back`.",
        "- Lint findings land under `output/lint/`.",
    ]
    return "\n".join(lines) + "\n"


def compile_wiki(root: Path) -> dict[str, Any]:
    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    entries: list[dict[str, Any]] = manifest["entries"]
    compiled_at = utc_now()
    changed_pages = 0

    for entry in entries:
        source_file = root / entry["stored_path"]
        preview = read_text_preview(source_file)
        destination = root / "wiki" / "sources" / f"{entry['id']}.md"
        content = render_source_page(entry, preview, compiled_at)
        changed_pages += int(write_if_changed(destination, content))

    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "sources.md", render_sources_index(entries, compiled_at))
    )
    changed_pages += int(
        write_if_changed(root / "wiki" / "indexes" / "concepts.md", render_concepts_index(entries, compiled_at))
    )
    changed_pages += int(
        write_if_changed(
            root / "wiki" / "indexes" / "compile-status.md",
            render_compile_status(entries, compiled_at),
        )
    )

    return {
        "compiled_at": compiled_at,
        "sources": len(entries),
        "changed_pages": changed_pages,
    }


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def rank_sources(root: Path, entries: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    question_tokens = tokenize(question)
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        source_file = root / entry["stored_path"]
        haystack = " ".join([entry["title"], read_text_preview(source_file, limit_lines=8)]).lower()
        score = 0
        for token in question_tokens:
            score += haystack.count(token)
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1]["title"].lower()))
    return [entry for _score, entry in scored[:5]]


def render_report(question: str, entries: list[dict[str, Any]], created_at: str, artifact_id: str) -> str:
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
        "## Recommended Sources",
    ]
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


def render_slides(question: str, entries: list[dict[str, Any]], created_at: str, artifact_id: str) -> str:
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
        "## Ranked Sources",
    ]
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


def render_figure_brief(question: str, entries: list[dict[str, Any]], created_at: str, artifact_id: str) -> str:
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
        "## Recommended Sources",
    ]
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
    ranked = rank_sources(root, entries, question)
    created_at = utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    artifact_id = f"query-{stamp}-{slugify(question)[:48]}"

    if output_format == "report":
        destination = root / "output" / "reports" / f"{artifact_id}.md"
        content = render_report(question, ranked, created_at, artifact_id)
    elif output_format == "slides":
        destination = root / "output" / "slides" / f"{artifact_id}.md"
        content = render_slides(question, ranked, created_at, artifact_id)
    elif output_format == "figure":
        destination = root / "output" / "figures" / f"{artifact_id}.md"
        content = render_figure_brief(question, ranked, created_at, artifact_id)
    else:
        raise ValueError(f"Unsupported format: {output_format}")

    destination.write_text(content, encoding="utf-8")
    return {
        "path": relative_path(root, destination),
        "format": output_format,
        "ranked_sources": [entry["id"] for entry in ranked],
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
    return {"path": relative_path(root, destination)}


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
    return {
        "path": relative_path(root, report_path),
        "counts": {"errors": error_count, "warnings": warn_count},
    }
