"""Markdown renderer for the judgment assets index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lifecycle.knowledge import judgment_lifecycle_profile
from ..protocol.descriptors import protocol_title
from ..protocol.focus_scoring import page_focus_score
from ..state.constants import DEFAULT_PROTOCOL, JUDGMENT_LIFECYCLE_STATES
from ..utils.markdown import parse_frontmatter
from .views import render_curated_page_summary


def frontmatter_relation_values(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def resolve_curated_relation_reference(
    reference: str,
    *,
    current_path: str,
    page_by_id: dict[str, dict[str, str]],
    page_by_path: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    candidate = reference.strip()
    if not candidate:
        return None
    if candidate in page_by_id:
        return page_by_id[candidate]
    if candidate in page_by_path:
        return page_by_path[candidate]
    if candidate.endswith(".md") and not candidate.startswith("wiki/"):
        relative_candidate = (Path(current_path).parent / candidate).as_posix()
        if relative_candidate in page_by_path:
            return page_by_path[relative_candidate]
    stem = Path(candidate).stem
    return page_by_id.get(stem) or page_by_path.get(stem)


def collect_curated_relation_rows(root: Path, pages: list[dict[str, str]]) -> list[dict[str, str]]:
    page_by_id = {str(page.get("page_id") or ""): page for page in pages if page.get("page_id")}
    page_by_path: dict[str, dict[str, str]] = {}
    for page in pages:
        page_path = str(page.get("path") or "")
        if not page_path:
            continue
        page_by_path[page_path] = page
        page_by_path[Path(page_path).name] = page
        page_by_path[Path(page_path).stem] = page
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for page in pages:
        page_path = str(page.get("path") or "")
        target = root / page_path
        if not page_path or not target.exists():
            continue
        frontmatter = parse_frontmatter(target.read_text(encoding="utf-8", errors="replace"))
        for key, relation in (
            ("related_judgments", "related"),
            ("supports", "supports"),
            ("contradicts", "contradicts"),
        ):
            for reference in frontmatter_relation_values(frontmatter, key):
                resolved = resolve_curated_relation_reference(
                    reference,
                    current_path=page_path,
                    page_by_id=page_by_id,
                    page_by_path=page_by_path,
                )
                target_id = str(resolved.get("page_id") or reference) if resolved else reference
                row_key = (str(page.get("page_id") or ""), relation, target_id)
                if row_key in seen:
                    continue
                seen.add(row_key)
                rows.append(
                    {
                        "source_title": str(page.get("title") or page.get("page_id") or page_path),
                        "source_path": page_path,
                        "source_id": str(page.get("page_id") or ""),
                        "relation": relation,
                        "target_title": str((resolved or {}).get("title") or reference or "unknown relation target"),
                        "target_path": str((resolved or {}).get("path") or ""),
                        "target_id": target_id,
                        "resolved": "true" if resolved else "false",
                    }
                )
    return rows


def judgment_asset_gap_codes(page: dict[str, str]) -> list[str]:
    if str(page.get("kind") or "") not in {"decision", "judgment"}:
        return []
    reasons: list[str] = []
    if page.get("has_counter_evidence") != "true":
        reasons.append("missing-counter-evidence")
    if page.get("has_invalidation") != "true":
        reasons.append("missing-invalidation")
    if page.get("has_next_signals") != "true":
        reasons.append("missing-next-signals")
    if page.get("has_review_history") != "true":
        reasons.append("missing-review-history")
    if page.get("citation_drift") == "true":
        reasons.append("citation-drift")
    if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0:
        reasons.append("citation-snapshot-gap")
    if page.get("has_counter_evidence_metadata") != "true":
        reasons.append("missing-counter-evidence-metadata")
    if page.get("has_invalidation_rule_metadata") != "true":
        reasons.append("missing-invalidation-rule-metadata")
    if page.get("has_next_signals_metadata") != "true":
        reasons.append("missing-next-signals-metadata")
    if page.get("has_formed_at_metadata") != "true":
        reasons.append("missing-formed-at-metadata")
    if page.get("has_last_reviewed_metadata") != "true":
        reasons.append("missing-last-reviewed-metadata")
    return reasons


def judgment_asset_shell_record(
    page: dict[str, str],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    asset_gaps = judgment_asset_gap_codes(page)
    judgment_lifecycle_state, judgment_lifecycle_reason_codes = judgment_lifecycle_profile(page)
    attention_reasons: list[str] = []
    if page.get("escalation_candidate") == "true":
        attention_reasons.append("escalation-candidate")
    if page.get("overdue_review") == "true":
        attention_reasons.append("overdue-review")
    if page.get("pending_review") == "true":
        attention_reasons.append("pending-review")
    if page.get("aging_state") == "scheduled":
        attention_reasons.append("scheduled-review")
    for reason_code in asset_gaps:
        if reason_code not in attention_reasons:
            attention_reasons.append(reason_code)
    return {
        "page_id": str(page.get("page_id") or ""),
        "title": str(page.get("title") or page.get("path") or ""),
        "path": str(page.get("path") or ""),
        "kind": str(page.get("kind") or ""),
        "status": str(page.get("status") or ""),
        "current_status": str(page.get("status") or ""),
        "protocol": str(page.get("protocol") or ""),
        "confidence": str(page.get("confidence") or ""),
        "formed_at": str(page.get("formed_at") or ""),
        "last_reviewed": str(page.get("last_reviewed") or page.get("reviewed_at") or ""),
        "reviewed_at": str(page.get("reviewed_at") or ""),
        "updated_at": str(page.get("updated_at") or ""),
        "revisit_after": str(page.get("revisit_after") or ""),
        "escalate_after": str(page.get("escalate_after") or ""),
        "aging_state": str(page.get("aging_state") or ""),
        "pending_review": str(page.get("pending_review") or "") == "true",
        "overdue_review": str(page.get("overdue_review") or "") == "true",
        "escalation_candidate": str(page.get("escalation_candidate") or "") == "true",
        "focus_score": page_focus_score(active_protocol, page),
        "asset_score": int(page.get("asset_score", "0") or "0"),
        "has_counter_evidence": str(page.get("has_counter_evidence") or "") == "true",
        "has_invalidation": str(page.get("has_invalidation") or "") == "true",
        "has_next_signals": str(page.get("has_next_signals") or "") == "true",
        "has_review_history": str(page.get("has_review_history") or "") == "true",
        "has_counter_evidence_metadata": str(page.get("has_counter_evidence_metadata") or "") == "true",
        "has_invalidation_rule_metadata": str(page.get("has_invalidation_rule_metadata") or "") == "true",
        "has_next_signals_metadata": str(page.get("has_next_signals_metadata") or "") == "true",
        "has_formed_at_metadata": str(page.get("has_formed_at_metadata") or "") == "true",
        "has_last_reviewed_metadata": str(page.get("has_last_reviewed_metadata") or "") == "true",
        "has_structured_counter_evidence": str(page.get("has_structured_counter_evidence") or "") == "true",
        "has_structured_invalidation_rule": str(page.get("has_structured_invalidation_rule") or "") == "true",
        "has_structured_next_signals": str(page.get("has_structured_next_signals") or "") == "true",
        "counter_evidence_count": int(page.get("counter_evidence_count", "0") or "0"),
        "next_signal_count": int(page.get("next_signal_count", "0") or "0"),
        "invalidation_rule": str(page.get("invalidation_rule") or ""),
        "review_history_entries": int(page.get("review_history_entries", "0") or "0"),
        "latest_review_history_entry": str(page.get("latest_review_history_entry") or ""),
        "citation_drift": str(page.get("citation_drift") or "") == "true",
        "citation_drift_count": int(page.get("citation_drift_count", "0") or "0"),
        "citation_snapshot_gap_count": int(page.get("citation_snapshot_gap_count", "0") or "0"),
        "judgment_lifecycle_state": judgment_lifecycle_state,
        "judgment_lifecycle_reason_codes": judgment_lifecycle_reason_codes,
        "asset_gaps": asset_gaps,
        "attention_reasons": attention_reasons,
    }


def judgment_asset_attention_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if record.get("escalation_candidate") else 1,
        0 if record.get("overdue_review") else 1,
        0 if record.get("pending_review") else 1,
        0 if record.get("citation_drift") else 1,
        0 if int(record.get("citation_snapshot_gap_count", 0) or 0) > 0 else 1,
        -len(record.get("asset_gaps", [])),
        int(record.get("asset_score", 0) or 0),
        -int(record.get("focus_score", 0) or 0),
        str(record.get("revisit_after") or record.get("escalate_after") or "9999"),
        str(record.get("title") or "").lower(),
    )


def judgment_asset_summary(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    pages = sorted(
        decisions + judgments,
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -page_focus_score(active_protocol, page),
            -(int(page.get("asset_score", "0") or "0")),
            page.get("title", "").lower(),
        ),
    )
    strong_assets = [page for page in pages if int(page.get("asset_score", "0") or "0") >= 3]
    missing_counter = [page for page in pages if page.get("has_counter_evidence") != "true"]
    missing_invalidation = [page for page in pages if page.get("has_invalidation") != "true"]
    missing_next_signals = [page for page in pages if page.get("has_next_signals") != "true"]
    missing_history = [page for page in pages if page.get("has_review_history") != "true"]
    drifted = [page for page in pages if page.get("citation_drift") == "true"]
    snapshot_gaps = [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0]
    missing_counter_metadata = [page for page in pages if page.get("has_counter_evidence_metadata") != "true"]
    missing_invalidation_metadata = [page for page in pages if page.get("has_invalidation_rule_metadata") != "true"]
    missing_next_signal_metadata = [page for page in pages if page.get("has_next_signals_metadata") != "true"]
    missing_formed_at_metadata = [page for page in pages if page.get("has_formed_at_metadata") != "true"]
    missing_last_reviewed_metadata = [page for page in pages if page.get("has_last_reviewed_metadata") != "true"]
    shell_records = {
        str(page.get("path") or ""): judgment_asset_shell_record(page, active_protocol=active_protocol)
        for page in pages
        if str(page.get("path") or "")
    }
    attention_pages = [
        page for page in pages if shell_records.get(str(page.get("path") or ""), {}).get("attention_reasons")
    ]
    attention_records = [
        shell_records[str(page.get("path") or "")]
        for page in attention_pages
        if str(page.get("path") or "") in shell_records
    ]
    attention_records.sort(key=judgment_asset_attention_sort_key)
    strong_records = [
        shell_records[str(page.get("path") or "")]
        for page in strong_assets
        if str(page.get("path") or "") in shell_records
    ]
    lifecycle_counts = {state: 0 for state in JUDGMENT_LIFECYCLE_STATES}
    for record in shell_records.values():
        lifecycle_state = str(record.get("judgment_lifecycle_state") or "")
        if lifecycle_state in lifecycle_counts:
            lifecycle_counts[lifecycle_state] += 1
    return {
        "counts": {
            "pages": len(pages),
            "decisions": len(decisions),
            "judgments": len(judgments),
            "strong_assets": len(strong_assets),
            "attention_pages": len(attention_pages),
            "missing_counter_evidence": len(missing_counter),
            "missing_invalidation": len(missing_invalidation),
            "missing_next_signals": len(missing_next_signals),
            "missing_review_history": len(missing_history),
            "missing_counter_evidence_metadata": len(missing_counter_metadata),
            "missing_invalidation_rule_metadata": len(missing_invalidation_metadata),
            "missing_next_signals_metadata": len(missing_next_signal_metadata),
            "missing_formed_at_metadata": len(missing_formed_at_metadata),
            "missing_last_reviewed_metadata": len(missing_last_reviewed_metadata),
            "citation_drift": len(drifted),
            "citation_snapshot_gaps": len(snapshot_gaps),
            "pending_review": sum(1 for page in pages if page.get("pending_review") == "true"),
            "overdue_review": sum(1 for page in pages if page.get("overdue_review") == "true"),
            "scheduled_review": sum(1 for page in pages if page.get("aging_state") == "scheduled"),
            "escalation_candidates": sum(1 for page in pages if page.get("escalation_candidate") == "true"),
            "formed_lifecycle": lifecycle_counts["formed"],
            "active_lifecycle": lifecycle_counts["active"],
            "under_review_lifecycle": lifecycle_counts["under-review"],
            "revised_lifecycle": lifecycle_counts["revised"],
            "retired_lifecycle": lifecycle_counts["retired"],
        },
        "lists": {
            "pages": pages,
            "attention_pages": attention_pages,
            "strong_assets": strong_assets,
            "missing_counter_evidence": missing_counter,
            "missing_invalidation": missing_invalidation,
            "missing_next_signals": missing_next_signals,
            "missing_review_history": missing_history,
            "missing_counter_evidence_metadata": missing_counter_metadata,
            "missing_invalidation_rule_metadata": missing_invalidation_metadata,
            "missing_next_signals_metadata": missing_next_signal_metadata,
            "missing_formed_at_metadata": missing_formed_at_metadata,
            "missing_last_reviewed_metadata": missing_last_reviewed_metadata,
            "citation_drift": drifted,
            "citation_snapshot_gaps": snapshot_gaps,
            "escalation_candidates": [page for page in pages if page.get("escalation_candidate") == "true"],
        },
        "attention_pages": attention_records,
        "decision_focus": [record for record in attention_records if record.get("kind") == "decision"],
        "judgment_focus": [record for record in attention_records if record.get("kind") == "judgment"],
        "strong_assets": strong_records,
    }


def render_judgment_assets(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
) -> str:
    summary = judgment_asset_summary(decisions, judgments, active_protocol=active_protocol)
    counts = summary["counts"]
    lists = summary["lists"]
    relation_rows = collect_curated_relation_rows(root, decisions + judgments)
    unresolved_relation_rows = [row for row in relation_rows if row.get("resolved") != "true"]
    lines = [
        "# 判断资产",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 决策页：`{counts['decisions']}`",
        f"- 判断页：`{counts['judgments']}`",
        f"- 资产完整（>= 3/4）：`{counts['strong_assets']}`",
        f"- 治理焦点：`{counts['attention_pages']}`",
        f"- 生命周期 formed / active / under-review / revised / retired：`{counts['formed_lifecycle']}` / `{counts['active_lifecycle']}` / `{counts['under_review_lifecycle']}` / `{counts['revised_lifecycle']}` / `{counts['retired_lifecycle']}`",
        f"- 缺反证：`{counts['missing_counter_evidence']}`",
        f"- 缺失效条件：`{counts['missing_invalidation']}`",
        f"- 缺下一信号：`{counts['missing_next_signals']}`",
        f"- 缺复审历史：`{counts['missing_review_history']}`",
        f"- 缺 Counter Evidence metadata：`{counts['missing_counter_evidence_metadata']}`",
        f"- 缺 Invalidation metadata：`{counts['missing_invalidation_rule_metadata']}`",
        f"- 缺 Next Signals metadata：`{counts['missing_next_signals_metadata']}`",
        f"- 缺 formed_at / last_reviewed metadata：`{counts['missing_formed_at_metadata']}` / `{counts['missing_last_reviewed_metadata']}`",
        f"- 升级处理项：`{counts['escalation_candidates']}`",
        f"- 显式 judgment 关系边：`{len(relation_rows)}`",
        f"- 未解析关系引用：`{len(unresolved_relation_rows)}`",
        "",
        "## 当前治理焦点",
    ]
    if not lists["attention_pages"]:
        lines.append("- 当前没有需要额外关注的 decision / judgment 页面。")
    else:
        for page in lists["attention_pages"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 强判断资产",
        ]
    )
    if not lists["strong_assets"]:
        lines.append("- 当前还没有资产完整度较高的 decision / judgment 页面。")
    else:
        for page in lists["strong_assets"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Judgment 关联图谱"])
    if not relation_rows:
        lines.append("- 当前还没有显式 judgment / decision 关系。")
    else:
        for row in relation_rows[:16]:
            source_ref = f"[{row['source_title']}](../{row['source_path']})"
            if row.get("target_path"):
                target_ref = f"[{row['target_title']}](../{row['target_path']})"
            else:
                target_ref = f"`{row['target_title']}`"
            relation_note = ""
            if row.get("resolved") != "true":
                relation_note = " | unresolved"
            lines.append(f"- {source_ref} | {row['relation']} -> {target_ref}{relation_note}")
    lines.extend(["", "## 升级处理项"])
    if not lists["escalation_candidates"]:
        lines.append("- 当前没有需要升级处理的 judgment asset。")
    else:
        for page in lists["escalation_candidates"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Counter Evidence"])
    if not lists["missing_counter_evidence"]:
        lines.append("- 当前所有判断资产都包含显式 counter evidence。")
    else:
        for page in lists["missing_counter_evidence"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Structured Counter Evidence Metadata"])
    if not lists["missing_counter_evidence_metadata"]:
        lines.append("- 当前所有判断资产都携带 `counter_evidence` frontmatter 字段。")
    else:
        for page in lists["missing_counter_evidence_metadata"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Invalidation"])
    if not lists["missing_invalidation"]:
        lines.append("- 当前所有判断资产都包含显式 invalidation 条件。")
    else:
        for page in lists["missing_invalidation"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Structured Invalidation Metadata"])
    if not lists["missing_invalidation_rule_metadata"]:
        lines.append("- 当前所有判断资产都携带 `invalidation_rule` frontmatter 字段。")
    else:
        for page in lists["missing_invalidation_rule_metadata"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Next Signals"])
    if not lists["missing_next_signals"]:
        lines.append("- 当前所有判断资产都包含下一次观察信号。")
    else:
        for page in lists["missing_next_signals"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Structured Next Signals Metadata"])
    if not lists["missing_next_signals_metadata"]:
        lines.append("- 当前所有判断资产都携带 `next_signals` frontmatter 字段。")
    else:
        for page in lists["missing_next_signals_metadata"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 缺 Review History"])
    if not lists["missing_review_history"]:
        lines.append("- 当前所有判断资产都已经积累复审历史。")
    else:
        for page in lists["missing_review_history"][:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"
