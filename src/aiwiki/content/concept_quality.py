"""Concept quality scoring and rewrite strategy symbols (extracted from concepts.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corpus.parse import normalize_concept_hardness
from ..corpus.ranks import action_priority_rank
from ..corpus.snapshots import placeholder_concept_slugs
from ..protocol.runtime_config import CONCEPT_HARDNESS_LEVELS
from ..utils.text import STOP_WORDS, tokenize
from ..utils.time import parse_iso_datetime, utc_now
from .concepts import (
    concept_hardness_rank,
    detect_concept_conflict_signals,
    detect_concept_gap_signals,
)
from .io import load_source_page_context


def concept_quality_tokens(label: str) -> set[str]:
    return {token for token in tokenize(label) if token not in STOP_WORDS}


def concept_source_freshness_score(
    source_contexts: list[dict[str, str]],
    *,
    compiled_at: str,
) -> int:
    compiled_dt = parse_iso_datetime(compiled_at)
    if compiled_dt is None:
        return 50
    source_ages: list[float] = []
    for context in source_contexts:
        parsed = parse_iso_datetime(str(context.get("last_compiled_at") or ""))
        if parsed is None:
            continue
        age_days = max(0.0, (compiled_dt - parsed).total_seconds() / 86400)
        source_ages.append(age_days)
    if not source_ages:
        return 50
    average_age = sum(source_ages) / len(source_ages)
    if average_age <= 1:
        return 100
    if average_age <= 7:
        return 85
    if average_age <= 30:
        return 70
    if average_age <= 90:
        return 55
    return 35


def concept_quality_metrics(
    source_pages: list[str],
    source_contexts: list[dict[str, str]],
    conflict_signals: list[dict[str, Any]],
    gap_signals: list[dict[str, Any]],
    *,
    compiled_at: str,
) -> dict[str, int]:
    source_count = len(source_pages)
    ready_count = sum(1 for context in source_contexts if context.get("status") == "ready")
    placeholder_count = sum(1 for context in source_contexts if context.get("status") == "placeholder")
    missing_count = sum(1 for context in source_contexts if context.get("status") == "missing")
    coverage_score = min(100, source_count * 35) if source_count else 0
    consistency_score = max(20, 100 - len(conflict_signals) * 35) if source_count else 0
    evidence_ratio = (ready_count / source_count) if source_count else 0.0
    gap_penalty = len(gap_signals) * 14 + placeholder_count * 10 + missing_count * 20
    evidence_depth_score = max(0, round(evidence_ratio * 100) - gap_penalty)
    freshness_score = concept_source_freshness_score(source_contexts, compiled_at=compiled_at)
    quality_score = round(
        coverage_score * 0.28 + consistency_score * 0.32 + evidence_depth_score * 0.25 + freshness_score * 0.15
    )
    return {
        "source_coverage": coverage_score,
        "consistency": consistency_score,
        "evidence_depth": evidence_depth_score,
        "recency": freshness_score,
        "quality_score": max(0, min(100, quality_score)),
        "ready_sources": ready_count,
        "placeholder_sources": placeholder_count,
        "missing_sources": missing_count,
    }


def concept_quality_band(quality_score: int) -> str:
    if quality_score >= 85:
        return "strong"
    if quality_score >= 70:
        return "stable"
    if quality_score >= 55:
        return "watch"
    return "fragile"


def concept_rewrite_priority(
    score: int,
    issues: list[str],
    conflicts: list[dict[str, Any]],
    *,
    quality_score: int,
) -> str:
    if score >= 6 or conflicts or "placeholder-summary" in issues or quality_score < 55:
        return "high"
    if score >= 3 or quality_score < 70:
        return "medium"
    if score > 0 or quality_score < 85:
        return "low"
    return ""


def concept_rewrite_strategy(record: dict[str, Any]) -> str:
    issues = set(record.get("issues", []))
    steps: list[str] = []
    if "placeholder-summary" in issues:
        steps.append("替换占位摘要，改成 grounded synthesis。")
    if "conflicting-source-signals" in issues:
        steps.append("并列呈现冲突来源，明确分歧和适用边界。")
    if "evidence-gap" in issues:
        steps.append("保留证据缺口和不确定性，避免过强结论。")
    if "single-source" in issues:
        steps.append("保持保守措辞，并指出还缺哪些来源。")
    if "no-related-concepts" in issues:
        steps.append("补充相关概念边界和反链。")
    if "merge-boundary" in issues:
        steps.append("检查是否需要合并或拆分概念边界。")
    return " ".join(steps[:3]) or "保持当前概念总结。"


def build_concept_quality(root: Path, memory: dict[str, Any]) -> dict[str, Any]:
    placeholder_slugs = set(placeholder_concept_slugs(root))
    singleton_slugs = set(memory.get("health", {}).get("singleton_concept_slugs", []))
    concept_nodes = [dict(node) for node in memory.get("concept_nodes", []) if isinstance(node, dict)]
    concept_records: dict[str, dict[str, Any]] = {}
    compiled_at = str(memory.get("compiled_at") or utc_now())

    merge_candidates: list[dict[str, Any]] = []
    for index, left in enumerate(concept_nodes):
        left_tokens = concept_quality_tokens(str(left.get("title") or left.get("slug") or ""))
        left_sources = set(left.get("source_pages", []))
        if not left_tokens or not left_sources:
            continue
        for right in concept_nodes[index + 1 :]:
            right_tokens = concept_quality_tokens(str(right.get("title") or right.get("slug") or ""))
            right_sources = set(right.get("source_pages", []))
            if not right_tokens or not right_sources:
                continue
            shared_sources = sorted(left_sources & right_sources)
            if not shared_sources:
                continue
            shared_tokens = sorted(left_tokens & right_tokens)
            left_slug = str(left.get("slug") or "")
            right_slug = str(right.get("slug") or "")
            subset_match = (
                left_tokens <= right_tokens
                or right_tokens <= left_tokens
                or left_slug in right_slug
                or right_slug in left_slug
            )
            if not subset_match and len(shared_tokens) < 2:
                continue
            merge_candidates.append(
                {
                    "left_slug": left_slug,
                    "left_title": str(left.get("title") or left_slug),
                    "right_slug": right_slug,
                    "right_title": str(right.get("title") or right_slug),
                    "shared_sources": shared_sources,
                    "shared_tokens": shared_tokens,
                    "score": len(shared_sources) * 2 + len(shared_tokens),
                }
            )

    merge_candidates.sort(
        key=lambda item: (-int(item.get("score", 0)), item["left_title"].lower(), item["right_title"].lower())
    )
    merge_candidate_slugs = {
        slug
        for candidate in merge_candidates
        for slug in (candidate.get("left_slug", ""), candidate.get("right_slug", ""))
        if slug
    }

    for node in concept_nodes:
        slug = str(node.get("slug") or "")
        title = str(node.get("title") or slug)
        source_pages = list(node.get("source_pages", []))
        related_slugs = list(node.get("related_slugs", []))
        hardness = normalize_concept_hardness(node.get("hardness"), default="soft")
        confidence = str(node.get("confidence") or "")
        source_contexts = [load_source_page_context(root, relative) for relative in source_pages]
        conflict_signals = detect_concept_conflict_signals(source_contexts)
        gap_signals = detect_concept_gap_signals(source_contexts)
        issues: list[str] = []
        score = 0
        if hardness == "soft":
            issues.append("soft-hardness")
            score += 1
        if slug in placeholder_slugs:
            issues.append("placeholder-summary")
            score += 3
        if slug in singleton_slugs or len(source_pages) <= 1:
            issues.append("single-source")
            score += 2
        if not related_slugs:
            issues.append("no-related-concepts")
            score += 1
        if conflict_signals:
            issues.append("conflicting-source-signals")
            score += 3
        if gap_signals:
            issues.append("evidence-gap")
            score += 2
        if slug in merge_candidate_slugs:
            issues.append("merge-boundary")
            score += 1
        metrics = concept_quality_metrics(
            source_pages,
            source_contexts,
            conflict_signals,
            gap_signals,
            compiled_at=compiled_at,
        )
        quality_score = int(metrics.get("quality_score", 0))
        concept_records[slug] = {
            "slug": slug,
            "title": title,
            "path": f"wiki/concepts/{slug}.md",
            "source_pages": source_pages,
            "source_signature": str(node.get("source_signature") or ""),
            "source_count": len(source_pages),
            "related_count": len(related_slugs),
            "confidence": confidence,
            "hardness": hardness,
            "issues": issues,
            "score": score,
            "quality_score": quality_score,
            "quality_band": concept_quality_band(quality_score),
            "quality_metrics": {
                "source_coverage": int(metrics.get("source_coverage", 0)),
                "consistency": int(metrics.get("consistency", 0)),
                "evidence_depth": int(metrics.get("evidence_depth", 0)),
                "recency": int(metrics.get("recency", 0)),
            },
            "ready_source_count": int(metrics.get("ready_sources", 0)),
            "placeholder_source_count": int(metrics.get("placeholder_sources", 0)),
            "missing_source_count": int(metrics.get("missing_sources", 0)),
            "conflict_signals": conflict_signals[:4],
            "gap_signals": gap_signals[:4],
            "quality_state": (
                "stable"
                if score == 0 and quality_score >= 75
                else ("rewrite-now" if score >= 3 or quality_score < 55 else "watch")
            ),
        }

    weak_concepts: list[dict[str, Any]] = []
    stable_concepts: list[dict[str, Any]] = []
    rewrite_candidates: list[dict[str, Any]] = []
    all_conflict_signals: list[dict[str, Any]] = []
    all_gap_signals: list[dict[str, Any]] = []
    for record in concept_records.values():
        record["rewrite_priority"] = concept_rewrite_priority(
            int(record.get("score", 0)),
            list(record.get("issues", [])),
            list(record.get("conflict_signals", [])),
            quality_score=int(record.get("quality_score", 0)),
        )
        record["rewrite_strategy"] = concept_rewrite_strategy(record)
        if record["conflict_signals"]:
            for signal in record["conflict_signals"]:
                all_conflict_signals.append({"slug": record["slug"], "title": record["title"], **signal})
        if record["gap_signals"]:
            for gap in record["gap_signals"]:
                all_gap_signals.append({"slug": record["slug"], "title": record["title"], **gap})
        if int(record.get("score", 0)) > 0:
            weak_concepts.append(record)
            rewrite_candidates.append(
                {
                    "slug": record["slug"],
                    "title": record["title"],
                    "path": record["path"],
                    "source_signature": record.get("source_signature", ""),
                    "priority": record["rewrite_priority"],
                    "issues": list(record.get("issues", [])),
                    "score": int(record.get("score", 0)),
                    "quality_score": int(record.get("quality_score", 0)),
                    "quality_band": str(record.get("quality_band") or ""),
                    "quality_metrics": dict(record.get("quality_metrics", {})),
                    "rewrite_strategy": record["rewrite_strategy"],
                    "conflict_count": len(record.get("conflict_signals", [])),
                    "gap_count": len(record.get("gap_signals", [])),
                    "source_pages": list(record.get("source_pages", [])),
                }
            )
        else:
            stable_concepts.append(record)

    weak_concepts.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            int(item.get("quality_score", 0)),
            -len(item.get("conflict_signals", [])),
            int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    stable_concepts.sort(
        key=lambda item: (
            -int(item.get("quality_score", 0)),
            -int(item.get("source_count", 0)),
            item.get("title", "").lower(),
        )
    )
    rewrite_candidates.sort(
        key=lambda item: (
            action_priority_rank(item.get("priority", "")),
            -int(item.get("score", 0)),
            int(item.get("quality_score", 0)),
            -int(item.get("conflict_count", 0)),
            item.get("title", "").lower(),
        )
    )
    hard_concepts = sorted(
        (
            record
            for record in concept_records.values()
            if concept_hardness_rank(record.get("hardness")) >= concept_hardness_rank("medium")
        ),
        key=lambda item: (
            -concept_hardness_rank(item.get("hardness")),
            -int(item.get("source_count", 0)),
            -int(item.get("quality_score", 0)),
            item.get("title", "").lower(),
        ),
    )
    all_conflict_signals.sort(
        key=lambda item: (
            -len(item.get("source_pages", [])),
            item.get("title", "").lower(),
            item.get("label", ""),
        )
    )
    all_gap_signals.sort(
        key=lambda item: (
            item.get("kind", ""),
            item.get("title", "").lower(),
            item.get("path", ""),
        )
    )
    all_concepts = sorted(
        concept_records.values(),
        key=lambda item: (-int(item.get("score", 0)), int(item.get("quality_score", 0)), item.get("title", "").lower()),
    )
    average_quality_score = (
        round(
            sum(int(record.get("quality_score", 0)) for record in all_concepts) / len(all_concepts),
            1,
        )
        if all_concepts
        else 0.0
    )
    quality_bands = {
        band: sum(1 for record in all_concepts if str(record.get("quality_band") or "") == band)
        for band in ("strong", "stable", "watch", "fragile")
    }
    hardness_counts = {
        label: sum(1 for record in all_concepts if normalize_concept_hardness(record.get("hardness")) == label)
        for label in CONCEPT_HARDNESS_LEVELS
    }
    return {
        "all_concepts": all_concepts,
        "hard_concepts": hard_concepts[:12],
        "weak_concepts": weak_concepts[:20],
        "stable_concepts": stable_concepts[:12],
        "merge_candidates": merge_candidates[:12],
        "rewrite_candidates": rewrite_candidates[:12],
        "conflict_signals": all_conflict_signals[:12],
        "gap_signals": all_gap_signals[:12],
        "placeholder_slugs": sorted(placeholder_slugs),
        "average_quality_score": average_quality_score,
        "quality_bands": quality_bands,
        "counts": {
            "weak": len(weak_concepts),
            "stable": len(stable_concepts),
            "merge_candidates": len(merge_candidates),
            "placeholders": len(placeholder_slugs),
            "rewrite_candidates": len(rewrite_candidates),
            "conflict_signals": len(all_conflict_signals),
            "gap_signals": len(all_gap_signals),
            "strong_quality": quality_bands["strong"],
            "stable_quality": quality_bands["stable"],
            "watch_quality": quality_bands["watch"],
            "fragile_quality": quality_bands["fragile"],
            "soft_hardness": hardness_counts["soft"],
            "medium_hardness": hardness_counts["medium"],
            "hard_hardness": hardness_counts["hard"],
            "medium_or_hard": hardness_counts["medium"] + hardness_counts["hard"],
        },
    }
