"""Alchemy execution — mutation layer.

Owns: filesystem writes, atomic rename, snapshot/restore, receipt persistence
for elixir lifecycle (start → distill → finalize → promote/demote/revert).

Boundary: mutation only. Higher-level orchestration lives in
``runner/alchemy.py``. Transactional helpers (``_snapshot_file_bytes`` /
``_restore_file_bytes``) live in ``aiwiki.utils.io``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path
from typing import Any

from ..execution.receipts import (
    build_elixir_demotion_receipt,
    build_elixir_promotion_receipt,
    build_elixir_revert_receipt,
    compute_file_sha256,
    find_latest_elixir_promotion_receipt,
)
from ..utils.hash import sha256_bytes
from ..utils.io import _restore_file_bytes, _snapshot_file_bytes
from ..utils.path import next_available_stem
from ..utils.text import slugify
from ..utils.time import utc_now  # noqa: F401
from .alchemy_cleanup import (
    apply_superseded_elixir_cleanup,
    preview_superseded_elixir_cleanup,
)
from .alchemy_helpers import (
    _ACTIVE_ELIXIR_STATES,
    _ELIXIR_SOURCE_PREFIXES,
    _PROMOTION_TS_FIELD,
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    ELIXIR_STATE_VALUES,
    DemoteHalfWriteError,
    DemoteReceiptError,
    LegacyMigrationApplyError,
    LegacyMigrationHalfWriteError,
    LegacyMigrationPlanError,
    LegacyMigrationReceiptError,
    PromoteHalfWriteError,
    PromoteReceiptError,
    RevertHalfWriteError,
    RevertReceiptError,
    SupersededCleanupApplyError,
    SupersededCleanupHalfWriteError,
    SupersededCleanupPlanError,
    SupersededCleanupReceiptError,
    _candidate_path,
    _collect_dependent_elixir_ids,
    _default_elixir_review_after,
    _detect_elixir_cycle,
    _elixir_body_has_pending_refinement,
    _find_corpus,
    _parse_elixir_frontmatter,
    _read_elixir_anywhere,
    _read_elixir_both_planes,
    _render_elixir_document,
    _resolve_elixir_id,
    _scaffold_elixir_markdown,
    _seed_elixir_body_from_sources,
    _settled_path,
    _validate_source_outputs,
    _validate_state_for_path,
    _write_atomic_text,
    _write_elixir_markdown,
    list_promoted_outputs_for_corpus,
    validate_promote_gate,
)
from .alchemy_migration import (
    apply_legacy_elixir_migration,
    preview_legacy_elixir_migration,
)
from .alchemy_receipts import _persist_receipt_transactionally

logger = logging.getLogger("aiwiki")

def start_elixir(
    root: Path,
    corpus_id: str,
    *,
    topic: str,
    protocol: str | None = None,
    include_elixir_ids: list[str] | None = None,
) -> dict[str, Any]:
    corpus = _find_corpus(root, corpus_id)  # validate corpus exists
    protocol_name = str(protocol or corpus.get("protocol") or "").strip()
    if not protocol_name:
        raise ValueError("protocol 不能为空")
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    if not promoted:
        raise ValueError(f"no promoted outputs for corpus {corpus_id}")
    source_outputs = [item["promoted_to"] for item in promoted if item.get("promoted_to")]
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for elixir_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, elixir_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{elixir_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {elixir_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    source_outputs = list(dict.fromkeys([*source_outputs, *include_paths]))
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith(_ELIXIR_SOURCE_PREFIXES) for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    candidate_dir = root / CANDIDATE_ELIXIR_DIR
    candidate_dir.mkdir(parents=True, exist_ok=True)
    seed = f"elixir-{slugify(topic)[:40]}-{sha256_bytes(topic.encode())[:8]}"
    elixir_id = next_available_stem(candidate_dir, seed)
    settled_path = _settled_path(root, elixir_id)
    candidate_path = _candidate_path(root, elixir_id)
    _norm = str(settled_path.relative_to(root))
    if _norm in {str(Path(ref)) for ref in source_outputs}:
        raise ValueError(f"cannot reference self: {_norm}")
    cycle = _detect_elixir_cycle(root, settled_path, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    if settled_path.exists() or candidate_path.exists():
        raise FileExistsError(f"elixir already exists: {elixir_id}")
    now = utc_now()
    candidate_path.write_text(
        _scaffold_elixir_markdown(
            elixir_id=elixir_id,
            protocol=protocol_name,
            topic=topic,
            corpus_id=corpus_id,
            source_outputs=source_outputs,
            iteration=0,
            elixir_state="draft",
            created_at=now,
            updated_at=now,
            body=_seed_elixir_body_from_sources(root, topic=topic, source_outputs=source_outputs),
        ),
        encoding="utf-8",
    )
    _validate_state_for_path(root, "draft", candidate_path)
    return {
        "elixir_id": elixir_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{elixir_id}.md",
        "derived_from": source_outputs,
        "iteration": 0,
        "elixir_state": "draft",
        "protocol": protocol_name,
    }


def distill_elixir(
    root: Path, elixir_id: str, *, question: str, include_elixir_ids: list[str] | None = None
) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    source_path, frontmatter = _read_elixir_anywhere(root, normalized_id)
    if source_path.resolve().parent == (root / ELIXIR_DIR).resolve():
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    source_state = str(frontmatter.get("elixir_state") or "")
    if source_state == "settled":
        raise ValueError(f"sealed elixir cannot be distilled: {elixir_id}")
    if source_state not in _ACTIVE_ELIXIR_STATES:
        raise ValueError(f"unsupported_source_state: cannot distill elixir from state={source_state or 'unknown'}")
    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    existing = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    # Defense-in-depth: refuse to distill an elixir whose existing provenance was
    # tampered empty or points outside the current corpus allowlist. Prevents
    # silent provenance loss via frontmatter edits.
    if not existing:
        raise ValueError(f"elixir has empty derived_from, refusing to distill: {elixir_id}")
    _validate_source_outputs(root, existing, allowed=allowed)
    include_elixir_ids = list(dict.fromkeys(include_elixir_ids or []))
    include_paths: list[str] = []
    for include_id in include_elixir_ids:
        include_id = _resolve_elixir_id(root, include_id)
        include_path = _settled_path(root, include_id)
        include_ref = f"wiki/elixirs/{include_id}.md"
        if not include_path.is_file():
            draft_candidate = _candidate_path(root, include_id)
            if draft_candidate.is_file():
                include_frontmatter = _parse_elixir_frontmatter(draft_candidate)
                state = include_frontmatter.get("elixir_state") or "unknown"
                raise ValueError(f"引用金丹 {include_ref} 当前状态为 {state}，只能引用 settled 金丹")
            raise FileNotFoundError(f"指定的金丹 {include_id} 不存在: {include_ref}")
        include_paths.append(include_ref)
    merged = list(dict.fromkeys([*existing, *allowed, *include_paths]))
    _validate_source_outputs(root, merged, allowed=allowed)
    if not any(ref.startswith(_ELIXIR_SOURCE_PREFIXES) for ref in merged):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")
    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in merged if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, merged)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))
    target_path = _candidate_path(root, normalized_id)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    iteration = int(frontmatter.get("iteration", 0) or 0) + 1
    history = frontmatter.get("distill_history") if isinstance(frontmatter.get("distill_history"), list) else []
    history = list(history)
    history.append({"iteration": iteration, "question": question, "at": utc_now()})
    frontmatter.update(
        {
            "iteration": iteration,
            "derived_from": merged,
            "elixir_state": "distilling",
            "updated_at": utc_now(),
            "distill_history": history,
        }
    )
    original = source_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1]
    body = body.lstrip("\n")
    if _elixir_body_has_pending_refinement(body):
        body = _seed_elixir_body_from_sources(root, topic=question, source_outputs=merged)
    _write_elixir_markdown(target_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "distilling", target_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "iteration": iteration,
        "derived_from": merged,
        "elixir_state": "distilling",
    }


def finalize_elixir(root: Path, *, elixir_id: str) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("unsupported_source_state: cannot finalize settled elixir")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)

    if source_state == "candidate":
        raise ValueError("already_candidate: elixir already finalized")
    if source_state not in {"draft", "distilling"}:
        raise ValueError(f"unsupported_source_state: cannot finalize elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith(_ELIXIR_SOURCE_PREFIXES) for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    # P4-INV-4 (Round 59): derive a protocol-aware default `review_after` when
    # the author did not set one explicitly, so the candidate carries a real
    # expiration anchor (Furnace Evolution Mechanics §7.2 target schema). Never
    # overwrite a value already in frontmatter.
    review_after_existing = str(frontmatter.get("review_after") or "").strip()
    review_after_value = review_after_existing or _default_elixir_review_after(
        protocol=str(frontmatter.get("protocol") or "general"),
    )

    frontmatter.update(
        {
            "elixir_state": "candidate",
            "updated_at": utc_now(),
            "review_after": review_after_value,
        }
    )
    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    _write_elixir_markdown(candidate_path, frontmatter=frontmatter, body=body)
    _validate_state_for_path(root, "candidate", candidate_path)
    return {
        "elixir_id": normalized_id,
        "path": f"{CANDIDATE_ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "candidate",
        "review_after": review_after_value,
    }


def promote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> dict[str, Any]:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    if settled_path.is_file():
        raise ValueError("already_promoted: settled elixir already exists")

    candidate_path = _candidate_path(root, normalized_id)
    if not candidate_path.is_file():
        raise FileNotFoundError(f"elixir not found: {normalized_id}")

    frontmatter = _parse_elixir_frontmatter(candidate_path)
    source_state = str(frontmatter.get("elixir_state") or "")
    _validate_state_for_path(root, source_state, candidate_path)
    if source_state != "candidate":
        raise ValueError(f"unsupported_source_state: cannot promote elixir from state={source_state or 'unknown'}")

    corpus_id = str(frontmatter.get("provenance_corpus") or "")
    _find_corpus(root, corpus_id)
    promoted = list_promoted_outputs_for_corpus(root, corpus_id)
    allowed = {item["promoted_to"] for item in promoted if item.get("promoted_to")}
    source_outputs = [str(item) for item in frontmatter.get("derived_from", []) if isinstance(item, str)]
    _validate_source_outputs(root, source_outputs, allowed=allowed)
    if not any(ref.startswith(_ELIXIR_SOURCE_PREFIXES) for ref in source_outputs):
        raise ValueError("金丹 derived_from 必须至少包含一个 wiki/derived/ 源条目（当前仅包含 elixir 引用）")

    canonical = _settled_path(root, normalized_id)
    if any(str(Path(ref)) == str(canonical.relative_to(root)) for ref in source_outputs if isinstance(ref, str)):
        raise ValueError(f"cannot reference self: {canonical.relative_to(root)}")
    cycle = _detect_elixir_cycle(root, canonical, source_outputs)
    if cycle:
        raise ValueError("金丹引用形成环路: " + " → ".join(cycle))

    validate_promote_gate(frontmatter)

    counter_evidence_items = [str(item).strip() for item in frontmatter.get("counter_evidence", [])]
    counter_evidence_provenance = "none_found" if counter_evidence_items == ["NONE_FOUND"] else "real"

    original = candidate_path.read_text(encoding="utf-8", errors="replace")
    body = original.split("---", 2)[-1].lstrip("\n")
    if _elixir_body_has_pending_refinement(body):
        raise ValueError("elixir_body_placeholder: cannot promote elixir with pending refinement body")
    applied_at_dt = datetime.now(timezone.utc)
    applied_at = applied_at_dt.isoformat()

    settled_frontmatter = dict(frontmatter)
    settled_frontmatter.pop("sealed_at", None)
    settled_frontmatter.update(
        {
            "elixir_state": "settled",
            "promoted_at": applied_at,
            "counter_evidence_provenance": counter_evidence_provenance,
        }
    )
    tombstone_frontmatter = dict(frontmatter)
    tombstone_frontmatter.pop("sealed_at", None)
    tombstone_frontmatter.update(
        {
            "elixir_state": "superseded",
            "superseded_by": f"{ELIXIR_DIR}/{normalized_id}.md",
            "promoted_at": applied_at,
        }
    )

    settled_text = _render_elixir_document(settled_frontmatter, body)
    tombstone_text = _render_elixir_document(tombstone_frontmatter, body)
    protocol = str(frontmatter.get("protocol") or "")

    settled_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot pre-mutation state for rollback on receipt-persist failure.
    settled_snapshot = _snapshot_file_bytes(settled_path)  # expected None: gate above ensured non-existence
    candidate_snapshot = _snapshot_file_bytes(candidate_path)  # expected non-None: gate above ensured candidate exists

    _write_atomic_text(settled_path, settled_text)
    try:
        _write_atomic_text(candidate_path, tombstone_text)
    except Exception as exc:
        try:
            _restore_file_bytes(settled_path, settled_snapshot)
        except Exception as rollback_exc:
            raise PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    _validate_state_for_path(root, "settled", settled_path)
    _validate_state_for_path(root, "superseded", candidate_path)

    def _rollback_promote_data() -> None:
        _restore_file_bytes(candidate_path, candidate_snapshot)
        _restore_file_bytes(settled_path, settled_snapshot)

    try:
        primary_hash = compute_file_sha256(settled_path)
        secondary_hash = compute_file_sha256(candidate_path)
        receipt = build_elixir_promotion_receipt(
            root,
            elixir_id=normalized_id,
            slug=slugify(normalized_id),
            settled_path=settled_path,
            candidate_path=candidate_path,
            protocol=protocol,
            applied_at=applied_at_dt,
            note=note,
            primary_path_sha256=primary_hash,
            secondary_path_sha256=secondary_hash,
            counter_evidence=counter_evidence_items,
            confidence_level=str(frontmatter.get("confidence_level") or "").strip(),
            counter_evidence_provenance=counter_evidence_provenance,
        )
        receipt_result_path = str(receipt.get("receipt_path") or "")
        _persist_receipt_transactionally(
            root,
            receipt=receipt,
            elixir_id=normalized_id,
            operation="promote",
            rollback_data=_rollback_promote_data,
            receipt_error_cls=PromoteReceiptError,
            half_write_error_factory=lambda phase: PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase=phase
            ),
        )
    except (PromoteReceiptError, PromoteHalfWriteError):
        raise
    except Exception as receipt_exc:
        logger.warning(
            "elixir promote receipt preparation failed for %s; rolling back mutation: %s",
            normalized_id,
            receipt_exc,
        )
        try:
            _rollback_promote_data()
        except Exception as rollback_exc:
            raise PromoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="receipt_rollback"
            ) from rollback_exc
        raise PromoteReceiptError(
            f"promote_receipt_error: receipt persistence failed for elixir {normalized_id}; mutation rolled back"
        ) from receipt_exc

    return {
        "elixir_id": normalized_id,
        "path": f"{ELIXIR_DIR}/{normalized_id}.md",
        "elixir_state": "settled",
        "promoted_at": applied_at,
        "receipt_path": receipt_result_path,
    }


def revert_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, _settled_body = settled_data

    latest_promotion = find_latest_elixir_promotion_receipt(root, elixir_id=normalized_id)
    if latest_promotion is None:
        raise ValueError("promotion_receipt_missing: latest promotion receipt not found")

    source_applied_at = str(latest_promotion.get("applied_at") or "")
    source_action_id = str(latest_promotion.get("action_id") or "")
    bundle = latest_promotion.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")
    expected_settled_hash = bundle.get("primary_path_sha256")
    expected_tombstone_hash = bundle.get("secondary_path_sha256")
    if (
        not isinstance(expected_settled_hash, str)
        or not expected_settled_hash.strip()
        or not isinstance(expected_tombstone_hash, str)
        or not expected_tombstone_hash.strip()
    ):
        raise ValueError("promotion_receipt_missing_hash: promotion receipt bundle/hash anchors are missing")

    actual_settled_hash = compute_file_sha256(settled_path)
    if actual_settled_hash != expected_settled_hash:
        raise ValueError("revert_conflict_settled_modified: settled elixir was modified after promotion")

    if candidate_data is None:
        raise ValueError("revert_tombstone_missing: superseded tombstone is required")
    tombstone_frontmatter, tombstone_body = candidate_data
    tombstone_state = str(tombstone_frontmatter.get("elixir_state") or "")
    if tombstone_state != "superseded":
        raise ValueError(f"unsupported_source_state: cannot revert elixir from state={tombstone_state or 'unknown'}")

    actual_tombstone_hash = compute_file_sha256(candidate_path)
    if actual_tombstone_hash != expected_tombstone_hash:
        raise ValueError("revert_conflict_candidate_modified: candidate tombstone no longer matches promotion receipt")

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_reverted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for revert: %s",
            normalized_id,
        )
        dependency_breaks = []

    tombstone_original_bytes = candidate_path.read_bytes()
    settled_original_bytes = settled_path.read_bytes()
    candidate_frontmatter = dict(tombstone_frontmatter)
    candidate_frontmatter["elixir_state"] = "candidate"
    candidate_frontmatter.pop("superseded_by", None)
    candidate_frontmatter.pop(_PROMOTION_TS_FIELD, None)
    candidate_text = _render_elixir_document(candidate_frontmatter, tombstone_body)

    _write_atomic_text(candidate_path, candidate_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            _restore_file_bytes(candidate_path, tombstone_original_bytes)
        except Exception as rollback_exc:
            raise RevertHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or tombstone_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_revert_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        source_receipt_applied_at=source_applied_at,
        source_receipt_action_id=source_action_id,
        dependency_breaks=dependency_breaks,
    )
    _persist_receipt_transactionally(
        root,
        receipt=receipt,
        elixir_id=normalized_id,
        operation="revert",
        rollback_data=lambda: (
            _restore_file_bytes(candidate_path, tombstone_original_bytes),
            _restore_file_bytes(settled_path, settled_original_bytes),
        ),
        receipt_error_cls=RevertReceiptError,
        half_write_error_factory=lambda phase: RevertHalfWriteError(
            settled_path=settled_path, candidate_path=candidate_path, phase=phase
        ),
    )

    return candidate_path


def demote_elixir(root: Path, *, elixir_id: str, note: str | None = None) -> Path:
    normalized_id = _resolve_elixir_id(root, elixir_id)
    settled_path = _settled_path(root, normalized_id)
    candidate_path = _candidate_path(root, normalized_id)

    settled_data, candidate_data = _read_elixir_both_planes(root, normalized_id)
    if settled_data is None:
        raise FileNotFoundError(f"elixir not found: {normalized_id}")
    settled_frontmatter, settled_body = settled_data
    settled_state = str(settled_frontmatter.get("elixir_state") or "")
    if settled_state != "settled":
        raise ValueError(f"unsupported_source_state: cannot demote elixir from state={settled_state or 'unknown'}")

    had_candidate_before = candidate_data is not None
    candidate_snapshot = _snapshot_file_bytes(candidate_path) if had_candidate_before else None
    settled_snapshot = _snapshot_file_bytes(settled_path)
    if candidate_data is not None:
        candidate_frontmatter, _candidate_body = candidate_data
        candidate_state = str(candidate_frontmatter.get("elixir_state") or "")
        if candidate_state != "superseded":
            raise ValueError("demote_conflict_candidate_exists: candidate plane has conflicting non-superseded state")

    demoted_frontmatter = dict(settled_frontmatter)
    demoted_frontmatter["elixir_state"] = "candidate"
    demoted_frontmatter.pop("promoted_at", None)
    demoted_frontmatter.pop("sealed_at", None)
    demoted_frontmatter.pop("superseded_by", None)
    demoted_text = _render_elixir_document(demoted_frontmatter, settled_body)

    dependency_breaks: list[dict[str, str]]
    try:
        dependent_ids = _collect_dependent_elixir_ids(root, source_elixir_id=normalized_id)
        dependency_breaks = [
            {
                "dependent_elixir_id": dependent_id,
                "break_reason": "source_demoted",
            }
            for dependent_id in dependent_ids
        ]
    except Exception:
        logging.getLogger("aiwiki").exception(
            "failed to collect elixir dependency breaks for demote: %s",
            normalized_id,
        )
        dependency_breaks = []

    _write_atomic_text(candidate_path, demoted_text)
    try:
        settled_path.unlink()
    except Exception as exc:
        try:
            _restore_file_bytes(candidate_path, candidate_snapshot)
        except Exception as rollback_exc:
            raise DemoteHalfWriteError(
                settled_path=settled_path, candidate_path=candidate_path, phase="double_write"
            ) from rollback_exc
        raise exc

    protocol = str(settled_frontmatter.get("protocol") or "")
    applied_at = datetime.now(timezone.utc)
    receipt = build_elixir_demotion_receipt(
        root,
        elixir_id=normalized_id,
        slug=slugify(normalized_id),
        wiki_path=settled_path,
        candidate_path=candidate_path,
        protocol=protocol,
        applied_at=applied_at,
        note=note,
        dependency_breaks=dependency_breaks,
    )
    _persist_receipt_transactionally(
        root,
        receipt=receipt,
        elixir_id=normalized_id,
        operation="demote",
        rollback_data=lambda: (
            _restore_file_bytes(candidate_path, candidate_snapshot),
            _restore_file_bytes(settled_path, settled_snapshot),
        ),
        receipt_error_cls=DemoteReceiptError,
        half_write_error_factory=lambda phase: DemoteHalfWriteError(
            settled_path=settled_path, candidate_path=candidate_path, phase=phase
        ),
    )

    return candidate_path

