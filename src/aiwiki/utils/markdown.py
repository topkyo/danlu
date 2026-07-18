from __future__ import annotations

import contextlib
import fcntl
import functools
import hashlib
import html
import http.client
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from .hash import compiled_source_sha, sha256_file
from .path import normalize_workspace_path

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
PROVENANCE_PATH_PATTERN = re.compile(r"(?:\.\./)*(wiki/sources/[^\s`)\]]+\.md|raw/[^\s`)\]]+)")


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
    for key in ("title", "source_type", "original_path", "note_kind"):
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
