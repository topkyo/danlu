"""Pure helpers for drop ingestion."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_FILENAME_TITLE_SUFFIXES = {
    ".gif",
    ".jpeg",
    ".jpg",
    ".md",
    ".markdown",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
}

_LEADING_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def timestamped_stem(label: str) -> str:
    """Convert a user-facing title or filename into a stable safe file stem."""
    filename_label = re.sub(r"[\\/]+", " ", label.strip())
    suffix = Path(filename_label).suffix.lower()
    if suffix in _FILENAME_TITLE_SUFFIXES:
        filename_label = filename_label[: -len(suffix)]
    result = re.sub(r"[^\w\u3400-\u9fff]+", "-", filename_label.lower(), flags=re.UNICODE).strip("-_.")[:64]
    result = result.strip("-_.")
    if result and result != "item":
        return result
    return f"doc-{hashlib.sha256(label.encode()).hexdigest()[:12]}"


def normalize_drop_title(text: str) -> str:
    """Normalize a title for duplicate-heading comparison."""
    cleaned = re.sub(r"\s+", " ", str(text or "").strip()).casefold()
    return cleaned.strip(" \t-–—|:：")


def strip_leading_title_echo(body: str, display_title: str) -> str:
    """Remove leading body headings that duplicate or restate the note title.

    drop-url / drop-repo prepend ``# {display_title}``. Fetched pages often start
    with the same heading *or* a second H1 (page H1 vs og:title). Both become
    stacked title lines in Obsidian once inline title is off.
    """
    text = str(body or "").strip()
    if not text:
        return text
    target = normalize_drop_title(display_title)
    lines = text.splitlines()
    index = 0

    def _consume_blank() -> None:
        nonlocal index
        while index < len(lines) and not lines[index].strip():
            index += 1

    _consume_blank()

    # 1) Exact title echoes (may repeat).
    if target:
        while index < len(lines):
            raw = lines[index].strip()
            if not raw:
                index += 1
                continue
            match = _LEADING_HEADING_RE.match(raw)
            candidate = match.group(2) if match else raw
            if normalize_drop_title(candidate) != target:
                break
            index += 1
            _consume_blank()

    # 2) One alternate leading H1 (page title ≠ display_title).
    if index < len(lines):
        match = _LEADING_HEADING_RE.match(lines[index].strip())
        if match and match.group(1) == "#":
            index += 1
            _consume_blank()

    return "\n".join(lines[index:]).strip()
