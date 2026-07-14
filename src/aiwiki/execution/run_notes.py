from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..app_state import run_notes_path
from ..app_utils import relative_path, render_frontmatter, slugify, utc_now

RUN_NOTES_GENERATED_BY = "aiwiki-run-notes"


_ABSOLUTE_PATH_RE = re.compile(r"(?<![`\w])/[A-Za-z0-9._~+@%-]+(?:/[A-Za-z0-9._~+@%=-]+)+")


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


def write_run_notes_frontmatter(path: Path, *, run_id: str, run_notes_ref: str) -> None:
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
    insertions = [f'run_id: "{run_id}"', f'run_notes_path: "{run_notes_ref}"']
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


def _safe_note_text(root: Path, value: str) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    root_text = str(root)
    if root_text:
        text = text.replace(root_text, "[vault-root]")
    return _ABSOLUTE_PATH_RE.sub("[local-path]", text)


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
    if not str(run_id or "").strip():
        run_id = run_id_for_artifact(output_path or question or "run")
    generated_at = utc_now()
    notes_path = run_notes_path(root, run_id)
    notes_ref = relative_path(root, notes_path)
    frontmatter: dict[str, Any] = {
        "kind": "run-progress-notes",
        "generated_by": RUN_NOTES_GENERATED_BY,
        "run_id": run_id,
        "status": status,
        "protocol": protocol,
        "format": output_format,
        "output_path": output_path,
        "receipt_path": receipt_path,
        "updated_at": generated_at,
    }
    if backend:
        frontmatter["backend"] = backend
    if model:
        frontmatter["model"] = model
    if fallback_stage:
        frontmatter["fallback_stage"] = fallback_stage
    if failure_class:
        frontmatter["failure_class"] = failure_class
    stage_lines = stages or []
    if not stage_lines:
        stage_lines = [
            "Received request and selected protocol.",
            f"Prepared deterministic context: {source_count} sources, {concept_count} concepts.",
            "Drafted output artifact and recorded provenance links.",
        ]
    safe_question = _safe_note_text(root, question)
    safe_output_path = _safe_note_text(root, output_path)
    safe_receipt_path = _safe_note_text(root, receipt_path)
    safe_stage_lines = [_safe_note_text(root, line) for line in stage_lines]
    safe_context_refs = [_safe_note_text(root, ref) for ref in (context_refs or []) if str(ref or "").strip()]
    body_lines = [
        render_frontmatter(frontmatter),
        "",
        "# Visible Run Progress",
        "",
        "These notes are external progress notes for the user interface. They are not hidden model reasoning, internal instructions, tool internals, or a wiki fact source.",
        "",
        "## Request",
        "",
        f"- Question: {safe_question or '(empty request)'}",
        f"- Protocol: `{protocol}`",
        f"- Output format: `{output_format}`",
        f"- Output path: `{safe_output_path}`" if output_path else "- Output path: `(pending)`",
        "",
        "## Progress",
        "",
    ]
    body_lines.extend(f"- {line}" for line in safe_stage_lines)
    if safe_context_refs:
        body_lines.extend(["", "## Context References", ""])
        body_lines.extend(f"- `{ref}`" for ref in safe_context_refs)
    if receipt_path:
        body_lines.extend(["", "## Receipt", "", f"- Receipt path: `{safe_receipt_path}`"])
    body_lines.extend([
        "",
        "## Safety Boundary",
        "",
        "- This artifact intentionally omits hidden reasoning, internal instructions, backend payloads, command details, and local path traversal logs.",
        "- Use the final output and receipts as facts; use this note only as progress context.",
        "",
    ])
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text("\n".join(body_lines), encoding="utf-8")
    return {"run_id": run_id, "run_notes_path": notes_ref}
