"""EP-018B7: page review execution owner.

Owns the single-page review entry point that used to live in
``aiwiki.app_compile``:

- ``review_page``

Migration invariants (same as B1..B6):

- Dependencies imported from their **true origin** module, not via a
  re-export chain. In particular:
  * ``append_wiki_log`` comes from ``..app_render`` — ``app_content``
    re-exports it but ``app_render`` is the runtime-effective origin
    (B2 / B5 / B6 rule). Cross-group tech debt in B3 / B4 is separate.
  * ``compile_wiki`` comes from ``..compile.pipeline``, not from the
    ``..compile`` package ``__init__`` re-export (B4 oracle rule).
  * ``extract_provenance_paths`` / ``build_citation_snapshots`` /
    ``analyze_citation_snapshots`` come from ``..app_utils``.
  * ``append_review_history_entry`` / ``review_history_entries`` /
    ``entry_lookup_maps`` / ``entry_ids_from_paths`` come from
    ``..app_content``.
- ``utc_now`` is resolved lazily at **call time** via
  ``from .. import app_compile as _app_compile; _app_compile.utc_now()``
  so that ``patch("aiwiki.app_compile.utc_now", ...)`` in
  ``tests/test_app.py`` continues to take effect after the owner flip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_content import (
    append_review_history_entry,
    entry_ids_from_paths,
    entry_lookup_maps,
    review_history_entries,
)
from ..app_lifecycle import judgment_lifecycle_profile, valid_curated_statuses
from ..app_protocol import ensure_layout, schedule_review_windows
from ..app_render import append_wiki_log
from ..app_state import DEFAULT_PROTOCOL, append_runtime_history, load_manifest
from ..app_utils import (
    analyze_citation_snapshots,
    build_citation_snapshots,
    extract_provenance_paths,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..compile.pipeline import compile_wiki


@runtime_write_operation
def review_page(
    root: Path,
    page: str,
    status: str,
    *,
    note: str | None = None,
    confidence: str | None = None,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    candidate = Path(page)
    target = candidate if candidate.is_absolute() else (root / candidate)
    target = target.resolve()
    if not target.is_file():
        raise FileNotFoundError(f"Review target not found: {page}")
    content = target.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    kind = str(frontmatter.get("kind") or "")
    if kind == "derived":
        raise ValueError(
            f"Page kind 'derived' is the machine-memory terminal layer and is not subject to review-page workflow. "
            f"To enter review, file the artifact back with --kind judgment or --kind decision instead. "
            f"(page: {target})"
        )
    if kind not in {"decision", "judgment"}:
        raise ValueError(
            "Only decision or judgment pages can enter the review workflow; "
            "expected one of: ('decision', 'judgment')"
        )
    valid_statuses = valid_curated_statuses(kind)
    if status not in valid_statuses:
        raise ValueError(
            f"Unsupported review status for {kind}: {status!r}; "
            f"expected one of: {tuple(valid_statuses)}"
        )
    reviewed_at = _app_compile.utc_now()
    frontmatter["status"] = status
    frontmatter["reviewed_at"] = reviewed_at
    frontmatter["formed_at"] = str(frontmatter.get("formed_at") or frontmatter.get("last_compiled_at") or reviewed_at)
    frontmatter["last_reviewed"] = reviewed_at
    frontmatter.setdefault("counter_evidence", [])
    frontmatter.setdefault("invalidation_rule", "")
    frontmatter.setdefault("next_signals", [])
    if kind == "judgment" and confidence:
        frontmatter["confidence"] = confidence
    revisit_after, escalate_after = schedule_review_windows(
        kind,
        status,
        reviewed_at,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        root=root,
    )
    frontmatter["revisit_after"] = revisit_after
    frontmatter["escalate_after"] = escalate_after
    body = strip_frontmatter(content).strip()
    review_status_lines = [
        f"- Current status: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if confidence and kind == "judgment":
        review_status_lines.append(f"- Confidence: `{confidence}`")
    review_notes_lines = [
        f"- Outcome: `{status}`",
        f"- Reviewed at: `{reviewed_at}`",
    ]
    if note:
        review_notes_lines.append(f"- Note: {note}")
    else:
        review_notes_lines.append("- No additional review note recorded.")
    updated_body = upsert_markdown_section(body, "Review Status", "\n".join(review_status_lines))
    updated_body = upsert_markdown_section(updated_body, "Review Notes", "\n".join(review_notes_lines))
    updated_body = upsert_markdown_section(
        updated_body,
        "Aging",
        "\n".join(
            [
                f"- Revisit after: `{revisit_after or 'none'}`",
                f"- Escalate after: `{escalate_after or 'none'}`",
            ]
        ),
    )
    updated_body = append_review_history_entry(
        updated_body,
        reviewed_at=reviewed_at,
        status=status,
        note=note,
        confidence=confidence if kind == "judgment" else None,
    )
    citations = extract_provenance_paths(root, updated_body)
    frontmatter["citations"] = citations
    frontmatter["citation_snapshots"] = build_citation_snapshots(root, citations)
    citation_snapshot_state = analyze_citation_snapshots(root, citations, frontmatter)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(
        {
            "kind": kind,
            "status": status,
            "reviewed_at": reviewed_at,
            "last_reviewed": reviewed_at,
            "overdue_review": "false",
            "escalation_candidate": "false",
            "citation_drift": "true" if citation_snapshot_state["has_drift"] else "false",
            "citation_snapshot_gap_count": str(
                len(citation_snapshot_state["missing"]) + len(citation_snapshot_state["stale"])
            ),
            "review_history_entries": str(len(review_history_entries(updated_body))),
        }
    )
    target.write_text(f"{render_frontmatter(frontmatter)}\n\n{updated_body.strip()}\n", encoding="utf-8")
    _entry_by_id, path_to_entry_id = entry_lookup_maps(load_manifest(root).get("entries", []))
    source_ids = entry_ids_from_paths(path_to_entry_id, citations)
    append_runtime_history(
        root,
        {
            "event_type": "review",
            "occurred_at": reviewed_at,
            "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            "page_id": str(frontmatter.get("id") or target.stem),
            "page_path": relative_path(root, target),
            "page_kind": kind,
            "status": status,
            "judgment_lifecycle_state": judgment_lifecycle_state,
            "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
            "source_ids": source_ids,
        },
    )
    append_wiki_log(
        root,
        "review",
        str(frontmatter.get("title") or target.stem),
        [
            f"kind: `{kind}`",
            f"status: `{status}`",
            f"path: `{relative_path(root, target)}`",
            f"confidence: `{frontmatter.get('confidence', '') or 'n/a'}`",
        ],
    )
    compile_wiki(root)
    return {
        "path": relative_path(root, target),
        "kind": kind,
        "status": status,
        "reviewed_at": reviewed_at,
        "confidence": str(frontmatter.get("confidence") or ""),
    }
