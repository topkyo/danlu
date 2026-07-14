"""EP-018B7: page review execution owner.

Owns the single-page review entry point that used to live in
``aiwiki.app_compile``:

- ``review_page``

Migration invariants (same as B1..B6):

- Dependencies imported from their **true origin** module, not via a
  re-export chain. In particular:
  * ``append_wiki_log`` comes from ``..render.paths``; legacy facades
    keep re-exporting it for external compatibility.
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

import contextlib
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
from ..app_state import (
    DEFAULT_PROTOCOL,
    append_runtime_history,
    execution_receipt_history_path,
    load_manifest,
    runtime_history_path,
)
from ..app_utils import (
    _restore_snapshots,
    _snapshot_file_bytes,
    analyze_citation_snapshots,
    build_citation_snapshots,
    extract_provenance_paths,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
    runtime_write_operation,
    sha256_bytes,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..compile.pipeline import compile_wiki
from ..lifecycle.templates import (
    curated_frontmatter_hints,
    curated_structured_value_is_placeholder,
    repair_curated_page_body,
)
from ..render.paths import append_wiki_log
from .audit_preview import AUDIT_STREAM_PATH
from .receipts import write_execution_receipt


def _curated_hint_source_body(body: str) -> str:
    if "## Supporting Artifact" in body:
        return body.split("## Supporting Artifact", 1)[0].strip()
    return body


def _curated_supporting_body(body: str) -> str:
    if "## Supporting Artifact" in body:
        return body.split("## Supporting Artifact", 1)[1].strip()
    return body


def _normalized_curated_value(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return ""
    return str(value).strip()


def _curated_value_is_empty(value: Any) -> bool:
    normalized = _normalized_curated_value(value)
    if isinstance(normalized, list):
        return not normalized
    return not normalized


def _should_refresh_curated_hint(current: Any, previous_hint: Any) -> bool:
    return (
        _curated_value_is_empty(current)
        or curated_structured_value_is_placeholder(current)
        or _normalized_curated_value(current) == _normalized_curated_value(previous_hint)
    )


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
            f"To enter review, run file-back --kind judgment or file-back --kind decision instead. "
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
    previous_supporting_body = _curated_supporting_body(body)
    previous_hints = curated_frontmatter_hints(
        kind=kind,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        supporting_body=previous_supporting_body,
    )
    artifact_refs = [str(item) for item in frontmatter.get("source_files", []) if isinstance(item, str) and item.strip()]
    body = repair_curated_page_body(
        kind=kind,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        body=body,
        artifact_ref=artifact_refs[0] if artifact_refs else relative_path(root, target),
        revisit_after=revisit_after,
        escalate_after=escalate_after,
    )
    repaired_hints = curated_frontmatter_hints(
        kind=kind,
        protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
        supporting_body=_curated_hint_source_body(body),
    )
    for hint_key, hint_value in repaired_hints.items():
        if _should_refresh_curated_hint(frontmatter.get(hint_key), previous_hints.get(hint_key)):
            frontmatter[hint_key] = hint_value
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
    snapshots = {
        target: _snapshot_file_bytes(target),
        runtime_history_path(root): _snapshot_file_bytes(runtime_history_path(root)),
        root / "wiki" / "indexes" / "log.md": _snapshot_file_bytes(root / "wiki" / "indexes" / "log.md"),
        execution_receipt_history_path(root): _snapshot_file_bytes(execution_receipt_history_path(root)),
        root / AUDIT_STREAM_PATH: _snapshot_file_bytes(root / AUDIT_STREAM_PATH),
    }
    receipt: dict[str, Any] | None = None
    try:
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
        review_subject_kind = "judgment_review" if kind == "judgment" else "decision_review"
        before_bytes = snapshots.get(target)
        after_bytes = target.read_bytes()
        receipt = write_execution_receipt(
            root,
            operation="review-page",
            generated_by="aiwiki-review-page",
            subject_kind=review_subject_kind,
            subject_id=str(frontmatter.get("id") or target.stem),
            target_file=relative_path(root, target),
            primary_path=relative_path(root, target),
            protocol=str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
            extra={
                "domain": "non_core_semantic" if kind == "judgment" else "governance",
                "page_kind": kind,
                "conclusion": status,
                "confidence": str(frontmatter.get("confidence") or ""),
                "reviewed_at": reviewed_at,
                "citation_count": len(citations),
                "target_paths": [relative_path(root, target)],
                "before_hash": sha256_bytes(before_bytes) if before_bytes is not None else "",
                "after_hash": sha256_bytes(after_bytes),
                "source_provenance": {"citations": citations, "source_ids": source_ids},
                "llm_receipt_id": "",
                "autonomy_decision": {
                    "autonomy_domain": "non_core_semantic" if kind == "judgment" else "governance",
                    "execution_strategy": "semantic_review",
                    "llm_governed": False,
                },
                "revert_ref": "",
            },
        )
        compile_wiki(root)
    except Exception as transaction_error:
        if receipt:
            receipt_path = str(receipt.get("receipt_path") or "")
            if receipt_path:
                with contextlib.suppress(FileNotFoundError):
                    (root / receipt_path).unlink()
        try:
            _restore_snapshots(snapshots)
        except Exception as rollback_error:
            raise RuntimeError(
                f"review-page rollback failed for {relative_path(root, target)}: "
                f"transaction_error={transaction_error!r}; rollback_error={rollback_error!r}"
            ) from rollback_error
        raise
    return {
        "path": relative_path(root, target),
        "kind": kind,
        "status": status,
        "reviewed_at": reviewed_at,
        "confidence": str(frontmatter.get("confidence") or ""),
        "receipt_path": str(receipt.get("receipt_path") or ""),
    }
