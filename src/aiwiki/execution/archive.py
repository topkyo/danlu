"""EP-018B4: material-archive execution surface moved out of ``app_compile``.

This module owns the two material-archive execution entry points:

* :func:`apply_material_archive`
* :func:`revert_material_archive`

They were previously defined in :mod:`aiwiki.app_compile` and have since
been migrated here as the canonical owner. Callers should import directly
from :mod:`aiwiki.execution.archive`.

Import policy (mirrors EP-018B1/B2/B3):

* Helpers whose *true* origin is another module are imported directly
  from that module (not round-tripped through ``app_compile``).
* The single hot-patch target used by this group — ``utc_now`` — is
  looked up lazily inside each function body via
  ``from ..utils.time import utc_now; utc_now()``
  so that ``patch("aiwiki.utils.time.utc_now")`` patches
  (acceptance tests + downstream suites) still intercept the call
  through the migrated path.
* ``execution_bundle_path`` / ``execution_receipt_path`` / ``append_wiki_log``
  have dual definitions in the codebase (``app_content`` and
  ``app_render``). This migration keeps the ``app_content`` source that
  ``app_compile`` originally imported from — the pre-existing duplicate
  is a known technical-debt item, out-of-scope for EP-018B.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..app_execution import (
    append_execution_receipt_history,
    build_material_archive_bundle,
    build_material_archive_receipt,
    write_execution_bundle_document,
    write_execution_dry_run_document,
)
from ..app_protocol import ensure_layout, load_protocol_state
from ..app_queries import wiki_requires_compile
from ..app_state_paths import (
    archive_candidates_state_path,
    archive_dry_run_path,
    material_archive_action_id,
    material_state_path,
)
from ..compile.pipeline import compile_wiki
from ..content.archive import (
    active_material_archive_entries,
    load_archive_candidates_state,
    load_material_archive_state,
    save_material_archive_state,
)
from ..content.io import sync_manifest_with_raw
from ..content.material import load_material_state
from ..render.paths import (
    append_wiki_log,
    execution_bundle_path,
    execution_receipt_path,
)
from ..state.constants import DEFAULT_PROTOCOL
from ..state.io import load_json_document_strict
from ..state.manifest import load_manifest
from ..utils.io import atomic_write_text, runtime_write_operation
from ..utils.path import relative_path
from .history import append_runtime_history

logger = logging.getLogger(__name__)


@runtime_write_operation
def apply_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    # Hot-patch seam: ``utc_now`` is patched via
    # ``patch("aiwiki.utils.time.utc_now")``. Lazy import preserves it.
    from ..utils.time import utc_now

    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if (
        wiki_requires_compile(root, manifest["entries"])
        or not material_state_path(root).exists()
        or not archive_candidates_state_path(root).exists()
    ):
        compile_wiki(root)
        manifest = load_manifest(root)

    archive_candidates = load_archive_candidates_state(root)
    material_state = load_material_state(root)
    material_archive_state = load_material_archive_state(root)
    archived_entries = active_material_archive_entries(material_archive_state)
    if entry_id in archived_entries:
        raise RuntimeError(f"Material is already archived: {entry_id}")

    candidate = next(
        (
            item
            for item in archive_candidates.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if candidate is None:
        raise FileNotFoundError(f"Archive candidate not found: {entry_id}")
    if str(candidate.get("status") or "") != "ready":
        raise RuntimeError("Only ready archive candidates support apply.")
    if str(candidate.get("recommended_temperature") or "") != "archived":
        raise RuntimeError("Only archive candidates recommending `archived` support apply.")

    material_entry = next(
        (
            item
            for item in material_state.get("entries", [])
            if isinstance(item, dict) and str(item.get("entry_id") or "") == entry_id
        ),
        None,
    )
    if material_entry is None:
        raise FileNotFoundError(f"Material state entry not found: {entry_id}")
    if str(material_entry.get("temperature") or "") != "cold":
        raise RuntimeError("Only cold material can transition to archived.")
    if material_entry.get("active_corpus_ids"):
        raise RuntimeError("Active-corpus material cannot transition to archived.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or entry_id)
    source_path = f"wiki/sources/{entry_id}.md"
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    applied_at = utc_now()
    bundle = build_material_archive_bundle(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    if dry_run:
        bundle_path = root / str(
            bundle.get("bundle_path")
            or relative_path(root, execution_bundle_path(root, material_archive_action_id(entry_id)))
        )
        write_execution_bundle_document(bundle_path, bundle)
        dry_run_path = archive_dry_run_path(root, entry_id)
        dry_run_payload = {
            "version": 1,
            "kind": "archive-dry-run",
            "generated_by": "aiwiki-apply-archive",
            "generated_at": applied_at,
            "entry_id": entry_id,
            "title": title,
            "status": str(candidate.get("status") or ""),
            "protocol": protocol,
            "bundle_path": relative_path(root, bundle_path),
            "preview": bundle.get("safe_apply_preview"),
            "bundle": bundle,
        }
        write_execution_dry_run_document(dry_run_path, dry_run_payload)
        append_runtime_history(
            root,
            {
                "event_type": "archive-dry-run",
                "occurred_at": applied_at,
                "protocol": protocol,
                "source_ids": [entry_id],
                "bundle_path": relative_path(root, bundle_path),
                "preview_path": relative_path(root, dry_run_path),
                "note": note or "",
            },
        )
        append_wiki_log(
            root,
            "archive-dry-run",
            title,
            [
                f"entry_id: `{entry_id}`",
                f"source: `{source_path}`",
                f"bundle: `{relative_path(root, bundle_path)}`",
            ],
        )
        return {
            "id": entry_id,
            "status": str(candidate.get("status") or ""),
            "dry_run": True,
            "bundle_path": relative_path(root, bundle_path),
            "dry_run_path": relative_path(root, dry_run_path),
        }
    receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        operation="apply",
        current_temperature="cold",
        resulting_temperature="archived",
    )
    receipt_path = execution_receipt_path(root, material_archive_action_id(entry_id))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    archive_entries = [
        dict(item)
        for item in material_archive_state.get("entries", [])
        if isinstance(item, dict) and str(item.get("entry_id") or "") != entry_id
    ]
    archive_entries.append(
        {
            "entry_id": entry_id,
            "title": title,
            "source_path": source_path,
            "active": True,
            "archived_at": applied_at,
            "reverted_at": "",
            "previous_temperature": "cold",
            "note": note or "",
            "recommended_temperature": "archived",
            "last_receipt_path": relative_path(root, receipt_path),
        }
    )

    # R95.1: phase 1 = receipt file write -> state save (TX). Failure here
    # rolls back the receipt file so we don't leave an orphan apply receipt
    # claiming success when state never committed.
    wrote_receipt = False
    try:
        atomic_write_text(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        wrote_receipt = True
        save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    except BaseException:
        if wrote_receipt:
            try:
                receipt_path.unlink(missing_ok=True)
            except BaseException as rollback_exc:
                logger.warning(
                    "archive apply receipt unlink failed for %s: %s (%s)",
                    receipt_path,
                    rollback_exc,
                    type(rollback_exc).__name__,
                )
        raise

    # R95.1: phase 2 = best-effort audit/derived. State is already SOT;
    # raising here would mislead the caller into retry against an
    # already-archived entry, which would fail at active_material_archive
    # check with a confusing error. Per-step warning preserves observability.
    for step_name, step_fn in (
        ("append_execution_receipt_history", lambda: append_execution_receipt_history(root, receipt)),
        (
            "append_runtime_history",
            lambda: append_runtime_history(
                root,
                {
                    "event_type": "archive-apply",
                    "occurred_at": applied_at,
                    "protocol": protocol,
                    "source_ids": [entry_id],
                    "receipt_path": relative_path(root, receipt_path),
                },
            ),
        ),
        (
            "append_wiki_log",
            lambda: append_wiki_log(
                root,
                "archive-apply",
                title,
                [
                    f"entry_id: `{entry_id}`",
                    f"source: `{source_path}`",
                    "temperature: `cold -> archived`",
                    f"receipt: `{relative_path(root, receipt_path)}`",
                ],
            ),
        ),
        ("compile_wiki", lambda: compile_wiki(root)),
    ):
        try:
            step_fn()
        except Exception as phase2_exc:
            logger.warning(
                "archive apply phase 2 step %s failed for %s: %s (%s); state already saved",
                step_name,
                entry_id,
                phase2_exc,
                type(phase2_exc).__name__,
            )
    return {
        "id": entry_id,
        "status": "archived",
        "applied_at": applied_at,
        "receipt_path": relative_path(root, receipt_path),
    }


@runtime_write_operation
def revert_material_archive(
    root: Path,
    entry_id: str,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    from ..utils.time import utc_now

    ensure_layout(root)
    manifest = sync_manifest_with_raw(root)
    if wiki_requires_compile(root, manifest["entries"]) or not material_state_path(root).exists():
        compile_wiki(root)
        manifest = load_manifest(root)

    material_archive_state = load_material_archive_state(root)
    archive_entries = [dict(item) for item in material_archive_state.get("entries", []) if isinstance(item, dict)]
    target = next((item for item in archive_entries if str(item.get("entry_id") or "") == entry_id), None)
    if target is None or not bool(target.get("active", False)):
        raise RuntimeError(f"No active archived material exists for entry: {entry_id}")

    receipt_relative = str(target.get("last_receipt_path") or "")
    if not receipt_relative:
        raise RuntimeError("Archived material has no execution receipt to revert.")
    apply_receipt_path = root / receipt_relative
    if not apply_receipt_path.exists():
        raise FileNotFoundError(f"Execution receipt not found: {receipt_relative}")
    apply_receipt = load_json_document_strict(apply_receipt_path)
    if not isinstance(apply_receipt, dict) or str(apply_receipt.get("kind") or "") != "execution-receipt":
        raise RuntimeError("Execution receipt is not valid.")
    if str(apply_receipt.get("operation") or "") != "apply":
        raise RuntimeError("Only the latest apply archive receipt can be reverted.")
    if str(apply_receipt.get("subject_id") or "") != entry_id:
        raise RuntimeError("Execution receipt subject_id does not match the requested entry.")

    manifest_entry = next(
        (
            item
            for item in manifest.get("entries", [])
            if isinstance(item, dict) and str(item.get("id") or "") == entry_id
        ),
        {},
    )
    title = str(manifest_entry.get("title") or target.get("title") or entry_id)
    source_path = str(target.get("source_path") or f"wiki/sources/{entry_id}.md")
    protocol = str(load_protocol_state(root)["active_protocol"] or DEFAULT_PROTOCOL)
    reverted_at = utc_now()
    revert_receipt = build_material_archive_receipt(
        root,
        entry_id=entry_id,
        title=title,
        source_path=source_path,
        protocol=protocol,
        applied_at=reverted_at,
        note=note,
        operation="revert",
        current_temperature="archived",
        resulting_temperature="cold",
    )
    revert_receipt_path = apply_receipt_path.parent / "reverts" / apply_receipt_path.name
    revert_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    revert_receipt["receipt_path"] = relative_path(root, revert_receipt_path)

    target["active"] = False
    target["reverted_at"] = reverted_at
    target["revert_note"] = note or "Material archive reverted."
    target["last_receipt_path"] = relative_path(root, revert_receipt_path)

    # R95.1: phase 1 = revert receipt file write -> state save (TX). Failure
    # here unlinks the orphan revert receipt; target dict mutations live in
    # local memory only, so no in-memory rollback is needed (the next call
    # reloads from disk).
    wrote_receipt = False
    try:
        atomic_write_text(
            revert_receipt_path,
            json.dumps(revert_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        wrote_receipt = True
        save_material_archive_state(root, {"version": 1, "entries": archive_entries})
    except BaseException:
        if wrote_receipt:
            try:
                revert_receipt_path.unlink(missing_ok=True)
            except BaseException as rollback_exc:
                logger.warning(
                    "archive revert receipt unlink failed for %s: %s (%s)",
                    revert_receipt_path,
                    rollback_exc,
                    type(rollback_exc).__name__,
                )
        raise

    # R95.1: phase 2 = best-effort audit/derived. State is SOT; raising here
    # would mislead caller into retry which would fail at the active-archive
    # check.
    for step_name, step_fn in (
        ("append_execution_receipt_history", lambda: append_execution_receipt_history(root, revert_receipt)),
        (
            "append_runtime_history",
            lambda: append_runtime_history(
                root,
                {
                    "event_type": "archive-revert",
                    "occurred_at": reverted_at,
                    "protocol": protocol,
                    "source_ids": [entry_id],
                    "receipt_path": relative_path(root, revert_receipt_path),
                },
            ),
        ),
        (
            "append_wiki_log",
            lambda: append_wiki_log(
                root,
                "archive-revert",
                title,
                [
                    f"entry_id: `{entry_id}`",
                    f"source: `{source_path}`",
                    "temperature: `archived -> cold`",
                    f"receipt: `{relative_path(root, revert_receipt_path)}`",
                ],
            ),
        ),
        ("compile_wiki", lambda: compile_wiki(root)),
    ):
        try:
            step_fn()
        except Exception as phase2_exc:
            logger.warning(
                "archive revert phase 2 step %s failed for %s: %s (%s); state already saved",
                step_name,
                entry_id,
                phase2_exc,
                type(phase2_exc).__name__,
            )
    return {
        "id": entry_id,
        "status": "cold",
        "reverted_at": reverted_at,
        "receipt_path": relative_path(root, revert_receipt_path),
    }
