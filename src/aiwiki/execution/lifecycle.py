"""EP-018B3: lifecycle execution surface moved out of ``app_compile``.

This module owns the lifecycle-facing execution entry points:

* :func:`refresh_knowledge_lifecycle_runtime`
* :func:`retire_concept`
* :func:`reactivate_concept`
* :func:`review_concept` (Round 7 / P4-19b)
* :func:`review_concepts_batch` (Round 7 / P4-19b)

They were previously defined in :mod:`aiwiki.app_compile`. The monolithic
module now exposes them lazily through ``_LAZY_OWNERS`` so existing
callers (``aiwiki.app_compile.retire_concept(...)`` etc.) keep working
without re-importing.

Import policy (mirrors EP-018B1/B2):

* Helpers whose *true* origin is another module are imported directly
  from that module (not round-tripped through ``app_compile``).
* The single hot-patch target used by this group — ``utc_now`` — is
  looked up lazily inside each function body via
  ``from .. import app_compile as _app_compile; _app_compile.utc_now()``
  so that ``patch("aiwiki.app_compile.utc_now")`` in
  ``tests/test_app.py`` still intercepts the call through the migrated
  path.
* Intra-group calls (``retire_concept`` / ``reactivate_concept`` call
  ``refresh_knowledge_lifecycle_runtime``) resolve against the local
  module, which also guarantees the hot-patch seam works when tests
  patch ``utc_now`` at the ``app_compile`` namespace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_content import append_wiki_log, sync_manifest_with_raw
from ..app_lifecycle import refresh_knowledge_lifecycle_state
from ..app_memory import concept_lifecycle_entry, concept_page_path
from ..app_protocol import ensure_layout
from ..app_state import (
    append_runtime_history,
    ensure_knowledge_lifecycle_override_state,
    knowledge_lifecycle_override_state_path,
    knowledge_lifecycle_state_path,
    load_active_corpora_state,
    load_machine_memory,
    save_knowledge_lifecycle_override_state,
)
from ..app_utils import relative_path, runtime_write_operation


def refresh_knowledge_lifecycle_runtime(
    root: Path, *, generated_at: str | None = None
) -> dict[str, Any]:
    # Hot-patch seam: ``utc_now`` is patched in tests via
    # ``patch("aiwiki.app_compile.utc_now")``. Lazy import preserves that.
    from .. import app_compile as _app_compile

    manifest = sync_manifest_with_raw(root)
    return refresh_knowledge_lifecycle_state(
        root,
        generated_at=generated_at or _app_compile.utc_now(),
        entries=manifest["entries"],
        active_corpora_state=load_active_corpora_state(root),
        memory=load_machine_memory(root),
    )


@runtime_write_operation
def retire_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    lifecycle = refresh_knowledge_lifecycle_runtime(root)
    current_entry = concept_lifecycle_entry(lifecycle, slug)
    if not current_entry:
        raise RuntimeError(f"Concept lifecycle entry not found: {slug}")
    if current_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus concept cannot transition to retired.")
    if str(current_entry.get("lifecycle_state") or "") == "retired" and current_entry.get(
        "override_active"
    ):
        raise RuntimeError(f"Concept is already retired: {slug}")

    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [
        dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)
    ]
    retired_at = _app_compile.utc_now()
    path_ref = relative_path(root, path)
    page_id = str(current_entry.get("page_id") or f"concept-{slug}")
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        ):
            entry["active"] = False
            entry["cleared_at"] = retired_at
            entry["cleared_note"] = "Superseded by newer concept lifecycle override."
    override_entries.append(
        {
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "kind": "concept",
            "lifecycle_state": "retired",
            "active": True,
            "operation": "retire",
            "reason_codes": ["manual-retire"],
            "applied_at": retired_at,
            "updated_at": retired_at,
            "note": note or "Concept retired from the active knowledge plane.",
        }
    )
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=retired_at)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": retired_at,
            "operation": "retire",
            "kind": "concept",
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": "retired",
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-retire",
        str(current_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            "lifecycle_state: `retired`",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or "retired"),
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": retired_at,
    }


@runtime_write_operation
def reactivate_concept(root: Path, slug: str, *, note: str | None = None) -> dict[str, Any]:
    """Clear *any* active concept lifecycle override and route the concept
    back to heuristic lifecycle classification.

    Round 8 widened the filter from ``lifecycle_state == "retired"`` to
    "any active concept override on this path". This closes the
    Round 7 / P4-19b reversibility gap: ``review-concept`` writes
    ``active/deferred/review`` overrides which previously could only be
    cleared by hand-editing ``wiki/state/knowledge_lifecycle_override.json``.

    Behaviour notes:

    * If multiple active overrides target the same concept path
      (history bug / hand-edit), all of them are deactivated in one pass.
      ``cleared_lifecycle_state`` reports the *last* match — that is
      the one ``active_knowledge_lifecycle_overrides()`` actually pinned
      (later entries win in its dict comprehension).
    * Once cleared, ``apply_knowledge_lifecycle_override`` returns the
      raw heuristic entry, so the concept rejoins the normal
      revisit/review/active routing.
    """
    from .. import app_compile as _app_compile

    ensure_layout(root)
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [
        dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)
    ]
    path_ref = relative_path(root, path)
    matches: list[dict[str, Any]] = [
        entry
        for entry in override_entries
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        )
    ]
    if not matches:
        raise RuntimeError(f"No active concept lifecycle override exists for slug: {slug}")
    target = matches[-1]
    cleared_state = str(target.get("lifecycle_state") or "")
    reactivated_at = _app_compile.utc_now()
    for entry in matches:
        entry["active"] = False
        entry["reactivated_at"] = reactivated_at
        entry["reactivate_note"] = (
            note or "Concept reactivated into heuristic lifecycle routing."
        )
        entry["updated_at"] = reactivated_at
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=reactivated_at)
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug)
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": reactivated_at,
            "operation": "reactivate",
            "kind": "concept",
            "page_id": str(target.get("page_id") or f"concept-{slug}"),
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": str(final_entry.get("lifecycle_state") or ""),
            "cleared_lifecycle_state": cleared_state,
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-reactivate",
        str(final_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `{str(final_entry.get('lifecycle_state') or 'unknown')}` "
            f"(cleared `{cleared_state or 'unknown'}` override)",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or ""),
        "cleared_lifecycle_state": cleared_state,
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": reactivated_at,
    }


# ---------------------------------------------------------------------------
# Round 7 / P4-19b: review-concept manual ack workflow
#
# Why this exists:
#   ``revisit_concepts`` and ``review_concepts`` buckets in the review queue
#   are populated by *heuristic* concept lifecycle classification (see
#   ``concept_lifecycle_classification`` in ``app_lifecycle``). Before
#   Round 7 the user could only ack a concept by ``retire-concept``, but
#   retire (a) is blocked when the concept is in an active corpus, and
#   (b) is semantically wrong for "I've seen this signal, route it back
#   to normal lifecycle".
#
#   ``review_concept`` writes an active concept lifecycle override pinning
#   ``lifecycle_state`` to the user-chosen target (active / deferred /
#   review). The override is consumed by
#   ``apply_knowledge_lifecycle_override`` and pulls the concept out of
#   the revisit/review buckets at the next compile/refresh.
#
# Reversibility:
#   ``reactivate-concept`` (Round 8) clears *any* active concept lifecycle
#   override on a path, including review-ack overrides written here. It
#   is the symmetric inverse of both ``retire-concept`` and
#   ``review-concept``.
#
# Status set:
#   ``retired`` is intentionally excluded — that path goes through
#   ``retire-concept`` (which keeps the active-corpus guard).
#   ``revisit`` is also excluded — that is the heuristic-only state and
#   ack:ing into ``revisit`` would be a no-op user-facing.
# ---------------------------------------------------------------------------

REVIEW_CONCEPT_STATUSES: tuple[str, ...] = ("active", "deferred", "review")


@runtime_write_operation
def review_concept(
    root: Path,
    slug: str,
    *,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    from .. import app_compile as _app_compile

    ensure_layout(root)
    if status not in REVIEW_CONCEPT_STATUSES:
        raise ValueError(
            f"Unsupported review-concept status: {status!r}; "
            f"expected one of: {REVIEW_CONCEPT_STATUSES}"
        )
    path = concept_page_path(root, slug)
    if not path.exists():
        raise FileNotFoundError(f"Concept page not found: {relative_path(root, path)}")
    lifecycle = refresh_knowledge_lifecycle_runtime(root)
    current_entry = concept_lifecycle_entry(lifecycle, slug)
    if not current_entry:
        raise RuntimeError(f"Concept lifecycle entry not found: {slug}")
    if (
        str(current_entry.get("lifecycle_state") or "") == "retired"
        and current_entry.get("override_active")
    ):
        raise RuntimeError(
            f"Concept is retired: {slug}. Use reactivate-concept first if you want to review it."
        )

    override_state = ensure_knowledge_lifecycle_override_state(root)
    override_entries = [
        dict(entry) for entry in override_state.get("entries", []) if isinstance(entry, dict)
    ]
    reviewed_at = _app_compile.utc_now()
    path_ref = relative_path(root, path)
    page_id = str(current_entry.get("page_id") or f"concept-{slug}")
    for entry in override_entries:
        if (
            bool(entry.get("active"))
            and str(entry.get("kind") or "") == "concept"
            and str(entry.get("path") or "") == path_ref
        ):
            entry["active"] = False
            entry["cleared_at"] = reviewed_at
            entry["cleared_note"] = "Superseded by newer concept lifecycle override."
    override_entries.append(
        {
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "kind": "concept",
            "lifecycle_state": status,
            "active": True,
            "operation": "review",
            "reason_codes": ["manual-review-ack"],
            "applied_at": reviewed_at,
            "updated_at": reviewed_at,
            "note": note or f"Concept review-ack: routed to {status}.",
        }
    )
    save_knowledge_lifecycle_override_state(root, {"version": 1, "entries": override_entries})
    updated_lifecycle = refresh_knowledge_lifecycle_runtime(root, generated_at=reviewed_at)
    final_entry = concept_lifecycle_entry(updated_lifecycle, slug) or current_entry
    derived_state = str(current_entry.get("lifecycle_state") or "")
    append_runtime_history(
        root,
        {
            "event_type": "knowledge-lifecycle-override",
            "occurred_at": reviewed_at,
            "operation": "review",
            "kind": "concept",
            "page_id": page_id,
            "slug": slug,
            "path": path_ref,
            "lifecycle_state": status,
            "derived_lifecycle_state": derived_state,
            "note": note or "",
        },
    )
    append_wiki_log(
        root,
        "concept-review",
        str(current_entry.get("title") or slug),
        [
            f"slug: `{slug}`",
            f"path: `{path_ref}`",
            f"lifecycle_state: `{status}` (was `{derived_state}`)",
            f"override_state: `{relative_path(root, knowledge_lifecycle_override_state_path(root))}`",
        ],
    )
    return {
        "slug": slug,
        "path": path_ref,
        "status": str(final_entry.get("lifecycle_state") or status),
        "derived_lifecycle_state": derived_state,
        "override_path": relative_path(root, knowledge_lifecycle_override_state_path(root)),
        "knowledge_lifecycle_path": relative_path(root, knowledge_lifecycle_state_path(root)),
        "updated_at": reviewed_at,
    }


@runtime_write_operation
def review_concepts_batch(
    root: Path,
    slugs: list[str],
    *,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Batch wrapper around :func:`review_concept` (fail-fast).

    Mirrors ``review_pages_batch`` shape: dedupes input order-preserving,
    aborts on first failure, returns ``{slugs, receipts, count}``.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in slugs:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    if not ordered:
        raise ValueError("Batch review-concept requires at least one slug.")
    receipts: list[dict[str, Any]] = []
    for slug in ordered:
        receipts.append(review_concept(root, slug, status=status, note=note))
    return {
        "slugs": ordered,
        "receipts": receipts,
        "count": len(receipts),
        "status": status,
    }
