from __future__ import annotations

import hashlib
from pathlib import Path

from ..app_utils import slugify

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
        path.write_text("\n".join(synthesized).rstrip() + "\n", encoding="utf-8")
        return
    filtered = lines[:1] + [
        line
        for line in lines[1:close_idx]
        if not line.startswith("run_id:") and not line.startswith("run_notes_path:")
    ]
    new_close_idx = len(filtered)
    filtered.append(lines[close_idx])
    filtered.extend(lines[close_idx + 1 :])
    for offset, line in enumerate(insertions):
        filtered.insert(new_close_idx + offset, line)
    path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")


def write_run_notes(
    root: Path,
    *,
    run_id: str,
    status: str,
    question: str,
    output_format: str,
    protocol: str,
    output_path: str,
    source_count: int = 0,
    concept_count: int = 0,
    receipt_path: str = "",
    backend: str = "",
    model: str = "",
    fallback_stage: str = "",
    failure_class: str = "",
    stages: list[str] | None = None,
    context_refs: list[str] | None = None,
) -> dict[str, str]:
    """No-op: do not write Obsidian-visible ``output/control/runs/*/thinking.md``.

    Progress belongs in Product Shell bubble status; audit belongs in receipts /
    runtime-history / the output artifact. ``run_id`` is still returned for
    correlation. Unused kwargs are retained for call-site compatibility.
    """

    if not str(run_id or "").strip():
        run_id = run_id_for_artifact(output_path or question or "run")
    del (
        root,
        status,
        question,
        output_format,
        protocol,
        output_path,
        source_count,
        concept_count,
        receipt_path,
        backend,
        model,
        fallback_stage,
        failure_class,
        stages,
        context_refs,
    )
    return {"run_id": run_id, "run_notes_path": ""}
