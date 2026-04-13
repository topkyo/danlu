"""Phase 0 utility helpers extracted from aiwiki.app."""

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
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_RUNTIME_LOCK_GUARD = threading.RLock()


_RUNTIME_LOCKS: dict[str, dict[str, Any]] = {}


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


PROVENANCE_PATH_PATTERN = re.compile(r"(?:\.\./)*(wiki/sources/[^\s`)\]]+\.md|raw/[^\s`)\]]+)")


ISO_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\+\d{2}:\d{2}|Z)")


def runtime_lock_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "runtime.lock"


@contextmanager
def runtime_write_lock(root: Path):
    resolved_root = str(root.resolve())
    with _RUNTIME_LOCK_GUARD:
        state = _RUNTIME_LOCKS.get(resolved_root)
        if state is not None:
            state["depth"] = int(state.get("depth", 0)) + 1
            handle = state["handle"]
        else:
            lock_path = runtime_lock_path(root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = lock_path.open("a+", encoding="utf-8")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "root": resolved_root,
                        "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            _RUNTIME_LOCKS[resolved_root] = {"handle": handle, "depth": 1}
    try:
        yield
    finally:
        with _RUNTIME_LOCK_GUARD:
            state = _RUNTIME_LOCKS.get(resolved_root)
            if state is None:
                return
            state["depth"] = int(state.get("depth", 0)) - 1
            if state["depth"] > 0:
                return
            handle = state["handle"]
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
                _RUNTIME_LOCKS.pop(resolved_root, None)


def runtime_write_operation(func):
    @functools.wraps(func)
    def wrapper(root: Path, *args, **kwargs):
        with runtime_write_lock(root):
            return func(root, *args, **kwargs)

    return wrapper


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def next_identifier(existing_ids: set[str], seed: str) -> str:
    candidate = seed
    index = 2
    while candidate in existing_ids:
        candidate = f"{seed}-{index}"
        index += 1
    return candidate


def next_available_stem(directory: Path, seed: str, suffix: str = ".md") -> str:
    candidate = seed
    index = 2
    while (directory / f"{candidate}{suffix}").exists():
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


def upsert_markdown_section(markdown: str, heading: str, content: str) -> str:
    section = content.strip()
    block = f"## {heading}\n{section}\n"
    pattern = rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)"
    if re.search(pattern, markdown):
        updated = re.sub(pattern, block + "\n", markdown).strip()
        return updated + "\n"
    base = markdown.rstrip()
    if base:
        return base + "\n\n" + block
    return block


def normalize_workspace_path(value: str) -> str:
    normalized = value.strip().strip("'\"`")
    while normalized.startswith("../"):
        normalized = normalized[3:]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip(".,;:")


def extract_provenance_paths(root: Path, markdown: str) -> list[str]:
    frontmatter = parse_frontmatter(markdown)
    candidates: list[str] = []
    for key in ("citations", "source_files"):
        value = frontmatter.get(key, [])
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if isinstance(item, str))
    candidates.extend(match.group(1) for match in PROVENANCE_PATH_PATTERN.finditer(markdown))

    normalized_paths: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        path = normalize_workspace_path(candidate)
        if not path.startswith(("wiki/sources/", "raw/")):
            continue
        if not (root / path).exists():
            continue
        if path in seen:
            continue
        seen.add(path)
        normalized_paths.append(path)
    return normalized_paths


def evidence_path_digest(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists():
        return ""
    if relative.startswith("wiki/sources/"):
        return compiled_source_sha(path.read_text(encoding="utf-8", errors="replace"))
    if path.is_file():
        return sha256_file(path)
    return ""


def build_citation_snapshots(root: Path, citations: list[str]) -> list[str]:
    snapshots: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        normalized = normalize_workspace_path(str(citation))
        if not normalized or normalized in seen:
            continue
        digest = evidence_path_digest(root, normalized)
        if not digest:
            continue
        seen.add(normalized)
        snapshots.append(f"{normalized}#{digest}")
    return snapshots


def parse_citation_snapshots(frontmatter: dict[str, Any]) -> dict[str, str]:
    snapshots: dict[str, str] = {}
    raw_value = frontmatter.get("citation_snapshots", [])
    if not isinstance(raw_value, list):
        return snapshots
    for item in raw_value:
        if not isinstance(item, str) or "#" not in item:
            continue
        relative, digest = item.rsplit("#", 1)
        relative = normalize_workspace_path(relative)
        if not relative or not digest:
            continue
        snapshots[relative] = digest
    return snapshots


def analyze_citation_snapshots(
    root: Path,
    citations: list[str],
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    current = {
        snapshot.rsplit("#", 1)[0]: snapshot.rsplit("#", 1)[1]
        for snapshot in build_citation_snapshots(root, citations)
        if "#" in snapshot
    }
    recorded = parse_citation_snapshots(frontmatter)
    drifted = sorted(path for path, digest in current.items() if recorded.get(path) and recorded[path] != digest)
    missing = sorted(path for path in current if path not in recorded)
    stale = sorted(path for path in recorded if path not in current)
    return {
        "current": current,
        "recorded": recorded,
        "drifted": drifted,
        "missing": missing,
        "stale": stale,
        "has_drift": bool(drifted or missing or stale),
    }


def replace_first_markdown_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            lines[index] = f"# {title}"
            return "\n".join(lines).strip() + "\n"
    body = markdown.strip()
    if body:
        return f"# {title}\n\n{body}\n"
    return f"# {title}\n"


def first_markdown_heading(markdown: str) -> str:
    for line in strip_frontmatter(markdown).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def normalize_generated_artifact_content(content: str) -> str:
    return ISO_DATETIME_PATTERN.sub("<ISO_DATETIME>", content)


def write_if_changed_ignoring_timestamps(path: Path, content: str) -> tuple[bool, bool]:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False, False
        if normalize_generated_artifact_content(current) == normalize_generated_artifact_content(content):
            return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, True


def render_json_document(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def normalize_generated_state_document(payload: Any) -> Any:
    if isinstance(payload, dict):
        normalized: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"generated_at", "computed_at"} and isinstance(value, str) and ISO_DATETIME_PATTERN.fullmatch(value):
                normalized[key] = "<ISO_DATETIME>"
            else:
                normalized[key] = normalize_generated_state_document(value)
        return normalized
    if isinstance(payload, list):
        return [normalize_generated_state_document(item) for item in payload]
    return payload


def write_json_document_if_changed_ignoring_generated_timestamps(path: Path, document: dict[str, Any]) -> tuple[bool, bool]:
    rendered = render_json_document(document)
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == rendered:
            return False, False
        try:
            current_document = json.loads(current)
        except json.JSONDecodeError:
            current_document = None
        if isinstance(current_document, dict):
            if normalize_generated_state_document(current_document) == normalize_generated_state_document(document):
                return False, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True, True


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


def html_safe_json_literal(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]
