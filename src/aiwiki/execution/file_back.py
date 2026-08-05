"""File-back execution owner: promote output artifacts into wiki/judgments.

Extracted from execution.ask (hub single seam 2026-08-05).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..compile import compile_wiki
from ..lifecycle.status import default_curated_status
from ..lifecycle.templates import curated_page_template, repair_curated_page_body
from ..protocol.review_windows import schedule_review_windows
from ..protocol.scaffold import ensure_layout
from ..protocol.state import resolve_protocol
from ..render.paths import append_wiki_log
from ..state.paths import output_candidates_state_path
from ..utils.io import _restore_file_bytes, _snapshot_file_bytes, atomic_write_text, runtime_write_operation
from ..utils.markdown import parse_frontmatter, render_frontmatter, strip_frontmatter
from ..utils.path import next_available_stem, relative_path
from .candidates import load_output_candidates_state, upsert_output_candidate
from .receipts import write_execution_receipt

NEXT_STEP_HINTS = {
    "derived": (
        "wiki/derived 是机器记忆终态层；不进入 review-page 工作流。"
        "如需人工审阅，请用 aiwiki advanced file-back <artifact> 写入 wiki/judgments/。"
        "如需进入金丹链路，请先用 aiwiki advanced alchemy promote <output_ref> 注册 corpus candidate，再运行 advanced alchemy start。"
    ),
    "judgment": ("next: aiwiki advanced review-page {path} --status <tentative|tracking|confirmed|rejected>"),
    "decision": ("next: aiwiki advanced review-page {path} --status <proposed|approved|needs-revisit|superseded>"),
}

READABLE_FILENAME_MAX_CHARS = 72


def _readable_filename_stem(label: str, *, fallback: str, max_chars: int = READABLE_FILENAME_MAX_CHARS) -> str:
    parts: list[str] = []
    pending_separator = False
    for char in label.strip():
        if char.isalnum():
            if pending_separator and parts:
                parts.append("-")
            parts.append(char.lower() if char.isascii() else char)
            pending_separator = False
        elif char in {"-", "_"} or char.isspace() or not char.isprintable() or char in {"/", "\\"}:
            pending_separator = True
        else:
            pending_separator = True
    stem = "".join(parts).strip("-_")
    if len(stem) > max_chars:
        stem = stem[:max_chars].rstrip("-_")
    return stem or fallback


def _file_back_entry_seed(kind: str, title: str) -> str:
    stem = _readable_filename_stem(title, fallback=kind)
    return f"{kind}-{stem}"


@runtime_write_operation
def file_back(
    root: Path,
    artifact: str,
    title: str | None = None,
    kind: str = "judgment",
    protocol: str | None = None,
) -> dict[str, Any]:
    from ..utils.security import safe_resolve_within
    from ..utils.time import utc_now

    ensure_layout(root)
    root_resolved = root.resolve(strict=False)
    candidate = Path(artifact)
    artifact_path = safe_resolve_within(
        candidate if candidate.is_absolute() else (root / candidate),
        root,
    )
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact}")
    if artifact_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        raise ValueError("Only markdown or text artifacts can be filed back in the MVP.")
    if kind != "judgment":
        raise ValueError(
            "file-back accepts judgment only; derived and decision kinds were removed from the product CLI."
        )

    filed_at = utc_now()
    artifact_ref = (
        relative_path(root, artifact_path) if artifact_path.is_relative_to(root_resolved) else str(artifact_path)
    )
    original = artifact_path.read_text(encoding="utf-8", errors="replace")
    original_frontmatter = parse_frontmatter(original)
    source_protocol = str(original_frontmatter.get("protocol") or "").strip()
    resolved_protocol = resolve_protocol(root, protocol or source_protocol or None)

    # Idempotent product UX: same report already filed → reuse judgment, do not mint -N.md spam.
    for candidate in load_output_candidates_state(root).get("candidates", []):
        if candidate.get("artifact_ref") != artifact_ref:
            continue
        existing = str(candidate.get("promoted_to") or "").strip()
        if existing.startswith("wiki/judgments/") and (root / existing).is_file():
            next_step_hint = NEXT_STEP_HINTS[kind].format(path=existing)
            return {
                "path": existing,
                "protocol": resolved_protocol,
                "next_step_hint": next_step_hint,
                "reused": True,
                "already_filed": True,
            }
        break
    entry_seed = _file_back_entry_seed(kind, title or artifact_path.stem)
    directory = {
        "derived": root / "wiki" / "derived",
        "decision": root / "wiki" / "decisions",
        "judgment": root / "wiki" / "judgments",
    }[kind]
    directory.mkdir(parents=True, exist_ok=True)
    entry_id = next_available_stem(directory, entry_seed)
    destination = directory / f"{entry_id}.md"
    revisit_after = ""
    escalate_after = ""
    if kind in {"decision", "judgment"}:
        revisit_after, escalate_after = schedule_review_windows(
            kind,
            default_curated_status(kind),
            filed_at,
            protocol=resolved_protocol,
            root=root,
        )
    stripped = strip_frontmatter(original).strip()

    frontmatter_payload: dict[str, Any] = {
        "id": entry_id,
        "kind": kind,
        "status": default_curated_status(kind),
        "title": title or artifact_path.stem,
        "protocol": resolved_protocol,
        "confidence": "medium",
        "source_files": [artifact_ref],
        "revisit_after": revisit_after,
        "reviewed_at": "",
        "cssclasses": ["aiwiki-output"],
    }
    frontmatter = render_frontmatter(frontmatter_payload)
    body_lines = curated_page_template(
        kind=kind,
        protocol=resolved_protocol,
        title=title or artifact_path.stem,
        artifact_ref=artifact_ref,
        filed_at=filed_at,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
    )
    body_text = repair_curated_page_body(
        kind=kind,
        protocol=resolved_protocol,
        body="\n".join(body_lines),
        artifact_ref=artifact_ref,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
        supporting_body=stripped,
        root=root,
        source_files=[artifact_ref],
    )
    payload = "\n".join([frontmatter, "", body_text]).rstrip() + "\n"
    destination_snapshot = _snapshot_file_bytes(destination)
    output_candidates_snapshot = _snapshot_file_bytes(output_candidates_state_path(root))
    wiki_log_snapshot = _snapshot_file_bytes(root / "wiki" / "indexes" / "log.md")
    atomic_write_text(destination, payload)
    try:
        candidate_state = load_output_candidates_state(root)
        for candidate in candidate_state.get("candidates", []):
            if candidate.get("artifact_ref") == artifact_ref:
                # wiki/judgments/ is the W8-sanctioned alchemy provenance anchor
                # (promote_candidate via wiki/derived was removed). Judgment
                # file-backs set promoted_to to wiki/judgments/; alchemy accepts
                # both wiki/derived/ (legacy) and wiki/judgments/ as elixir sources.
                # DEF-R2-01: duplicate file-back must not rewrite an existing
                # judgment/derived anchor — that orphans elixir derived_from.
                promoted_to = relative_path(root, destination)
                if kind in {"judgment", "decision"}:
                    existing = str(candidate.get("promoted_to") or "").strip()
                    if existing.startswith("wiki/derived/"):
                        promoted_to = existing
                    elif existing.startswith("wiki/judgments/") and (root / existing).is_file():
                        promoted_to = existing
                upsert_output_candidate(
                    root,
                    artifact_ref=artifact_ref,
                    candidate_state="promoted",
                    created_at=str(candidate.get("created_at") or filed_at),
                    updated_at=filed_at,
                    format=str(candidate.get("format") or ""),
                    protocol=str(candidate.get("protocol") or resolved_protocol),
                    corpus_id=str(candidate.get("corpus_id") or ""),
                    question=str(candidate.get("question") or ""),
                    promoted_to=promoted_to,
                    promoted_at=filed_at,
                    promotion_origin=str(candidate.get("promotion_origin") or "manual"),
                )
                break
        append_wiki_log(
            root,
            "file-back",
            title or artifact_path.stem,
            [
                f"kind: `{kind}`",
                f"protocol: `{resolved_protocol}`",
                f"from: `{artifact_ref}`",
                f"destination: `{relative_path(root, destination)}`",
            ],
        )
        compile_wiki(root)
        destination_ref = relative_path(root, destination)
        write_execution_receipt(
            root,
            operation="file-back",
            generated_by="aiwiki-file-back",
            subject_kind="output-artifact",
            subject_id=str(original_frontmatter.get("id") or original_frontmatter.get("_id") or artifact_path.stem),
            target_file=artifact_ref,
            primary_path=artifact_ref,
            secondary_path=destination_ref,
            protocol=resolved_protocol,
            extra={
                "filed_kind": kind,
                "title": title or artifact_path.stem,
            },
        )
    except Exception:
        _restore_file_bytes(root / "wiki" / "indexes" / "log.md", wiki_log_snapshot)
        _restore_file_bytes(output_candidates_state_path(root), output_candidates_snapshot)
        _restore_file_bytes(destination, destination_snapshot)
        raise
    next_step_hint = NEXT_STEP_HINTS[kind]
    if kind in {"decision", "judgment"}:
        next_step_hint = next_step_hint.format(path=destination_ref)
    return {"path": destination_ref, "protocol": resolved_protocol, "next_step_hint": next_step_hint}


__all__ = ["file_back", "_readable_filename_stem"]
