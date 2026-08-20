from __future__ import annotations

import hashlib
from pathlib import Path

from ..utils.io import atomic_write_text
from ..utils.text import slugify

RUN_NOTES_GENERATED_BY = "aiwiki-run-notes"


def run_id_for_artifact(artifact_ref: str) -> str:
    normalized = str(artifact_ref or "run").strip().replace("\\", "/") or "run"
    if normalized.endswith(".md"):
        normalized = normalized[:-3]
    slug = slugify(normalized)
    if any(not char.isascii() for char in normalized):
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
        if not slug or slug == "item":
            slug = digest
        elif not slug.endswith(f"-{digest}"):
            slug = f"{slug}-{digest}"
    return f"ask-{slug}"


def write_run_notes_frontmatter(path: Path, *, run_id: str, run_notes_ref: str = "") -> None:
    """Stamp ``run_id`` onto an output artifact; ``run_notes_path`` is retired."""

    del run_notes_ref  # Obsidian-visible thinking.md is no longer written.
    if not path.exists():
        raise FileNotFoundError(f"run notes artifact target not found: {path}")
    original = path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    has_frontmatter = bool(lines) and lines[0].strip() == "---"
    close_idx: int | None = None
    if has_frontmatter:
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                close_idx = idx
                break
    insertions = [f'run_id: "{run_id}"']
    if not has_frontmatter or close_idx is None:
        synthesized = ["---", *insertions, "---", *lines]
        atomic_write_text(path, "\n".join(synthesized).rstrip() + "\n")
        return
    filtered = lines[:1] + [
        line for line in lines[1:close_idx] if not line.startswith("run_id:") and not line.startswith("run_notes_path:")
    ]
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    for offset, line in enumerate(insertions):
        filtered.insert(new_close_idx + offset, line)
    atomic_write_text(path, "\n".join(filtered).rstrip() + "\n")
