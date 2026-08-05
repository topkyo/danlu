"""Scarce compound (沉淀/凝丹) suggestions for Product Shell summary."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from ..content.output_artifacts import find_promoted_curated_page
from ..content.outputs import normalize_query_signature
from ..execution.alchemy_helpers import ELIXIR_DIR, list_promoted_outputs_for_corpus
from ..execution.candidates import load_output_candidates_state
from ..utils.hash import question_signature
from ..utils.markdown import frontmatter_string_list, parse_frontmatter

_COMPOUND_SUGGEST_MAX = 3
_REPORT_SCAN_LIMIT = 8
_CLI_PREFIX = "PYTHONPATH=src python3 -m aiwiki.cli --root ."


def _confirmed_judgment_paths(memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    paths: dict[str, dict[str, str]] = {}
    for node in memory.get("judgment_nodes", []) or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("kind") or "") != "judgment":
            continue
        if str(node.get("status") or "") != "confirmed":
            continue
        page_id = str(node.get("page_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not path and page_id:
            path = f"wiki/judgments/{page_id}.md"
        if not path:
            continue
        paths[path] = {
            "page_id": page_id or Path(path).stem,
            "title": str(node.get("title") or page_id or path),
        }
    return paths


def _settled_elixir_paths(root: Path, memory: dict[str, Any]) -> dict[str, dict[str, str]]:
    paths: dict[str, dict[str, str]] = {}
    for node in memory.get("elixir_nodes", []) or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("elixir_state") or "settled") != "settled":
            continue
        elixir_id = str(node.get("elixir_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not path and elixir_id:
            path = f"{ELIXIR_DIR}/{elixir_id}.md"
        if not path:
            continue
        paths[path] = {
            "elixir_id": elixir_id or Path(path).stem,
            "title": str(node.get("title") or elixir_id or path),
        }
    if paths:
        return paths
    elixir_dir = root / ELIXIR_DIR
    if not elixir_dir.is_dir():
        return paths
    for page in sorted(elixir_dir.glob("*.md")):
        try:
            frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        state = str(frontmatter.get("elixir_state") or "settled").strip() or "settled"
        if state != "settled":
            continue
        elixir_id = str(frontmatter.get("id") or page.stem).strip() or page.stem
        page_path = f"{ELIXIR_DIR}/{page.name}"
        paths[page_path] = {
            "elixir_id": elixir_id,
            "title": str(frontmatter.get("title") or elixir_id),
        }
    return paths




def _query_signature_counts(route_telemetry: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in route_telemetry.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        signature = str(entry.get("query_signature") or "").strip()
        if not signature:
            continue
        counts[signature] = counts.get(signature, 0) + 1
    return counts


def _corpus_report_counts(reports: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        corpus_id = str(report.get("corpus_id") or "").strip()
        if not corpus_id:
            continue
        counts[corpus_id] = counts.get(corpus_id, 0) + 1
    return counts


def _load_report_context(root: Path, report_path: str) -> dict[str, Any] | None:
    target = root / report_path
    if not target.is_file():
        return None
    try:
        frontmatter = parse_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    query = str(frontmatter.get("query") or "").strip()
    used_refs = frontmatter_string_list(frontmatter, "used_refs")
    if not used_refs:
        used_refs = frontmatter_string_list(frontmatter, "used_context_refs")
    corpus_id = str(frontmatter.get("active_corpus_id") or frontmatter.get("corpus_id") or "").strip()
    return {
        "path": report_path,
        "title": str(frontmatter.get("title") or query or Path(report_path).stem),
        "query": query,
        "query_signature": question_signature(query) if query else "",
        "query_signature_normalized": normalize_query_signature(query) if query else "",
        "corpus_id": corpus_id,
        "used_refs": used_refs,
        "protocol": str(frontmatter.get("protocol") or ""),
        "artifact_quality": str(frontmatter.get("artifact_quality") or ""),
    }


def _score_candidate(
    *,
    multi_turn: bool,
    has_linked: bool,
    has_conflict: bool,
    already_judgment: bool,
) -> int:
    if already_judgment:
        return -999
    score = 0
    if multi_turn:
        score += 1
    if has_linked:
        score += 2
    if has_conflict:
        score += 2
    return score


def _signal_label(*, multi_turn: bool, has_linked: bool, has_conflict: bool) -> str:
    if has_conflict and has_linked:
        return "conflict-or-extend"
    if has_conflict:
        return "conflict"
    if multi_turn and has_linked:
        return "extend"
    if multi_turn:
        return "multi-turn"
    if has_linked:
        return "linked"
    return "unknown"


def _file_back_command(report_path: str) -> str:
    return f"{_CLI_PREFIX} advanced file-back {shlex.quote(report_path)}"


def _alchemy_start_command(*, corpus_id: str, topic: str) -> str:
    return f"{_CLI_PREFIX} advanced alchemy start {shlex.quote(corpus_id)} --topic {shlex.quote(topic)}"


def build_compound_suggest(
    root: Path,
    *,
    memory: dict[str, Any],
    recent_outputs: list[dict[str, Any]],
    route_telemetry: dict[str, Any],
    counter_evidence_pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return scarce compound suggestions; never one per report by default."""

    confirmed_judgments = _confirmed_judgment_paths(memory)
    settled_elixirs = _settled_elixir_paths(root, memory)
    signature_counts = _query_signature_counts(route_telemetry if isinstance(route_telemetry, dict) else {})
    counter_paths = {
        str(item.get("path") or "").strip()
        for item in (counter_evidence_pages or [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    }

    deliverable_reports: list[dict[str, Any]] = []
    for item in recent_outputs[: _REPORT_SCAN_LIMIT * 2]:
        if not isinstance(item, dict):
            continue
        report_path = str(item.get("path") or "").strip()
        if not report_path.startswith("output/reports/"):
            continue
        quality = str(item.get("artifact_quality") or "deliverable")
        if quality == "degraded":
            continue
        context = _load_report_context(root, report_path)
        if context is None:
            continue
        context["artifact_quality"] = quality
        deliverable_reports.append(context)
        if len(deliverable_reports) >= _REPORT_SCAN_LIMIT:
            break

    corpus_counts = _corpus_report_counts(deliverable_reports)
    candidates: list[dict[str, Any]] = []
    promoted_artifact_refs = {
        str(item.get("artifact_ref") or "").strip()
        for item in load_output_candidates_state(root).get("candidates", [])
        if isinstance(item, dict)
        and str(item.get("candidate_state") or "") == "promoted"
        and str(item.get("promoted_to") or "").strip().startswith("wiki/judgments/")
    }

    for report in deliverable_reports:
        report_path = str(report["path"])
        query = str(report.get("query") or "")
        query_sig = str(report.get("query_signature") or "")
        corpus_id = str(report.get("corpus_id") or "")
        used_refs = list(report.get("used_refs") or [])

        linked_judgments = [ref for ref in used_refs if ref in confirmed_judgments]
        linked_elixirs = [ref for ref in used_refs if ref in settled_elixirs]
        has_linked = bool(linked_judgments or linked_elixirs)

        multi_turn = bool(
            (query_sig and signature_counts.get(query_sig, 0) >= 2)
            or (corpus_id and corpus_counts.get(corpus_id, 0) >= 2)
        )
        has_conflict = any(ref in counter_paths for ref in linked_judgments)

        already_judgment = report_path in promoted_artifact_refs
        if not already_judgment and query:
            protocol = str(report.get("protocol") or "")
            existing = find_promoted_curated_page(
                root,
                "judgment",
                normalize_query_signature(query),
                protocol,
            )
            already_judgment = existing is not None

        score = _score_candidate(
            multi_turn=multi_turn,
            has_linked=has_linked,
            has_conflict=has_conflict,
            already_judgment=already_judgment,
        )
        if score < 3:
            continue

        signal = _signal_label(
            multi_turn=multi_turn,
            has_linked=has_linked,
            has_conflict=has_conflict,
        )
        linked_refs = linked_judgments + linked_elixirs
        reason_parts = []
        if multi_turn:
            reason_parts.append("multi-turn-same-corpus")
        if linked_judgments:
            reason_parts.append("links-confirmed-judgment")
        if linked_elixirs:
            reason_parts.append("links-settled-elixir")
        if has_conflict:
            reason_parts.append("conflict-or-extend")

        use_alchemy = bool(
            linked_elixirs and multi_turn and corpus_id and list_promoted_outputs_for_corpus(root, corpus_id)
        )
        if use_alchemy:
            action = "alchemy-start"
            elixir_title = settled_elixirs[linked_elixirs[0]]["title"]
            title = f"凝丹：衔接「{elixir_title}」"
            command = _alchemy_start_command(corpus_id=corpus_id, topic=query or report_path)
        else:
            action = "file-back-judgment"
            title = f"沉淀：{query or report['title']}"
            command = _file_back_command(report_path)

        candidates.append(
            {
                "report_path": report_path,
                "report_title": str(report.get("title") or query or report_path),
                "signal": signal,
                "action": action,
                "reason": ",".join(reason_parts) or signal,
                "linked_refs": linked_refs,
                "corpus_id": corpus_id,
                "topic": query,
                "title": title,
                "command": command,
                "protocol": str(report.get("protocol") or ""),
                "score": score,
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            0 if str(item.get("action") or "") == "alchemy-start" else 1,
            str(item.get("report_path") or ""),
        )
    )
    items = [
        {key: value for key, value in item.items() if key != "score"} for item in candidates[:_COMPOUND_SUGGEST_MAX]
    ]
    return {
        "available": bool(items),
        "count": len(items),
        "max_items": _COMPOUND_SUGGEST_MAX,
        "items": items,
    }
