"""Dashboard and shell-facing render surface owners."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from .app_content import (
    action_supports_low_risk_apply,
    collect_aging_signals,
    compact_section_lines,
    display_action_status,
    display_curated_status,
    display_judgment_lifecycle_state,
    display_knowledge_lifecycle_state,
    display_rewrite_proposal_status,
    furnace_quick_commands,
    judgment_asset_summary,
    knowledge_lifecycle_governance_summary,
    protocol_execution_receipts,
    protocol_output_pack_rows,
    protocol_scorecard,
    render_curated_page_summary,
    render_knowledge_lifecycle_entry_summary,
    review_history_entries,
    review_queue,
    select_knowledge_lifecycle_entries,
    sort_curated_pages,
    sort_knowledge_lifecycle_entries,
)
from .app_memory import (
    render_execution_audit,
    render_execution_audit_html,
    render_execution_center,
    render_execution_center_html,
    render_machine_memory_graph_html,
)
from .app_protocol import PROTOCOL_LIBRARY, page_focus_score, protocol_title
from .app_state import (
    DEFAULT_PROTOCOL,
    default_compile_state,
    default_knowledge_lifecycle_state,
    load_knowledge_lifecycle_state,
    load_runtime_history,
)
from .app_utils import parse_frontmatter


def _frontmatter_relation_values(frontmatter: dict[str, Any], key: str) -> list[str]:
    value = frontmatter.get(key, [])
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _resolve_curated_relation_reference(
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


def _collect_curated_relation_rows(root: Path, pages: list[dict[str, str]]) -> list[dict[str, str]]:
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
            for reference in _frontmatter_relation_values(frontmatter, key):
                resolved = _resolve_curated_relation_reference(
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
                        "target_title": str(
                            (resolved or {}).get("title") or reference or "unknown relation target"
                        ),
                        "target_path": str((resolved or {}).get("path") or ""),
                        "target_id": target_id,
                        "resolved": "true" if resolved else "false",
                    }
                )
    return rows


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
    relation_rows = _collect_curated_relation_rows(root, decisions + judgments)
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


def render_cognitive_history(
    root: Path,
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or load_knowledge_lifecycle_state(root)
    pages = sort_curated_pages(decisions + judgments)
    drifted_pages = sorted(
        [page for page in pages if page.get("citation_drift") == "true"],
        key=lambda page: (
            0 if page.get("escalation_candidate") == "true" else 1,
            0 if page.get("overdue_review") == "true" else 1,
            -int(page.get("citation_drift_count", "0") or "0"),
            -page_focus_score(active_protocol, page),
            page.get("title", "").lower(),
        ),
    )
    snapshot_gap_pages = sorted(
        [page for page in pages if int(page.get("citation_snapshot_gap_count", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("citation_snapshot_gap_count", "0") or "0"),
            0 if page.get("pending_review") == "true" else 1,
            page.get("title", "").lower(),
        ),
    )
    long_history_pages = sorted(
        [page for page in pages if int(page.get("review_history_entries", "0") or "0") > 0],
        key=lambda page: (
            -int(page.get("review_history_entries", "0") or "0"),
            page.get("reviewed_at", "") or "",
            page.get("title", "").lower(),
        ),
        reverse=True,
    )
    lifecycle_revisit_entries = sort_knowledge_lifecycle_entries(
        select_knowledge_lifecycle_entries(
            knowledge_lifecycle,
            states={"revisit"},
        ),
        active_protocol=active_protocol,
    )
    lifecycle_entry_titles = {
        str(entry.get("path") or ""): str(entry.get("title") or entry.get("page_id") or "")
        for entry in knowledge_lifecycle.get("entries", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    page_titles_by_path = {
        str(page.get("path") or ""): str(page.get("title") or page.get("page_id") or "")
        for page in pages
        if page.get("path")
    }
    concept_override_events: list[tuple[str, str, str, str]] = []
    judgment_lifecycle_events: list[tuple[str, str, str, str]] = []
    judgment_relation_events: list[tuple[str, list[dict[str, str]], list[dict[str, str]]]] = []
    nightly_escalation_events: list[tuple[str, list[str], list[str]]] = []
    rewrite_events: list[tuple[str, str, str, str]] = []
    for event in load_runtime_history(root):
        event_type = str(event.get("event_type") or "")
        if event_type == "knowledge-lifecycle-override" and str(event.get("kind") or "") == "concept":
            occurred_at = str(event.get("occurred_at") or "")
            path = str(event.get("path") or "")
            title = lifecycle_entry_titles.get(path) or str(event.get("slug") or path or "unknown concept")
            operation = str(event.get("operation") or "override")
            lifecycle_state = str(event.get("lifecycle_state") or "")
            concept_override_events.append((occurred_at, title, path, f"{operation} -> {lifecycle_state or 'unknown'}"))
            continue
        if event_type == "review" and str(event.get("page_kind") or "") in {"decision", "judgment"}:
            occurred_at = str(event.get("occurred_at") or "")
            path = str(event.get("page_path") or "")
            title = lifecycle_entry_titles.get(path) or str(event.get("page_id") or path or "unknown judgment")
            lifecycle_state = str(event.get("judgment_lifecycle_state") or "")
            status = str(event.get("status") or "")
            detail = f"review -> {display_judgment_lifecycle_state(lifecycle_state)}"
            if status:
                detail += f" | status {display_curated_status(status)}"
            judgment_lifecycle_events.append((occurred_at, title, path, detail))
            continue
        if event_type == "judgment-relation-refresh":
            occurred_at = str(event.get("occurred_at") or "")
            added_relations = [
                relation
                for relation in event.get("added_relations", [])
                if isinstance(relation, dict)
            ]
            removed_relations = [
                relation
                for relation in event.get("removed_relations", [])
                if isinstance(relation, dict)
            ]
            if added_relations or removed_relations:
                judgment_relation_events.append((occurred_at, added_relations, removed_relations))
            continue
        if event_type == "nightly":
            overdue_pages = [
                str(path)
                for path in event.get("overdue_pages", [])
                if isinstance(path, str) and path.strip()
            ]
            escalated_pages = [
                str(path)
                for path in event.get("escalated_pages", [])
                if isinstance(path, str) and path.strip()
            ]
            if overdue_pages or escalated_pages:
                nightly_escalation_events.append(
                    (
                        str(event.get("occurred_at") or ""),
                        overdue_pages,
                        escalated_pages,
                    )
                )
            continue
        if event_type in {"rewrite-review", "rewrite-apply", "rewrite-verify", "rewrite-revert"}:
            occurred_at = str(event.get("occurred_at") or "")
            path = str(event.get("target_path") or "")
            title = lifecycle_entry_titles.get(path) or str(event.get("slug") or path or "unknown concept")
            detail = event_type.replace("rewrite-", "rewrite -> ")
            if event_type == "rewrite-review":
                detail = f"review -> {display_rewrite_proposal_status(str(event.get('status') or 'proposed'))}"
            elif event_type == "rewrite-apply":
                detail = f"apply -> verification {str(event.get('verification_status') or 'pending')}"
            elif event_type == "rewrite-verify":
                detail = f"verify -> {str(event.get('status') or 'unknown')}"
            elif event_type == "rewrite-revert":
                detail = "revert -> accepted"
            rewrite_events.append((occurred_at, title, path, detail))
    concept_override_events.sort(key=lambda item: item[0], reverse=True)
    judgment_lifecycle_events.sort(key=lambda item: item[0], reverse=True)
    judgment_relation_events.sort(key=lambda item: item[0], reverse=True)
    nightly_escalation_events.sort(key=lambda item: item[0], reverse=True)
    rewrite_events.sort(key=lambda item: item[0], reverse=True)
    recent_events: list[tuple[str, str, str, str]] = []
    for page in pages:
        page_path = root / page["path"]
        if not page_path.exists():
            continue
        content = page_path.read_text(encoding="utf-8", errors="replace")
        for entry in review_history_entries(content)[:3]:
            match = re.match(r"- `([^`]+)`", entry)
            reviewed_at = match.group(1) if match else ""
            recent_events.append((reviewed_at, page["title"], page["path"], entry))
    recent_events.sort(key=lambda item: item[0], reverse=True)
    lines = [
        "# 认知历史",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议焦点：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- decision / judgment 页面：`{len(pages)}`",
        f"- 证据漂移页面：`{len(drifted_pages)}`",
        f"- snapshot 缺口页面：`{len(snapshot_gap_pages)}`",
        f"- 有复审历史的页面：`{len(long_history_pages)}`",
        f"- 生命周期待回看项：`{len(lifecycle_revisit_entries)}`",
        f"- concept lifecycle 事件：`{len(concept_override_events)}`",
        f"- judgment lifecycle 事件：`{len(judgment_lifecycle_events)}`",
        f"- judgment relation 事件：`{len(judgment_relation_events)}`",
        f"- nightly 升级事件：`{len(nightly_escalation_events)}`",
        f"- concept rewrite 事件：`{len(rewrite_events)}`",
        "",
        "## 证据漂移",
    ]
    if not drifted_pages:
        lines.append("- 当前没有 reviewed judgment / decision 因 citation drift 被标记。")
    else:
        for page in drifted_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## Snapshot 缺口"])
    if not snapshot_gap_pages:
        lines.append("- 当前没有 citation snapshot 缺口。")
    else:
        for page in snapshot_gap_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(["", "## 生命周期待回看项"])
    if not lifecycle_revisit_entries:
        lines.append("- 当前没有 lifecycle state 标记为 `revisit` 的知识项。")
    else:
        for entry in lifecycle_revisit_entries[:16]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "## 概念生命周期事件"])
    if not concept_override_events:
        lines.append("- 当前还没有 concept lifecycle override 事件。")
    else:
        for occurred_at, title, path, detail in concept_override_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}"
            )
    lines.extend(["", "## Judgment 生命周期事件"])
    if not judgment_lifecycle_events:
        lines.append("- 当前还没有 judgment lifecycle 事件。")
    else:
        for occurred_at, title, path, detail in judgment_lifecycle_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}"
            )
    lines.extend(["", "## Judgment 关系事件"])
    if not judgment_relation_events:
        lines.append("- 当前还没有 judgment relation change 事件。")
    else:
        for occurred_at, added_relations, removed_relations in judgment_relation_events[:20]:
            summary_parts: list[str] = []
            if added_relations:
                summary_parts.append(f"added `{len(added_relations)}`")
            if removed_relations:
                summary_parts.append(f"removed `{len(removed_relations)}`")
            samples: list[str] = []
            for relation in added_relations[:2]:
                source_ref = (
                    f"[{relation.get('source_title') or relation.get('source_id') or 'unknown'}]"
                    f"(../../{relation.get('source_path')})"
                    if relation.get("source_path")
                    else str(relation.get("source_title") or relation.get("source_id") or "unknown")
                )
                target_ref = (
                    f"[{relation.get('target_title') or relation.get('target_id') or 'unknown'}]"
                    f"(../../{relation.get('target_path')})"
                    if relation.get("target_path")
                    else str(relation.get("target_title") or relation.get("target_id") or "unknown")
                )
                samples.append(f"+ {relation.get('relation_kind') or 'judgment'}:{relation.get('relation') or 'related'} {source_ref} -> {target_ref}")
            for relation in removed_relations[:2]:
                source_ref = (
                    f"[{relation.get('source_title') or relation.get('source_id') or 'unknown'}]"
                    f"(../../{relation.get('source_path')})"
                    if relation.get("source_path")
                    else str(relation.get("source_title") or relation.get("source_id") or "unknown")
                )
                target_ref = (
                    f"[{relation.get('target_title') or relation.get('target_id') or 'unknown'}]"
                    f"(../../{relation.get('target_path')})"
                    if relation.get("target_path")
                    else str(relation.get("target_title") or relation.get("target_id") or "unknown")
                )
                samples.append(f"- {relation.get('relation_kind') or 'judgment'}:{relation.get('relation') or 'related'} {source_ref} -> {target_ref}")
            detail = " | ".join(summary_parts) if summary_parts else "no relation delta"
            if samples:
                detail = f"{detail} | {'; '.join(samples)}"
            lines.append(f"- occurred `{occurred_at or 'unknown'}` | {detail}")
    lines.extend(["", "## Nightly 升级事件"])
    if not nightly_escalation_events:
        lines.append("- 当前还没有 nightly escalation 事件。")
    else:
        for occurred_at, overdue_pages, escalated_pages in nightly_escalation_events[:20]:
            overdue_titles = [
                f"[{page_titles_by_path.get(path, path)}](../../{path})"
                for path in overdue_pages[:3]
            ]
            escalated_titles = [
                f"[{page_titles_by_path.get(path, path)}](../../{path})"
                for path in escalated_pages[:3]
            ]
            detail_parts = [
                f"overdue `{len(overdue_pages)}`",
                f"escalated `{len(escalated_pages)}`",
            ]
            if escalated_titles:
                detail_parts.append(f"focus {'; '.join(escalated_titles)}")
            elif overdue_titles:
                detail_parts.append(f"focus {'; '.join(overdue_titles)}")
            lines.append(f"- occurred `{occurred_at or 'unknown'}` | {' | '.join(detail_parts)}")
    lines.extend(["", "## Concept Rewrite 事件"])
    if not rewrite_events:
        lines.append("- 当前还没有 concept rewrite 事件。")
    else:
        for occurred_at, title, path, detail in rewrite_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}"
            )
    lines.extend(["", "## 最近认知事件"])
    if not recent_events:
        lines.append("- 当前还没有 review history 事件。")
    else:
        for reviewed_at, title, path, entry in recent_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | reviewed `{reviewed_at or 'unknown'}` | {entry.replace(f'- `{reviewed_at}` | ', '') if reviewed_at else entry}"
            )
    lines.extend(["", "## 长历史页面"])
    if not long_history_pages:
        lines.append("- 当前还没有积累多轮复审历史的页面。")
    else:
        for page in long_history_pages[:12]:
            lines.append(render_curated_page_summary(page))
    lines.extend(
        [
            "",
            "## 建议动作",
        ]
    )
    if drifted_pages:
        lines.append(f"- 先复查 `{len(drifted_pages)}` 个被新证据挑战的 decision / judgment。")
    if snapshot_gap_pages:
        lines.append(f"- 补齐 `{len(snapshot_gap_pages)}` 个缺少 citation snapshot 的页面，避免 drift 失真。")
    if long_history_pages:
        lines.append(f"- 从 `{min(len(long_history_pages), 5)}` 个长历史页面里提炼更稳定的 judgment pattern。")
    if judgment_relation_events:
        lines.append(f"- 复查最近 `{min(len(judgment_relation_events), 5)}` 次 judgment relation 变更，确认支持/反证关系仍然有效。")
    if nightly_escalation_events:
        lines.append(f"- 优先处理最近 `{min(len(nightly_escalation_events), 5)}` 次 nightly 升级事件里仍然活跃的页面。")
    if rewrite_events:
        lines.append(f"- 检查最近 `{min(len(rewrite_events), 5)}` 个 concept rewrite 事件，确认 verify / revert 闭环已经跑通。")
    if not any((drifted_pages, snapshot_gap_pages, long_history_pages, judgment_relation_events, nightly_escalation_events)):
        lines.append("- 当前认知历史层比较干净，继续靠 nightly 累积 review history。")
    lines.extend(
        [
            "",
            "## 相关链接",
            "- [决策索引](./decisions.md)",
            "- [判断索引](./judgments.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [审阅队列](./review-queue.md)",
            "- [审阅中心](./review-center.md)",
            "- [Aging 报告](./aging-report.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def render_review_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    *,
    active_protocol: str = DEFAULT_PROTOCOL,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    knowledge_lifecycle = knowledge_lifecycle or default_knowledge_lifecycle_state()
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = plan.get("ready_actions", [])
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_candidates = concept_quality.get("rewrite_candidates", [])
    conflict_signals = concept_quality.get("conflict_signals", [])
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    judgment_lifecycle_focus = lifecycle_summary.get("under_review_judgments", []) + lifecycle_summary.get("revised_judgments", [])

    def render_page_item(page: dict[str, str]) -> str:
        path = html.escape(f"../../{page['path']}")
        status = html.escape(display_curated_status(page.get("status", "") or "unknown"))
        revisit = html.escape(page.get("revisit_after", "") or "none")
        return (
            f'<li><a href="{path}">{html.escape(page["title"])}</a>'
            f" | status {status}"
            f" | revisit {revisit}</li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        primary = html.escape(str(action.get("primary_path") or ""))
        status = html.escape(display_action_status(str(action.get("status") or "proposed")))
        priority = html.escape(str(action.get("priority") or "medium"))
        detail = ""
        if action.get("secondary_path"):
            detail = f" | secondary <code>{html.escape(str(action['secondary_path']))}</code>"
        command = ""
        if action.get("command_hint"):
            command = f" | command <code>{html.escape(str(action['command_hint']))}</code>"
        return (
            f"<li>{html.escape(str(action.get('title') or 'unnamed action'))}"
            f" | priority {priority}"
            f" | status {status}"
            f" | primary <code>{primary}</code>{detail}{command}</li>"
        )

    def render_concept_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        issues = html.escape(", ".join(item.get("issues", [])) or "none")
        return (
            f'<li><a href="../../wiki/concepts/{slug}.md">{title}</a>'
            f" | issues {issues}"
            f" | sources {int(item.get('source_count', 0))}</li>"
        )

    def render_rewrite_item(item: dict[str, Any]) -> str:
        slug = html.escape(str(item.get("slug") or ""))
        title = html.escape(str(item.get("title") or slug))
        status = html.escape(display_rewrite_proposal_status(str(item.get("status") or "proposed")))
        return (
            f'<li><a href="../../wiki/rewrite-proposals/{slug}.md">{title}</a>'
            f" | status {status}"
            f" | apply_ready {html.escape(str(bool(item.get('apply_ready'))).lower())}</li>"
        )

    def render_review_action_item(action: dict[str, Any]) -> str:
        command = html.escape(str(action.get("review_command") or ""))
        return (
            f"<li><a href=\"../../{html.escape(str(action.get('page_path') or ''))}\">{html.escape(str(action.get('title') or 'review action'))}</a>"
            f" | priority {html.escape(str(action.get('priority') or 'medium'))}"
            f" | reasons {html.escape(', '.join(action.get('reason_codes', [])) or 'none')}"
            f"{f' | command <code>{command}</code>' if command else ''}</li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        kind = str(entry.get("kind") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        judgment_state = ""
        if kind in {"decision", "judgment"} and str(entry.get("judgment_lifecycle_state") or ""):
            judgment_state = (
                " | judgment "
                + html.escape(display_judgment_lifecycle_state(str(entry.get("judgment_lifecycle_state") or "")))
            )
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"

    pending_list = "".join(render_page_item(page) for page in pending_items[:12]) or "<li>当前没有待审项目。</li>"
    overdue_list = "".join(render_page_item(page) for page in aging.get("overdue", [])[:10]) or "<li>当前没有已到期待复审页面。</li>"
    escalated_list = "".join(render_page_item(page) for page in aging.get("escalated", [])[:10]) or "<li>当前没有需要升级处理的页面。</li>"
    lifecycle_backlog_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_list = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    ready_action_list = "".join(render_action_item(action) for action in ready_actions[:10]) or "<li>当前没有 ready repair action。</li>"
    apply_ready_action_list = (
        "".join(render_action_item(action) for action in apply_ready_actions[:8])
        or "<li>当前没有可直接 semi-auto apply 的低风险动作。</li>"
    )
    rewrite_list = "".join(render_concept_item(item) for item in rewrite_candidates[:10]) or "<li>当前没有高优先级弱概念页。</li>"
    conflict_list = "".join(render_concept_item(item) for item in conflict_signals[:10]) or "<li>当前没有显式概念冲突信号。</li>"
    rewrite_proposal_list = "".join(render_rewrite_item(item) for item in rewrite_proposals[:10]) or "<li>当前没有 rewrite proposal。</li>"
    judgment_action_list = (
        "".join(render_review_action_item(action) for action in judgment_review_actions[:10])
        or "<li>当前没有 judgment review action。</li>"
    )
    judgment_lifecycle_list = (
        "".join(render_lifecycle_item(entry) for entry in judgment_lifecycle_focus[:10])
        or "<li>当前没有 judgment lifecycle 焦点。</li>"
    )

    summary_cards = [
        ("待审项目", str(len(pending_items))),
        ("已到期复审", str(len(aging.get("overdue", [])))),
        ("升级项", str(len(aging.get("escalated", [])))),
        ("Judgment 复审中", str(lifecycle_summary.get("counts", {}).get("under_review_judgments", 0))),
        ("Judgment 修订态", str(lifecycle_summary.get("counts", {}).get("revised_judgments", 0))),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("Judgment Actions", str(len(judgment_review_actions))),
        ("ready actions", str(plan.get("counts", {}).get("ready", 0))),
        ("重写候选", str(concept_quality.get("counts", {}).get("rewrite_candidates", 0))),
        ("冲突信号", str(concept_quality.get("counts", {}).get("conflict_signals", 0))),
        ("rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可应用 rewrite", str(len(apply_ready_rewrites))),
        ("可应用动作", str(len(apply_ready_actions))),
    ]

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Review Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #fffaf0; --ink: #1f2937; --muted: #6b7280; --panel: #ffffff; --line: #e5e7eb; }",
            "    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #fffaf0 0%, #f3f4f6 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1120px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: rgba(255,255,255,0.94); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; margin-bottom: 18px; }",
            "    .meta, .lists { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); margin: 18px 0 24px; }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #b45309; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    .lists { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 4px 0; }",
            "    a { color: #92400e; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    code { background: #f3f4f6; padding: 1px 5px; border-radius: 6px; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel">',
            "    <h1>Review Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议焦点：<code>{html.escape(active_protocol)}</code>。这是炼丹炉的人用审阅 cockpit：把 review、aging、repair 和 concept rewrite 收在一个地方。</p>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="lists">',
            '    <div class="panel"><h2>待审项目</h2><ul>',
            f"{pending_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已到期 / 需升级</h2><ul>',
            f"{overdue_list}",
            f"{escalated_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Judgment Lifecycle Focus</h2><ul>',
            f"{judgment_lifecycle_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Judgment Review Actions</h2><ul>',
            f"{judgment_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>生命周期概念待审</h2><ul>',
            f"{lifecycle_backlog_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>已退役概念</h2><ul>',
            f"{retired_concept_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Ready Repair Actions</h2><ul>',
            f"{ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Safe Apply Actions</h2><ul>',
            f"{apply_ready_action_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念重写优先级</h2><ul>',
            f"{rewrite_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>概念冲突信号</h2><ul>',
            f"{conflict_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>Rewrite Proposals</h2><ul>',
            f"{rewrite_proposal_list}",
            "    </ul></div>",
            '    <div class="panel"><h2>相关入口</h2><ul>',
            '      <li><a href="../../wiki/indexes/furnace-center.md">炉心面板</a></li>',
            '      <li><a href="../../wiki/indexes/review-center.md">Review Center Dashboard</a></li>',
            '      <li><a href="../../wiki/indexes/review-queue.md">审阅队列</a></li>',
            '      <li><a href="../../wiki/indexes/aging-report.md">Aging 报告</a></li>',
            '      <li><a href="../../wiki/indexes/cognitive-history.md">认知历史</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-actions.md">机器记忆动作队列</a></li>',
            '      <li><a href="../../wiki/indexes/machine-memory-repair-plan.md">机器记忆修复计划</a></li>',
            '      <li><a href="../../wiki/indexes/judgment-assets.md">判断资产</a></li>',
            '      <li><a href="../../wiki/indexes/execution-center.md">执行中心</a></li>',
            '      <li><a href="../../wiki/indexes/concept-quality.md">概念质量</a></li>',
            '      <li><a href="../../wiki/indexes/rewrite-proposals.md">Rewrite Proposals</a></li>',
            "    </ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_furnace_center(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    concept_backlog = lifecycle_summary.get("concept_backlog", [])
    retired_concepts = lifecycle_summary.get("retired_concepts", [])
    lifecycle_counts = lifecycle_summary.get("counts", {})
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    rewrite_state = health.get("concept_rewrite", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    citation_drift_count = sum(1 for page in decisions + judgments if page.get("citation_drift") == "true")
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    judgment_lifecycle_focus = lifecycle_summary.get("under_review_judgments", []) + lifecycle_summary.get("revised_judgments", [])
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:6]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)
    next_steps: list[str] = []
    if concept_backlog:
        next_steps.append(f"先处理 `{min(len(concept_backlog), 5)}` 个 lifecycle concept backlog。")
    if judgment_review_actions:
        next_steps.append(f"先清理 `{min(len(judgment_review_actions), 5)}` 个 judgment review action。")
    if apply_ready_actions:
        next_steps.append(f"先处理 `{len(apply_ready_actions)}` 个可直接 `apply-action` 的低风险动作。")
    if apply_ready_rewrites:
        next_steps.append(f"应用 `{len(apply_ready_rewrites)}` 个已接受的 concept rewrite proposal。")
    if aging.get("escalated"):
        next_steps.append(f"优先复查 `{len(aging.get('escalated', []))}` 个升级项。")
    if pending_items:
        next_steps.append(f"继续审 `{len(pending_items)}` 个 decision / judgment 页面。")
    if retired_concepts and not concept_backlog:
        next_steps.append(f"检查 `{min(len(retired_concepts), 3)}` 个 retired concept 是否需要重新激活。")
    if not next_steps:
        next_steps.append("当前没有紧急执行项，优先看最新输出和图谱漂移。")

    lines = [
        "# 炉心面板",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 当前协议：`{active_protocol}` ({protocol_title(active_protocol)})",
        f"- 来源节点：`{len(memory.get('source_nodes', []))}`",
        f"- 概念节点：`{len(memory.get('concept_nodes', []))}`",
        f"- 待审项目：`{len(pending_items)}`",
        f"- 已到期 / 升级：`{len(aging.get('overdue', []))}` / `{len(aging.get('escalated', []))}`",
        f"- Judgment formed / active / under-review / revised / retired：`{lifecycle_counts.get('formed_judgments', 0)}` / `{lifecycle_counts.get('active_judgments', 0)}` / `{lifecycle_counts.get('under_review_judgments', 0)}` / `{lifecycle_counts.get('revised_judgments', 0)}` / `{lifecycle_counts.get('retired_judgments', 0)}`",
        f"- 生命周期概念待审 / 已退役：`{lifecycle_counts.get('concept_backlog', len(concept_backlog))}` / `{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
        f"- 证据漂移：`{citation_drift_count}`",
        f"- Judgment review actions：`{len(judgment_review_actions)}`",
        f"- Ready repair actions：`{len(ready_actions)}`",
        f"- 可直接 apply 的动作：`{len(apply_ready_actions)}`",
        f"- Rewrite 提案：`{rewrite_state.get('counts', {}).get('active', 0)}`",
        f"- 可直接 apply 的 rewrite：`{len(apply_ready_rewrites)}`",
        f"- 页级 patch step：`{page_patch_steps}`",
        f"- 当前协议 stage：`{scorecard.get('stage', 'seed') if scorecard else 'unknown'}`",
        f"- 当前协议 outputs / receipts：`{scorecard_metrics.get('outputs', 0)}` / `{scorecard_metrics.get('receipts', 0)}`",
        f"- 当前协议 review packs / memos / SOP：`{scorecard_metrics.get('review_packs', 0)}` / `{scorecard_metrics.get('decision_memos', 0)}` / `{scorecard_metrics.get('sop_drafts', 0)}`",
        f"- 最近输出：`{len(recent_outputs)}`",
        "- 本地控制面板：`output/control/furnace-center.html`",
        "",
        "## 今天先做什么",
    ]
    for index, step in enumerate(next_steps, start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "## 即刻可执行",
        ]
    )
    if apply_ready_actions:
        lines.append("### Safe Apply Actions")
        for action in apply_ready_actions[:8]:
            lines.append(
                f"- `{action['title']}` | command `{action.get('command_hint', '')}`"
                f" | primary `{action.get('primary_path', '')}`"
            )
    if apply_ready_rewrites:
        lines.append("")
        lines.append("### Apply-Ready Rewrites")
        for proposal in apply_ready_rewrites[:8]:
            lines.append(
                f"- `{proposal['target_path']}` | command `PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {proposal['slug']}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Execution Proposals")
        for proposal in execution_proposals[:8]:
            lines.append(
                f"- `{proposal['action_id']}` | risk `{proposal.get('risk', 'medium')}`"
                f" | targets `{', '.join(proposal.get('target_paths', [])) or 'none'}`"
            )
    if execution_proposals:
        lines.append("")
        lines.append("### Page-Level Patch Plan")
        for proposal in execution_proposals[:4]:
            patch_plan = proposal.get("page_patch_plan", [])
            if not patch_plan:
                continue
            lines.append(f"- `{proposal['action_id']}` | patch step `{len(patch_plan)}`")
            for patch in patch_plan[:3]:
                lines.append(
                    f"  - `{patch.get('path', '')}`"
                    f" | mode `{patch.get('mode', 'update')}`"
                    f" | sections `{', '.join(patch.get('sections', [])) or 'none'}`"
                )
    if not any((apply_ready_actions, apply_ready_rewrites, execution_proposals)):
        lines.append("- 当前没有即刻可执行项。")

    lines.extend(
        [
            "",
            "## 最近输出",
        ]
    )
    if not recent_outputs:
        lines.append("- 当前还没有 recent outputs。")
    else:
        for artifact in recent_outputs:
            lines.append(
                f"- [{artifact['title']}](../../{artifact['path']})"
                f" | format `{artifact['format'] or 'unknown'}`"
                f" | protocol `{artifact['protocol'] or DEFAULT_PROTOCOL}`"
                f" | created `{artifact['created_at'] or 'unknown'}`"
            )

    lines.extend(["", "## 当前协议 Pilot"])
    if not scorecard:
        lines.append("- 当前协议还没有 pilot scorecard。")
    else:
        lines.append(
            f"- [{scorecard['title']}](../../{scorecard['path']})"
            f" | stage `{scorecard.get('stage', 'seed')}`"
            f" | {scorecard.get('summary', '')}"
        )
        gaps = compact_section_lines(scorecard.get("content", ""), "Gaps", fallback="- 当前没有明显结构性缺口。", limit=4)
        lines.append("")
        lines.append("### 当前缺口")
        lines.extend(gaps)
        next_moves_lines = compact_section_lines(scorecard.get("content", ""), "Next Moves", fallback="- 当前没有额外 next moves。", limit=4)
        lines.append("")
        lines.append("### 下一动作")
        lines.extend(next_moves_lines)

    lines.extend(["", "## Lifecycle 治理摘要"])
    lines.extend(
        [
            f"- review concepts：`{lifecycle_counts.get('review_concepts', 0)}`",
            f"- revisit concepts：`{lifecycle_counts.get('revisit_concepts', 0)}`",
            f"- retired concepts：`{lifecycle_counts.get('retired_concepts', len(retired_concepts))}`",
            f"- active concepts：`{lifecycle_counts.get('active_concepts', 0)}`",
            f"- formed judgments：`{lifecycle_counts.get('formed_judgments', 0)}`",
            f"- active judgments：`{lifecycle_counts.get('active_judgments', 0)}`",
            f"- under-review judgments：`{lifecycle_counts.get('under_review_judgments', 0)}`",
            f"- revised judgments：`{lifecycle_counts.get('revised_judgments', 0)}`",
            f"- retired judgments：`{lifecycle_counts.get('retired_judgments', 0)}`",
            "",
            "### Lifecycle Concept Backlog",
        ]
    )
    if not concept_backlog:
        lines.append("- 当前没有 lifecycle-driven concept backlog。")
    else:
        for entry in concept_backlog[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Retired Concepts"])
    if not retired_concepts:
        lines.append("- 当前没有 retired concept。")
    else:
        for entry in retired_concepts[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Judgment Lifecycle Focus"])
    if not judgment_lifecycle_focus:
        lines.append("- 当前没有 judgment lifecycle 焦点。")
    else:
        for entry in judgment_lifecycle_focus[:12]:
            lines.append(render_knowledge_lifecycle_entry_summary(entry))
    lines.extend(["", "### Judgment Review Actions"])
    if not judgment_review_actions:
        lines.append("- 当前没有 judgment review action。")
    else:
        for action in judgment_review_actions[:10]:
            command = str(action.get("review_command") or "")
            command_suffix = f" | command `{command}`" if command else ""
            lines.append(
                f"- `{action.get('title', 'review action')}`"
                f" | priority `{action.get('priority', 'medium')}`"
                f" | reasons `{', '.join(action.get('reason_codes', [])) or 'none'}`"
                f"{command_suffix}"
            )

    lines.extend(["", "## 最新输出 Packs"])
    if not pack_rows:
        lines.append("- 当前协议还没有 review pack / decision memo / SOP draft。")
    else:
        for pack in pack_rows:
            lines.append(
                f"- [{pack['title']}](../../{pack['path']})"
                f" | kind `{pack['kind']}`"
                f" | meta `{pack['meta'] or 'n/a'}`"
            )

    lines.extend(["", "## 最近执行回执"])
    if not receipt_rows:
        lines.append("- 当前协议还没有 execution receipt。")
    else:
        for receipt in receipt_rows:
            receipt_path = receipt["receipt_path"] or ".aiwiki/state/execution-receipts.jsonl"
            lines.append(
                f"- `{receipt['title']}`"
                f" | kind `{receipt['kind']}`"
                f" | action `{receipt['action_id']}`"
                f" | receipt `{receipt_path}`"
                f" | at `{receipt['applied_at'] or 'unknown'}`"
            )

    lines.extend(
        [
            "",
            "## 最近已审 / 已沉淀",
        ]
    )
    if recent_reviewed:
        for page in recent_reviewed:
            lines.append(
                f"- [{page['title']}](../../{page['path']})"
                f" | status `{display_curated_status(page.get('status', 'unknown'))}`"
                f" | reviewed `{page.get('reviewed_at', '') or 'unknown'}`"
            )
    else:
        lines.append("- 当前还没有最近已审项目。")

    lines.extend(["", "## 快速命令"])
    for command in quick_commands:
        lines.append(f"- `{command}`")

    lines.extend(
        [
            "",
            "## 快速跳转",
            "- [审阅中心](./review-center.md)",
            "- [执行中心](./execution-center.md)",
            "- [执行审计](./execution-audit.md)",
            "- [Agent Workbench](./agent-workbench.md)",
            "- [认知历史](./cognitive-history.md)",
            "- [输出 Pack 总览](./output-packs.md)",
            "- [领域 Pilot 总览](./domain-pilots.md)",
            "- [判断资产](./judgment-assets.md)",
            "- [图谱视图](./graph-view.md)",
            "- [修复待办](./repair-backlog.md)",
            "- [协议总览](./protocols.md)",
            "- [输出面板](../../wiki/indexes/Outputs.md)",
            "- `output/review/review-center.html`：本地审阅面板（浏览器 / 系统 HTML 入口）",
            "- `output/graph/machine-memory.html`：本地图谱视图（若点开变成 Mihomo/Clash，说明系统接管了 `text/html`）",
            "- `output/control/furnace-center.html`：本地炉心面板（浏览器 / 系统 HTML 入口）",
            "- `output/control/execution-center.html`：本地执行面板（浏览器 / 系统 HTML 入口）",
            "- `output/control/execution-audit.html`：本地执行审计面板（浏览器 / 系统 HTML 入口）",
        ]
    )
    return "\n".join(lines) + "\n"


def render_furnace_center_html(
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    memory: dict[str, Any],
    compiled_at: str,
    protocol_state: dict[str, Any],
    recent_outputs: list[dict[str, str]],
    output_packs: dict[str, Any],
    domain_pilots: dict[str, Any],
    execution_audit: dict[str, Any],
    *,
    knowledge_lifecycle: dict[str, Any] | None = None,
) -> str:
    active_protocol = protocol_state["active_protocol"]
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    lifecycle_summary = knowledge_lifecycle_governance_summary(
        knowledge_lifecycle,
        active_protocol=active_protocol,
    )
    health = memory.get("health", {})
    plan = health.get("repair_plan", {})
    concept_quality = health.get("concept_quality", {})
    rewrite_state = health.get("concept_rewrite", {})
    judgment_review_actions = health.get("judgment_review_actions", [])
    pending_items = queue.get("pending_decisions", []) + queue.get("pending_judgments", [])
    ready_actions = [
        action
        for action in plan.get("ready_actions", [])
        if isinstance(action, dict) and str(action.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    apply_ready_actions = [action for action in ready_actions if action_supports_low_risk_apply(action)]
    rewrite_proposals = rewrite_state.get("proposals", [])
    apply_ready_rewrites = [proposal for proposal in rewrite_proposals if proposal.get("apply_ready")]
    execution_proposals = [
        proposal
        for proposal in plan.get("execution_proposals", [])
        if isinstance(proposal, dict) and str(proposal.get("protocol") or DEFAULT_PROTOCOL) == active_protocol
    ]
    judgment_lifecycle_focus = lifecycle_summary.get("under_review_judgments", []) + lifecycle_summary.get("revised_judgments", [])
    page_patch_steps = sum(len(proposal.get("page_patch_plan", [])) for proposal in execution_proposals)
    recent_reviewed = queue.get("recently_reviewed", [])[:8]
    scorecard = protocol_scorecard(domain_pilots, active_protocol)
    scorecard_metrics = scorecard.get("metrics", {}) if isinstance(scorecard, dict) else {}
    pack_rows = protocol_output_pack_rows(output_packs, active_protocol)
    receipt_rows = protocol_execution_receipts(execution_audit, active_protocol)
    quick_commands = furnace_quick_commands(active_protocol, apply_ready_actions, apply_ready_rewrites)

    def render_page_item(page: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(page["path"])}">{html.escape(page["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(display_curated_status(page.get('status', 'unknown')))}</span></li>"
        )

    def render_action_item(action: dict[str, Any]) -> str:
        command = html.escape(str(action.get("command_hint") or ""))
        return (
            f"<li><strong>{html.escape(str(action.get('title') or 'unnamed action'))}</strong>"
            f" <span class=\"item-meta\">{html.escape(str(action.get('priority') or 'medium'))} / {html.escape(display_action_status(str(action.get('status') or 'proposed')))}</span>"
            f"<div><code>{html.escape(str(action.get('primary_path') or ''))}</code></div>"
            f"{f'<div><code>{command}</code></div>' if command else ''}</li>"
        )

    def render_rewrite_item(proposal: dict[str, Any]) -> str:
        slug = html.escape(str(proposal.get("slug") or ""))
        target = html.escape(str(proposal.get("target_path") or f"wiki/concepts/{slug}.md"))
        command = f"PYTHONPATH=src python3 -m aiwiki.cli --root . apply-rewrite {slug}"
        return (
            f"<li><strong><a href=\"../../wiki/rewrite-proposals/{slug}.md\">{html.escape(str(proposal.get('title') or slug))}</a></strong>"
            f" <span class=\"item-meta\">{html.escape(display_rewrite_proposal_status(str(proposal.get('status') or 'proposed')))}</span>"
            f"<div><code>{target}</code></div><div><code>{html.escape(command)}</code></div></li>"
        )

    def render_review_action_item(action: dict[str, Any]) -> str:
        command = html.escape(str(action.get("review_command") or ""))
        return (
            f"<li><strong><a href=\"../../{html.escape(str(action.get('page_path') or ''))}\">{html.escape(str(action.get('title') or 'review action'))}</a></strong>"
            f" <span class=\"item-meta\">{html.escape(str(action.get('priority') or 'medium'))}</span>"
            f"<div>{html.escape(', '.join(action.get('reason_codes', [])) or 'none')}</div>"
            f"{f'<div><code>{command}</code></div>' if command else ''}</li>"
        )

    def render_output_item(artifact: dict[str, str]) -> str:
        return (
            f'<li><a href="../../{html.escape(artifact["path"])}">{html.escape(artifact["title"])}</a>'
            f" <span class=\"item-meta\">{html.escape(artifact['format'] or 'unknown')} / {html.escape(artifact['protocol'] or DEFAULT_PROTOCOL)} / {html.escape(artifact['created_at'] or 'unknown')}</span></li>"
        )

    def render_proposal_item(proposal: dict[str, Any]) -> str:
        patch_count = len(proposal.get("page_patch_plan", []))
        return (
            f"<li><strong>{html.escape(str(proposal.get('action_id') or 'proposal'))}</strong>"
            f" <span class=\"item-meta\">risk {html.escape(str(proposal.get('risk') or 'medium'))}</span>"
            f"<div>{html.escape(str(proposal.get('summary') or ''))}</div>"
            f"<div><code>{html.escape(', '.join(proposal.get('target_paths', [])) or 'none')}</code></div>"
            f"<div class=\"item-meta\">patch steps {patch_count}</div></li>"
        )

    def render_lifecycle_item(entry: dict[str, Any]) -> str:
        path = str(entry.get("path") or "")
        kind = str(entry.get("kind") or "")
        title = html.escape(str(entry.get("title") or entry.get("page_id") or "unknown"))
        state = html.escape(display_knowledge_lifecycle_state(str(entry.get("lifecycle_state") or "")))
        judgment_state = ""
        if kind in {"decision", "judgment"} and str(entry.get("judgment_lifecycle_state") or ""):
            judgment_state = (
                " | judgment "
                + html.escape(display_judgment_lifecycle_state(str(entry.get("judgment_lifecycle_state") or "")))
            )
        override = ""
        if bool(entry.get("override_active")):
            override = f" | override {html.escape(str(entry.get('override_state') or entry.get('lifecycle_state') or 'unknown'))}"
        invalidation_signals = entry.get("invalidation_signals", [])
        invalidation = ""
        if isinstance(invalidation_signals, list) and invalidation_signals:
            invalidation = f" | invalidation {html.escape(', '.join(str(item) for item in invalidation_signals[:3]))}"
        active_corpus_ids = entry.get("active_corpus_ids", [])
        active_corpora = ""
        if isinstance(active_corpus_ids, list) and active_corpus_ids:
            active_corpora = f" | active corpora {html.escape(str(len(active_corpus_ids)))}"
        if path:
            return (
                f'<li><a href="../../{html.escape(path)}">{title}</a>'
                f" | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"
            )
        return f"<li>{title} | state {state}{judgment_state}{override}{invalidation}{active_corpora}</li>"

    summary_cards = [
        ("来源", str(len(memory.get("source_nodes", [])))),
        ("概念", str(len(memory.get("concept_nodes", [])))),
        ("待审", str(len(pending_items))),
        ("到期/升级", f"{len(aging.get('overdue', []))}/{len(aging.get('escalated', []))}"),
        ("Judgment 复审中", str(lifecycle_summary.get("counts", {}).get("under_review_judgments", 0))),
        ("Judgment 修订态", str(lifecycle_summary.get("counts", {}).get("revised_judgments", 0))),
        ("生命周期待审", str(lifecycle_summary.get("counts", {}).get("concept_backlog", 0))),
        ("已退役概念", str(lifecycle_summary.get("counts", {}).get("retired_concepts", 0))),
        ("证据漂移", str(sum(1 for page in decisions + judgments if page.get("citation_drift") == "true"))),
        ("Judgment Actions", str(len(judgment_review_actions))),
        ("Ready 动作", str(plan.get("counts", {}).get("ready", 0))),
        ("可 apply 动作", str(len(apply_ready_actions))),
        ("Rewrite 提案", str(rewrite_state.get("counts", {}).get("active", 0))),
        ("可 apply rewrite", str(len(apply_ready_rewrites))),
        ("Patch Steps", str(page_patch_steps)),
        ("最近输出", str(len(recent_outputs))),
        ("Pilot Stage", str(scorecard.get("stage", "unknown") if scorecard else "unknown")),
        ("Review Packs", str(scorecard_metrics.get("review_packs", 0))),
        ("Decision Memos", str(scorecard_metrics.get("decision_memos", 0))),
        ("SOP Drafts", str(scorecard_metrics.get("sop_drafts", 0))),
        ("Receipts", str(scorecard_metrics.get("receipts", 0))),
    ]

    protocol_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("review", [])[:3]
    nightly_focus = PROTOCOL_LIBRARY.get(active_protocol, {}).get("nightly", [])[:3]
    pending_markup = "".join(render_page_item(page) for page in pending_items[:8]) or "<li>当前没有待审项目。</li>"
    aging_markup = "".join(render_page_item(page) for page in (aging.get("escalated", []) + aging.get("overdue", []))[:8]) or "<li>当前没有已到期或升级项目。</li>"
    judgment_lifecycle_markup = (
        "".join(render_lifecycle_item(entry) for entry in judgment_lifecycle_focus[:8])
        or "<li>当前没有 judgment lifecycle 焦点。</li>"
    )
    judgment_action_markup = (
        "".join(render_review_action_item(action) for action in judgment_review_actions[:8])
        or "<li>当前没有 judgment review action。</li>"
    )
    apply_action_markup = "".join(render_action_item(action) for action in apply_ready_actions[:8]) or "<li>当前没有可直接 apply 的低风险动作。</li>"
    rewrite_markup = "".join(render_rewrite_item(proposal) for proposal in apply_ready_rewrites[:8]) or "<li>当前没有可直接 apply 的 rewrite proposal。</li>"
    proposal_markup = "".join(render_proposal_item(proposal) for proposal in execution_proposals[:8]) or "<li>当前没有 execution proposal。</li>"
    output_markup = "".join(render_output_item(artifact) for artifact in recent_outputs[:10]) or "<li>当前还没有 recent outputs。</li>"
    reviewed_markup = "".join(render_page_item(page) for page in recent_reviewed) or "<li>当前还没有最近已审项目。</li>"
    focus_markup = "".join(f"<li>{html.escape(item)}</li>" for item in protocol_focus + nightly_focus) or "<li>当前协议没有额外焦点。</li>"
    lifecycle_backlog_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("concept_backlog", [])[:10])
        or "<li>当前没有 lifecycle concept backlog。</li>"
    )
    retired_concept_markup = (
        "".join(render_lifecycle_item(entry) for entry in lifecycle_summary.get("retired_concepts", [])[:10])
        or "<li>当前没有 retired concept。</li>"
    )
    pack_markup = "".join(
        f"<li><strong><a href=\"../../{html.escape(row['path'])}\">{html.escape(row['title'])}</a></strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['meta'] or 'n/a')}</span></li>"
        for row in pack_rows[:10]
    ) or "<li>当前协议还没有 review pack / decision memo / SOP draft。</li>"
    receipt_markup = "".join(
        f"<li><strong>{html.escape(row['title'])}</strong>"
        f" <span class=\"item-meta\">{html.escape(row['kind'])} / {html.escape(row['action_id'])}</span>"
        f"<div><code>{html.escape(row['receipt_path'] or '.aiwiki/state/execution-receipts.jsonl')}</code></div>"
        f"<div class=\"item-meta\">{html.escape(row['applied_at'] or 'unknown')}</div></li>"
        for row in receipt_rows[:10]
    ) or "<li>当前协议还没有 execution receipt。</li>"
    quick_command_markup = "".join(
        f"<li><code>{html.escape(command)}</code></li>" for command in quick_commands
    ) or "<li>当前没有额外快速命令。</li>"
    scorecard_markup = (
        "\n".join(
            [
                f'<p><strong><a href="../../{html.escape(str(scorecard.get("path") or ""))}">{html.escape(str(scorecard.get("title") or "Pilot Scorecard"))}</a></strong></p>',
                f'<p class="item-meta">stage {html.escape(str(scorecard.get("stage") or "seed"))} · {html.escape(str(scorecard.get("summary") or ""))}</p>',
                '<ul>'
                + "".join(
                    f"<li>{html.escape(line.lstrip('- ').strip())}</li>"
                    for line in compact_section_lines(
                        str(scorecard.get("content") or ""),
                        "Next Moves",
                        fallback="- 当前没有额外 next moves。",
                        limit=4,
                    )
                )
                + "</ul>",
            ]
        )
        if scorecard
        else "<p>当前协议还没有 pilot scorecard。</p>"
    )

    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '  <meta charset="utf-8" />',
            '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
            "  <title>Furnace Center</title>",
            "  <style>",
            "    :root { color-scheme: light; --bg: #f8fafc; --ink: #0f172a; --muted: #475569; --panel: rgba(255,255,255,0.94); --line: #cbd5e1; }",
            "    body { margin: 0; padding: 24px; background: radial-gradient(circle at top right, #dbeafe 0%, #f8fafc 40%, #fefce8 100%); color: var(--ink); font: 14px/1.6 'Segoe UI', 'PingFang SC', sans-serif; }",
            "    main { max-width: 1180px; margin: 0 auto; }",
            "    h1, h2 { margin: 0 0 12px; }",
            "    p { margin: 0 0 12px; color: var(--muted); }",
            "    .panel, .card { background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(15,23,42,0.06); }",
            "    .panel { padding: 18px; }",
            "    .hero { margin-bottom: 18px; }",
            "    .meta, .grid { display: grid; gap: 16px; }",
            "    .meta { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); margin-top: 18px; }",
            "    .grid { grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }",
            "    .card { padding: 14px 16px; }",
            "    .metric { font-size: 24px; font-weight: 800; color: #1d4ed8; }",
            "    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }",
            "    ul { margin: 0; padding-left: 18px; }",
            "    li { margin: 6px 0; }",
            "    a { color: #1d4ed8; text-decoration: none; }",
            "    a:hover { text-decoration: underline; }",
            "    .item-meta { color: var(--muted); font-size: 12px; }",
            "    code { background: #eff6ff; padding: 1px 6px; border-radius: 6px; }",
            "    .quick-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }",
            "    .quick-links a { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; padding: 6px 12px; background: #ffffff; }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            '  <section class="panel hero">',
            "    <h1>Furnace Center</h1>",
            f"    <p>编译时间：<code>{html.escape(compiled_at)}</code>。当前协议：<code>{html.escape(active_protocol)}</code> ({html.escape(protocol_title(active_protocol))})。这是炼丹炉的统一入口：把 review、graph、execution 和 recent outputs 收到一个地方。</p>",
            '    <div class="quick-links">',
            '      <a href="../../wiki/indexes/furnace-center.md">Markdown 面板</a>',
            '      <a href="../../wiki/indexes/review-center.md">审阅中心</a>',
            '      <a href="../../wiki/indexes/execution-center.md">执行中心</a>',
            '      <a href="../../wiki/indexes/execution-audit.md">执行审计</a>',
            '      <a href="../../wiki/indexes/agent-workbench.md">Agent Workbench</a>',
            '      <a href="../../wiki/indexes/cognitive-history.md">认知历史</a>',
            '      <a href="../../wiki/indexes/output-packs.md">输出 Packs</a>',
            '      <a href="../../wiki/indexes/domain-pilots.md">领域 Pilots</a>',
            '      <a href="../../wiki/indexes/judgment-assets.md">判断资产</a>',
            '      <a href="../../wiki/indexes/graph-view.md">图谱视图</a>',
            '      <a href="../../wiki/indexes/repair-backlog.md">修复待办</a>',
            '      <a href="../../wiki/indexes/protocols.md">协议总览</a>',
            '      <a href="../../output/review/review-center.html">审阅 HTML</a>',
            '      <a href="../../output/graph/machine-memory.html">图谱 HTML</a>',
            '      <a href="../../output/control/execution-center.html">执行 HTML</a>',
            '      <a href="../../output/control/execution-audit.html">审计 HTML</a>',
            "    </div>",
            '    <div class="meta">',
            *[
                f'      <div class="card"><div class="metric">{html.escape(value)}</div><div class="metric-label">{html.escape(label)}</div></div>'
                for label, value in summary_cards
            ],
            "    </div>",
            "  </section>",
            '  <section class="grid">',
            f'    <div class="panel"><h2>待审 / 已到期</h2><ul>{pending_markup}{aging_markup}</ul></div>',
            f'    <div class="panel"><h2>Judgment Lifecycle</h2><ul>{judgment_lifecycle_markup}</ul></div>',
            f'    <div class="panel"><h2>Judgment Review Actions</h2><ul>{judgment_action_markup}</ul></div>',
            '    <div class="panel"><h2>生命周期治理</h2>'
            f'<p class="item-meta">review {html.escape(str(lifecycle_summary.get("counts", {}).get("review_concepts", 0)))}'
            f' · revisit {html.escape(str(lifecycle_summary.get("counts", {}).get("revisit_concepts", 0)))}'
            f' · active {html.escape(str(lifecycle_summary.get("counts", {}).get("active_concepts", 0)))}</p>'
            f"<ul>{lifecycle_backlog_markup}</ul></div>",
            f'    <div class="panel"><h2>已退役概念</h2><ul>{retired_concept_markup}</ul></div>',
            f'    <div class="panel"><h2>Safe Apply</h2><ul>{apply_action_markup}</ul></div>',
            f'    <div class="panel"><h2>Apply-Ready Rewrites</h2><ul>{rewrite_markup}</ul></div>',
            f'    <div class="panel"><h2>Execution Proposals</h2><ul>{proposal_markup}</ul></div>',
            f'    <div class="panel"><h2>最近输出</h2><ul>{output_markup}</ul></div>',
            f'    <div class="panel"><h2>协议焦点</h2><ul>{focus_markup}</ul></div>',
            f'    <div class="panel"><h2>最近已审 / 已沉淀</h2><ul>{reviewed_markup}</ul></div>',
            f'    <div class="panel"><h2>当前协议 Pilot</h2>{scorecard_markup}</div>',
            f'    <div class="panel"><h2>最新输出 Packs</h2><ul>{pack_markup}</ul></div>',
            f'    <div class="panel"><h2>最近执行回执</h2><ul>{receipt_markup}</ul></div>',
            f'    <div class="panel"><h2>快速命令</h2><ul>{quick_command_markup}</ul></div>',
            '    <div class="panel"><h2>系统状态</h2><ul>'
            f'<li>graph components <code>{html.escape(str(health.get("component_count", 0)))}</code></li>'
            f'<li>bridge concepts <code>{html.escape(str(len(health.get("bridge_concept_slugs", []))))}</code></li>'
            f'<li>conflict signals <code>{html.escape(str(concept_quality.get("counts", {}).get("conflict_signals", 0)))}</code></li>'
            f'<li>gap signals <code>{html.escape(str(concept_quality.get("counts", {}).get("gap_signals", 0)))}</code></li>'
            f'<li>rewrite candidates <code>{html.escape(str(concept_quality.get("counts", {}).get("rewrite_candidates", 0)))}</code></li>'
            f'<li>ready batches <code>{html.escape(str(plan.get("counts", {}).get("batches", 0)))}</code></li>'
            "</ul></div>",
            "  </section>",
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def render_compile_status(
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    decisions: list[dict[str, str]],
    judgments: list[dict[str, str]],
    protocol_state: dict[str, Any],
    compiled_at: str,
    *,
    compile_state: dict[str, Any] | None = None,
) -> str:
    queue = review_queue(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    aging = collect_aging_signals(decisions, judgments, active_protocol=protocol_state["active_protocol"])
    compile_state = compile_state or default_compile_state()
    phase_summary = [
        phase
        for phase in compile_state.get("phase_summary", [])
        if isinstance(phase, dict) and str(phase.get("name") or "")
    ]
    dirty_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_source_ids", [])
        if str(entry_id)
    ]
    clean_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_concept_source_ids", [])
        if str(entry_id)
    ]
    clean_concept_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_concept_source_ids", [])
        if str(entry_id)
    ]
    dirty_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_concept_slugs", [])
        if str(slug)
    ]
    clean_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_concept_slugs", [])
        if str(slug)
    ]
    dirty_machine_memory_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_machine_memory_source_ids", [])
        if str(entry_id)
    ]
    clean_machine_memory_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_machine_memory_source_ids", [])
        if str(entry_id)
    ]
    dirty_machine_memory_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_machine_memory_concept_slugs", [])
        if str(slug)
    ]
    clean_machine_memory_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_machine_memory_concept_slugs", [])
        if str(slug)
    ]
    machine_memory_core_reused = bool(compile_state.get("machine_memory_core_reused", False))
    dirty_ranking_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("dirty_ranking_source_ids", [])
        if str(entry_id)
    ]
    clean_ranking_source_ids = [
        str(entry_id)
        for entry_id in compile_state.get("clean_ranking_source_ids", [])
        if str(entry_id)
    ]
    dirty_ranking_concept_slugs = [
        str(slug)
        for slug in compile_state.get("dirty_ranking_concept_slugs", [])
        if str(slug)
    ]
    clean_ranking_concept_slugs = [
        str(slug)
        for slug in compile_state.get("clean_ranking_concept_slugs", [])
        if str(slug)
    ]
    dirty_output_pack_groups = [
        str(group)
        for group in compile_state.get("dirty_output_pack_groups", [])
        if str(group)
    ]
    clean_output_pack_groups = [
        str(group)
        for group in compile_state.get("clean_output_pack_groups", [])
        if str(group)
    ]
    dirty_domain_pilot_protocols = [
        str(protocol)
        for protocol in compile_state.get("dirty_domain_pilot_protocols", [])
        if str(protocol)
    ]
    clean_domain_pilot_protocols = [
        str(protocol)
        for protocol in compile_state.get("clean_domain_pilot_protocols", [])
        if str(protocol)
    ]
    dirty_index_artifacts = [
        str(path)
        for path in compile_state.get("dirty_index_artifacts", [])
        if str(path)
    ]
    clean_index_artifacts = [
        str(path)
        for path in compile_state.get("clean_index_artifacts", [])
        if str(path)
    ]
    dirty_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("dirty_maintenance_artifacts", [])
        if str(path)
    ]
    clean_maintenance_artifacts = [
        str(path)
        for path in compile_state.get("clean_maintenance_artifacts", [])
        if str(path)
    ]
    entry_by_id = {
        str(entry.get("id") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("id") or "")
    }
    concept_by_slug = {
        str(record.get("slug") or ""): record
        for record in concepts
        if isinstance(record, dict) and str(record.get("slug") or "")
    }
    detail_labels = {
        "manifest_entries": "entries",
        "changed_entries": "changed",
        "added_entries": "added",
        "updated_entries": "updated",
        "removed_entries": "removed",
        "source_pages": "sources",
        "dirty_sources": "dirty",
        "clean_sources": "clean",
        "updated_pages": "updated_pages",
        "skipped_pages": "skipped_pages",
        "concept_sources": "concept_sources",
        "dirty_concept_sources": "dirty_concept_sources",
        "clean_concept_sources": "clean_concept_sources",
        "concept_pages": "concepts",
        "dirty_concepts": "dirty_concepts",
        "clean_concepts": "clean_concepts",
        "machine_memory_sources": "machine_memory_sources",
        "dirty_machine_memory_sources": "dirty_machine_memory_sources",
        "clean_machine_memory_sources": "clean_machine_memory_sources",
        "machine_memory_concepts": "machine_memory_concepts",
        "dirty_machine_memory_concepts": "dirty_machine_memory_concepts",
        "clean_machine_memory_concepts": "clean_machine_memory_concepts",
        "reused_core": "reused_core",
        "ranking_sources": "ranking_sources",
        "dirty_ranking_sources": "dirty_ranking_sources",
        "clean_ranking_sources": "clean_ranking_sources",
        "ranking_concepts": "ranking_concepts",
        "dirty_ranking_concepts": "dirty_ranking_concepts",
        "clean_ranking_concepts": "clean_ranking_concepts",
        "pack_groups": "pack_groups",
        "dirty_pack_groups": "dirty_pack_groups",
        "clean_pack_groups": "clean_pack_groups",
        "review_packs": "review_packs",
        "decision_memos": "decision_memos",
        "sop_drafts": "sop_drafts",
        "pilot_protocols": "pilot_protocols",
        "dirty_protocols": "dirty_protocols",
        "clean_protocols": "clean_protocols",
        "tracked_artifacts": "tracked_artifacts",
        "dirty_artifacts": "dirty_artifacts",
        "clean_artifacts": "clean_artifacts",
        "updated_artifacts": "updated_artifacts",
        "skipped_artifacts": "skipped_artifacts",
        "removed_generated_pages": "removed_generated_pages",
        "material_state_entries": "material_state_entries",
        "archive_candidates": "archive_candidates",
        "active_corpora": "active_corpora",
        "knowledge_lifecycle_entries": "knowledge_lifecycle_entries",
    }
    lines = [
        "# 编译状态",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源页：`{len(entries)}`",
        f"- 概念页：`{len(concepts)}`",
        f"- 决策页：`{len(decisions)}`",
        f"- 判断页：`{len(judgments)}`",
        f"- 当前 active protocol：`{protocol_state['active_protocol']}` ({protocol_title(protocol_state['active_protocol'])})",
        f"- 待审项目：`{len(queue['pending_decisions']) + len(queue['pending_judgments'])}`",
        f"- 已到期复审：`{len(aging['overdue'])}`",
        f"- 需要升级：`{len(aging['escalated'])}`",
        f"- 证据漂移：`{sum(1 for page in decisions + judgments if page.get('citation_drift') == 'true')}`",
        "- Compile state：`.aiwiki/state/compile-state.json`",
        "- Concept build state：`.aiwiki/state/concept-build-state.json`",
        "- Machine memory build state：`.aiwiki/state/machine-memory-build-state.json`",
        "- Ranking build state：`.aiwiki/state/ranking-build-state.json`",
        "- Output pack build state：`.aiwiki/state/output-pack-build-state.json`",
        "- Domain pilot build state：`.aiwiki/state/domain-pilot-build-state.json`",
        f"- Dirty source：`{len(dirty_source_ids)}`",
        f"- Clean source：`{len(clean_source_ids)}`",
        f"- Dirty concept source：`{len(dirty_concept_source_ids)}`",
        f"- Clean concept source：`{len(clean_concept_source_ids)}`",
        f"- Dirty concept：`{len(dirty_concept_slugs)}`",
        f"- Clean concept：`{len(clean_concept_slugs)}`",
        f"- Dirty machine-memory source：`{len(dirty_machine_memory_source_ids)}`",
        f"- Clean machine-memory source：`{len(clean_machine_memory_source_ids)}`",
        f"- Dirty machine-memory concept：`{len(dirty_machine_memory_concept_slugs)}`",
        f"- Clean machine-memory concept：`{len(clean_machine_memory_concept_slugs)}`",
        f"- Machine-memory core reused：`{machine_memory_core_reused}`",
        f"- Dirty ranking source：`{len(dirty_ranking_source_ids)}`",
        f"- Clean ranking source：`{len(clean_ranking_source_ids)}`",
        f"- Dirty ranking concept：`{len(dirty_ranking_concept_slugs)}`",
        f"- Clean ranking concept：`{len(clean_ranking_concept_slugs)}`",
        f"- Dirty output pack group：`{len(dirty_output_pack_groups)}`",
        f"- Clean output pack group：`{len(clean_output_pack_groups)}`",
        f"- Dirty domain pilot protocol：`{len(dirty_domain_pilot_protocols)}`",
        f"- Clean domain pilot protocol：`{len(clean_domain_pilot_protocols)}`",
        f"- Dirty index artifact：`{len(dirty_index_artifacts)}`",
        f"- Clean index artifact：`{len(clean_index_artifacts)}`",
        f"- Dirty maintenance artifact：`{len(dirty_maintenance_artifacts)}`",
        f"- Clean maintenance artifact：`{len(clean_maintenance_artifacts)}`",
        "- 总索引位于 `index.md`。",
        "- 运行时规则位于 `schema/`。",
        "- 协议规则位于 `schema/protocols/`。",
        "- 协议总览位于 `protocols.md`。",
        "- 炉心面板位于 `furnace-center.md`。",
        "- 执行中心位于 `execution-center.md`。",
        "- 输出 Pack 总览位于 `output-packs.md`。",
        "- 领域 Pilot 总览位于 `domain-pilots.md`。",
        "- 操作日志位于 `log.md`。",
        "- Agent Workbench 位于 `agent-workbench.md`。",
        "- 决策索引位于 `decisions.md`。",
        "- 判断索引位于 `judgments.md`。",
        "- 判断资产盘点位于 `judgment-assets.md`。",
        "- 认知历史位于 `cognitive-history.md`。",
        "- 审阅队列位于 `review-queue.md`。",
        "- 审阅中心位于 `review-center.md`。",
        "- aging 报告位于 `aging-report.md`。",
        "- 机器记忆摘要位于 `machine-memory.md`。",
        "- 图谱视图位于 `graph-view.md`。",
        "- 机器记忆拓扑位于 `machine-memory-topology.md`。",
        "- 机器记忆动作队列位于 `machine-memory-actions.md`。",
        "- 机器记忆修复计划位于 `machine-memory-repair-plan.md`。",
        "- Rewrite 提案队列位于 `rewrite-proposals.md`。",
        "- 图谱健康页位于 `graph-health.md`。",
        "- 漂移报告位于 `drift-report.md`。",
        "- 修复待办位于 `repair-backlog.md`。",
        "- derived、decision、judgment 页面通过 `aiwiki file-back` 显式回流。",
        "- lint 结果输出在 `output/lint/`。",
    ]
    lines.extend(["", "## Compile Phases"])
    if not phase_summary:
        lines.append("- 当前还没有 compile phase summary。")
    else:
        for phase in phase_summary:
            details = phase.get("details", {})
            detail_chunks = []
            if isinstance(details, dict):
                for key, value in details.items():
                    if key not in detail_labels:
                        continue
                    detail_chunks.append(f"{detail_labels[key]}={value}")
            label = str(phase.get("label") or phase.get("name") or "")
            mode = str(phase.get("mode") or "full")
            status = str(phase.get("status") or "completed")
            detail_suffix = f" | {', '.join(detail_chunks)}" if detail_chunks else ""
            lines.append(f"- `{phase['name']}` `{label}` [{mode}/{status}]{detail_suffix}")
    lines.extend(["", "## Dirty Sources"])
    if not dirty_source_ids:
        lines.append("- 当前没有 dirty source page。")
    else:
        for entry_id in dirty_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_source_ids) > 8:
            lines.append(f"- 其余 dirty source：`{len(dirty_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concept Sources"])
    if not dirty_concept_source_ids:
        lines.append("- 当前没有 dirty concept source。")
    else:
        for entry_id in dirty_concept_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_concept_source_ids) > 8:
            lines.append(f"- 其余 dirty concept source：`{len(dirty_concept_source_ids) - 8}`")
    lines.extend(["", "## Dirty Machine Memory Sources"])
    if not dirty_machine_memory_source_ids:
        lines.append("- 当前没有 dirty machine-memory source input。")
    else:
        for entry_id in dirty_machine_memory_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_machine_memory_source_ids) > 8:
            lines.append(f"- 其余 dirty machine-memory source：`{len(dirty_machine_memory_source_ids) - 8}`")
    lines.extend(["", "## Dirty Concepts"])
    if not dirty_concept_slugs:
        lines.append("- 当前没有 dirty concept page。")
    else:
        for slug in dirty_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_concept_slugs) > 8:
            lines.append(f"- 其余 dirty concept：`{len(dirty_concept_slugs) - 8}`")
    lines.extend(["", "## Dirty Machine Memory Concepts"])
    if not dirty_machine_memory_concept_slugs:
        lines.append("- 当前没有 dirty machine-memory concept input。")
    else:
        for slug in dirty_machine_memory_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_machine_memory_concept_slugs) > 8:
            lines.append(
                f"- 其余 dirty machine-memory concept：`{len(dirty_machine_memory_concept_slugs) - 8}`"
            )
    lines.extend(["", "## Dirty Ranking Sources"])
    if not dirty_ranking_source_ids:
        lines.append("- 当前没有 dirty ranking source record。")
    else:
        for entry_id in dirty_ranking_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(dirty_ranking_source_ids) > 8:
            lines.append(f"- 其余 dirty ranking source：`{len(dirty_ranking_source_ids) - 8}`")
    lines.extend(["", "## Clean Ranking Sources"])
    if not clean_ranking_source_ids:
        lines.append("- 当前没有 clean ranking source record。")
    else:
        for entry_id in clean_ranking_source_ids[:8]:
            entry = entry_by_id.get(entry_id, {})
            title = str(entry.get("title") or entry_id)
            lines.append(f"- [{title}](../sources/{entry_id}.md)")
        if len(clean_ranking_source_ids) > 8:
            lines.append(f"- 其余 clean ranking source：`{len(clean_ranking_source_ids) - 8}`")
    lines.extend(["", "## Dirty Ranking Concepts"])
    if not dirty_ranking_concept_slugs:
        lines.append("- 当前没有 dirty ranking concept record。")
    else:
        for slug in dirty_ranking_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(dirty_ranking_concept_slugs) > 8:
            lines.append(f"- 其余 dirty ranking concept：`{len(dirty_ranking_concept_slugs) - 8}`")
    lines.extend(["", "## Clean Ranking Concepts"])
    if not clean_ranking_concept_slugs:
        lines.append("- 当前没有 clean ranking concept record。")
    else:
        for slug in clean_ranking_concept_slugs[:8]:
            record = concept_by_slug.get(slug, {})
            title = str(record.get("title") or slug)
            lines.append(f"- [{title}](../concepts/{slug}.md)")
        if len(clean_ranking_concept_slugs) > 8:
            lines.append(f"- 其余 clean ranking concept：`{len(clean_ranking_concept_slugs) - 8}`")
    lines.extend(["", "## Dirty Output Pack Groups"])
    if not dirty_output_pack_groups:
        lines.append("- 当前没有 dirty output pack group。")
    else:
        for group in dirty_output_pack_groups:
            lines.append(f"- `{group}`")
    lines.extend(["", "## Clean Output Pack Groups"])
    if not clean_output_pack_groups:
        lines.append("- 当前没有 clean output pack group。")
    else:
        for group in clean_output_pack_groups:
            lines.append(f"- `{group}`")
    lines.extend(["", "## Dirty Domain Pilot Protocols"])
    if not dirty_domain_pilot_protocols:
        lines.append("- 当前没有 dirty domain pilot protocol。")
    else:
        for protocol in dirty_domain_pilot_protocols:
            lines.append(f"- `{protocol}`")
    lines.extend(["", "## Clean Domain Pilot Protocols"])
    if not clean_domain_pilot_protocols:
        lines.append("- 当前没有 clean domain pilot protocol。")
    else:
        for protocol in clean_domain_pilot_protocols:
            lines.append(f"- `{protocol}`")
    lines.extend(["", "## Dirty Index Artifacts"])
    if not dirty_index_artifacts:
        lines.append("- 当前没有 dirty index artifact。")
    else:
        for relative in dirty_index_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_index_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_index_artifacts) - 12}`")
    lines.extend(["", "## Dirty Maintenance Artifacts"])
    if not dirty_maintenance_artifacts:
        lines.append("- 当前没有 dirty maintenance artifact。")
    else:
        for relative in dirty_maintenance_artifacts[:12]:
            lines.append(f"- `{relative}`")
        if len(dirty_maintenance_artifacts) > 12:
            lines.append(f"- 其余 dirty artifact：`{len(dirty_maintenance_artifacts) - 12}`")
    return "\n".join(lines) + "\n"


__all__ = [
    "render_cognitive_history",
    "render_compile_status",
    "render_execution_audit",
    "render_execution_audit_html",
    "render_execution_center",
    "render_execution_center_html",
    "render_furnace_center",
    "render_furnace_center_html",
    "render_judgment_assets",
    "render_machine_memory_graph_html",
    "render_review_center_html",
]
