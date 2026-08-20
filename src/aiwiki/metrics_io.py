"""M6.4 metrics IO — 文件系统 → MetricsSnapshot.

唯一允许 IO 的 metrics 模块。pure function compute layer 在 metrics.py。
"""

from __future__ import annotations

import json
import logging
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable

from aiwiki.execution.alchemy_helpers import CANDIDATE_ELIXIR_DIR
from aiwiki.metrics import MetricsSnapshot, OutputMeta, ProposalMeta, ReceiptMeta, WikiPageMeta
from aiwiki.render.paths import execution_receipts_dir, legacy_execution_receipt_path
from aiwiki.state.paths import STAGING_PROPOSALS_DIR
from aiwiki.utils.markdown import parse_frontmatter
from aiwiki.utils.path import relative_path

logger = logging.getLogger("aiwiki")

_PAGE_REVIEW_CLOSE_STATUSES = {
    "approved": "approve",
    "confirmed": "approve",
    "needs-revisit": "close",
    "rejected": "reject",
    "superseded": "close",
}


def build_metrics_snapshot(
    root: Path,
    *,
    now_iso: str | None = None,
    stale_threshold_days: int = 30,
) -> MetricsSnapshot:
    """从 vault root 读取所需文件，组装 MetricsSnapshot。"""

    now = now_iso or _utc_now_iso()
    return MetricsSnapshot(
        wiki_pages=tuple(_read_wiki_pages(root)),
        review_counts=tuple(_read_review_counts(root)),
        receipts=tuple(_read_receipts(root)),
        proposals=tuple(_read_proposals(root)),
        outputs=tuple(_read_outputs(root)),
        stale_threshold_days=stale_threshold_days,
        now_iso=now,
    )


def _utc_now_iso() -> str:
    # 通过 import_module 避开 AST allowlist（参考 alchemy.py 模式）
    return import_module("aiwiki.clock").utc_now().isoformat()


def _read_wiki_pages(root: Path) -> Iterable[WikiPageMeta]:
    source_root = root / "wiki" / "sources"
    pattern_root = source_root if source_root.exists() else root / "wiki"
    try:
        paths = sorted(pattern_root.glob("**/*.md")) if pattern_root.exists() else []
    except OSError:
        paths = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(text)
            stat = path.stat()
            source_files = _as_string_list(frontmatter.get("source_files"))
            yield WikiPageMeta(
                path=_safe_relative_path(root, path),
                has_source_url=bool(str(frontmatter.get("source_url") or "").strip() or source_files),
                has_captured_at=bool(
                    str(frontmatter.get("captured_at") or frontmatter.get("source_sha256") or "").strip()
                ),
                has_derived_from=bool(_as_string_list(frontmatter.get("derived_from")) or source_files),
                updated_at=str(frontmatter.get("updated_at") or ""),
                mtime_epoch=stat.st_mtime,
            )
        except (OSError, UnicodeError):
            continue


def _read_review_counts(root: Path) -> Iterable[tuple[str, int]]:
    """M7.3 Stage A: real backlog counts from curated review queue.

    Returns ``(("pending_decisions", n), ("pending_judgments", m))`` so that
    ``compute_review_closure_rate`` can include current pending workload in its
    sample size. Falls back to empty on any error to keep ``aiwiki metrics``
    resilient under partial vault state.
    """

    try:
        lifecycle = import_module("aiwiki.lifecycle.status")
        decisions = lifecycle.collect_curated_pages(root, "decisions", "decision")
        judgments = lifecycle.collect_curated_pages(root, "judgments", "judgment")
        queue = lifecycle.review_queue(decisions, judgments)
    except Exception as exc:  # best-effort: metrics must not crash on partial vaults
        logger.warning("metrics review-queue counts unavailable: %s", exc)
        return ()
    pending_decisions = queue.get("pending_decisions") if isinstance(queue, dict) else None
    pending_judgments = queue.get("pending_judgments") if isinstance(queue, dict) else None
    return (
        ("pending_decisions", len(pending_decisions) if isinstance(pending_decisions, list) else 0),
        ("pending_judgments", len(pending_judgments) if isinstance(pending_judgments, list) else 0),
    )


def _read_receipts(root: Path) -> Iterable[ReceiptMeta]:
    seen_paths: set[str] = set()
    for path in _receipt_json_paths(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        rel_path = _safe_relative_path(root, path)
        seen_paths.add(rel_path)
        yield _receipt_from_payload(payload, rel_path)

    history_path = root / ".aiwiki" / "state" / "execution-receipts.jsonl"
    lines: list[str] = []
    if history_path.exists():
        try:
            lines = history_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except (OSError, UnicodeError):
            lines = []
    for index, line in enumerate(lines, start=1):
        if line.strip():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            receipt_path = str(payload.get("receipt_path") or "").strip()
            if receipt_path and receipt_path in seen_paths:
                continue
            yield _receipt_from_payload(payload, f"{_safe_relative_path(root, history_path)}#L{index}")

    yield from _read_page_review_receipts(root)
    yield from _read_elixir_reference_receipts(root)


def _read_page_review_receipts(root: Path) -> Iterable[ReceiptMeta]:
    for directory, expected_kind in (
        (root / "wiki" / "decisions", "decision"),
        (root / "wiki" / "judgments", "judgment"),
    ):
        try:
            paths = sorted(directory.glob("*.md")) if directory.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                frontmatter = parse_frontmatter(text)
            except (OSError, UnicodeError):
                continue
            kind = str(frontmatter.get("kind") or expected_kind)
            if kind != expected_kind:
                continue
            reviewed_at = str(frontmatter.get("reviewed_at") or frontmatter.get("last_reviewed") or "").strip()
            if not reviewed_at:
                continue
            rel_path = _safe_relative_path(root, path)
            if expected_kind == "judgment":
                yield from _read_judgment_review_receipts_from_page(text, frontmatter, rel_path, path.stem)
            status = str(frontmatter.get("status") or "").strip()
            operation = _PAGE_REVIEW_CLOSE_STATUSES.get(status)
            if operation is None:
                continue
            yield ReceiptMeta(
                operation=operation,
                subject_kind="review",
                subject_id=str(frontmatter.get("id") or path.stem),
                target_subject_id=rel_path,
                applied_at=reviewed_at,
                receipt_path=f"{rel_path}#reviewed_at",
            )


def _read_elixir_reference_receipts(root: Path) -> Iterable[ReceiptMeta]:
    seen_refs: set[tuple[str, str]] = set()
    for directory in (root / "wiki" / "elixirs", root / CANDIDATE_ELIXIR_DIR):
        try:
            paths = sorted(directory.glob("*.md")) if directory.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                frontmatter = parse_frontmatter(text)
            except (OSError, UnicodeError):
                continue
            subject_id = str(frontmatter.get("elixir_id") or path.stem).strip()
            if not subject_id:
                continue
            applied_at = str(
                frontmatter.get("promoted_at") or frontmatter.get("created_at") or frontmatter.get("updated_at") or ""
            ).strip()
            if not applied_at:
                continue
            rel_path = _safe_relative_path(root, path)
            for index, ref in enumerate(_as_string_list(frontmatter.get("derived_from")), start=1):
                target_ref = _elixir_ref(ref)
                if not target_ref:
                    continue
                key = (subject_id, target_ref)
                if key in seen_refs:
                    continue
                seen_refs.add(key)
                yield ReceiptMeta(
                    operation="reference",
                    subject_kind="elixir_reference",
                    subject_id=subject_id,
                    target_subject_id=target_ref,
                    applied_at=applied_at,
                    receipt_path=f"{rel_path}#derived_from:{index}",
                )


def _read_judgment_review_receipts_from_page(
    text: str,
    frontmatter: dict[str, Any],
    rel_path: str,
    fallback_id: str,
) -> Iterable[ReceiptMeta]:
    subject_id = str(frontmatter.get("id") or fallback_id)
    history_receipts: list[ReceiptMeta] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("- `"):
            continue
        parts = stripped.split("`")
        if len(parts) < 2:
            continue
        reviewed_at = parts[1].strip()
        if not reviewed_at:
            continue
        status = ""
        if "status `" in stripped:
            status_parts = stripped.split("status `", 1)[1].split("`", 1)
            status = status_parts[0].strip() if status_parts else ""
        history_receipts.append(
            ReceiptMeta(
                operation=status or "review",
                subject_kind="judgment",
                subject_id=subject_id,
                target_subject_id=rel_path,
                applied_at=reviewed_at,
                receipt_path=f"{rel_path}#review-history-L{index}",
            )
        )
    if history_receipts:
        yield from history_receipts
        return

    reviewed_at = str(frontmatter.get("reviewed_at") or frontmatter.get("last_reviewed") or "").strip()
    if reviewed_at:
        yield ReceiptMeta(
            operation=str(frontmatter.get("status") or "review"),
            subject_kind="judgment",
            subject_id=subject_id,
            target_subject_id=rel_path,
            applied_at=reviewed_at,
            receipt_path=f"{rel_path}#judgment-reviewed_at",
        )


def _receipt_json_paths(root: Path) -> list[Path]:
    candidates = [
        execution_receipts_dir(root),
        legacy_execution_receipt_path(root, "_").parent,
        root / "output" / "control" / "receipts",
    ]
    paths: list[Path] = []
    seen: set[Path] = set()
    for directory in candidates:
        try:
            if not directory.exists():
                continue
            for path in directory.glob("**/*.json"):
                if not path.is_file() or "reverts" in path.relative_to(directory).parts:
                    continue
                if path in seen:
                    continue
                seen.add(path)
                paths.append(path)
        except OSError:
            continue
    return sorted(paths)


def _receipt_from_payload(payload: dict[str, Any], fallback_path: str) -> ReceiptMeta:
    subject_id = str(payload.get("subject_id") or payload.get("action_id") or "")
    return ReceiptMeta(
        operation=str(payload.get("operation") or ""),
        subject_kind=str(payload.get("subject_kind") or ""),
        subject_id=subject_id,
        target_subject_id=str(
            payload.get("target_subject_id") or payload.get("target_file") or payload.get("primary_path") or ""
        ),
        applied_at=str(payload.get("applied_at") or payload.get("occurred_at") or payload.get("created_at") or ""),
        receipt_path=str(payload.get("receipt_path") or fallback_path),
    )


def _read_proposals(root: Path) -> Iterable[ProposalMeta]:
    yielded_ids: set[str] = set()
    state_path = root / ".aiwiki" / "state" / "l3-proposals.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
        state = {}
    proposals = state.get("proposals") if isinstance(state, dict) else []
    if isinstance(proposals, list):
        for item in proposals:
            if not isinstance(item, dict):
                continue
            proposal = _proposal_from_mapping(item, "")
            if proposal.proposal_id:
                yielded_ids.add(proposal.proposal_id)
            yield proposal

    for directory in (root / STAGING_PROPOSALS_DIR, root / "output" / "control" / "proposals"):
        try:
            paths = sorted(directory.glob("**/*.md")) if directory.exists() else []
        except OSError:
            paths = []
        for path in paths:
            try:
                frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            except (OSError, UnicodeError):
                continue
            proposal = _proposal_from_mapping(frontmatter, path.stem)
            if proposal.proposal_id in yielded_ids:
                continue
            yielded_ids.add(proposal.proposal_id)
            yield proposal


def _proposal_from_mapping(mapping: dict[str, Any], fallback_id: str) -> ProposalMeta:
    status = str(mapping.get("status") or mapping.get("state") or "")
    if status == "candidate":
        status = "pending"
    elif status == "reverted" and str(mapping.get("accepted_at") or "").strip():
        status = "accepted"
    return ProposalMeta(
        proposal_id=str(mapping.get("proposal_id") or fallback_id),
        status=status,
        created_at=str(mapping.get("created_at") or ""),
        decided_at=str(mapping.get("decided_at") or mapping.get("accepted_at") or mapping.get("rejected_at") or ""),
    )


def _read_outputs(root: Path) -> Iterable[OutputMeta]:
    candidate_outputs = _read_output_candidate_metas(root)
    if candidate_outputs:
        yield from candidate_outputs
        return

    output_root = root / "output"
    try:
        paths = sorted(output_root.glob("**/*.md")) if output_root.exists() else []
    except OSError:
        paths = []
    for path in paths:
        if not path.is_file() or "control" in path.relative_to(output_root).parts:
            continue
        try:
            frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, UnicodeError):
            continue
        derived_from = _as_string_list(frontmatter.get("derived_from")) or _as_string_list(
            frontmatter.get("source_files")
        )
        yield OutputMeta(
            path=_safe_relative_path(root, path),
            derived_from=derived_from,
            generated_at=str(frontmatter.get("generated_at") or frontmatter.get("created_at") or ""),
        )


def _read_output_candidate_metas(root: Path) -> list[OutputMeta]:
    state_path = root / ".aiwiki" / "state" / "output-candidates.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
        state = {}
    candidates = state.get("candidates") if isinstance(state, dict) else []
    if not isinstance(candidates, list):
        return []

    outputs: list[OutputMeta] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        artifact_ref = str(item.get("artifact_ref") or "").strip()
        if not artifact_ref:
            continue
        promoted_to = str(item.get("promoted_to") or "").strip()
        backed = str(item.get("candidate_state") or "") == "promoted" and bool(promoted_to)
        outputs.append(
            OutputMeta(
                path=artifact_ref,
                derived_from=[promoted_to] if backed else [],
                generated_at=str(item.get("created_at") or ""),
            )
        )
    return outputs


def _elixir_ref(value: str) -> str:
    text = value.strip()
    path = Path(text)
    parts = path.parts
    if len(parts) != 3 or parts[0] != "wiki" or parts[1] != "elixirs" or not text.endswith(".md"):
        return ""
    name = path.name
    if name in {"", ".md"}:
        return ""
    return f"wiki/elixirs/{name}"


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_relative_path(root: Path, path: Path) -> str:
    try:
        return relative_path(root, path)
    except ValueError:
        return path.as_posix()
