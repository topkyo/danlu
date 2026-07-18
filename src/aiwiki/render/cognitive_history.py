"""Markdown renderer for the cognitive history index."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..app_lifecycle import (
    display_curated_status,
    display_judgment_lifecycle_state,
    display_rewrite_proposal_status,
    render_knowledge_lifecycle_entry_summary,
    select_knowledge_lifecycle_entries,
    sort_curated_pages,
    sort_knowledge_lifecycle_entries,
)
from ..app_protocol import page_focus_score, protocol_title
from ..content.io import review_history_entries
from ..execution.history import load_runtime_history
from ..lifecycle.knowledge import load_knowledge_lifecycle_state
from ..state.constants import DEFAULT_PROTOCOL
from .views import render_curated_page_summary


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
            added_relations = [relation for relation in event.get("added_relations", []) if isinstance(relation, dict)]
            removed_relations = [
                relation for relation in event.get("removed_relations", []) if isinstance(relation, dict)
            ]
            if added_relations or removed_relations:
                judgment_relation_events.append((occurred_at, added_relations, removed_relations))
            continue
        if event_type == "nightly":
            overdue_pages = [
                str(path) for path in event.get("overdue_pages", []) if isinstance(path, str) and path.strip()
            ]
            escalated_pages = [
                str(path) for path in event.get("escalated_pages", []) if isinstance(path, str) and path.strip()
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
            lines.append(f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}")
    lines.extend(["", "## Judgment 生命周期事件"])
    if not judgment_lifecycle_events:
        lines.append("- 当前还没有 judgment lifecycle 事件。")
    else:
        for occurred_at, title, path, detail in judgment_lifecycle_events[:20]:
            lines.append(f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}")
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
                samples.append(
                    f"+ {relation.get('relation_kind') or 'judgment'}:{relation.get('relation') or 'related'} "
                    f"{source_ref} -> {target_ref}"
                )
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
                samples.append(
                    f"- {relation.get('relation_kind') or 'judgment'}:{relation.get('relation') or 'related'} "
                    f"{source_ref} -> {target_ref}"
                )
            detail = " | ".join(summary_parts) if summary_parts else "no relation delta"
            if samples:
                detail = f"{detail} | {'; '.join(samples)}"
            lines.append(f"- occurred `{occurred_at or 'unknown'}` | {detail}")
    lines.extend(["", "## Nightly 升级事件"])
    if not nightly_escalation_events:
        lines.append("- 当前还没有 nightly escalation 事件。")
    else:
        for occurred_at, overdue_pages, escalated_pages in nightly_escalation_events[:20]:
            overdue_titles = [f"[{page_titles_by_path.get(path, path)}](../../{path})" for path in overdue_pages[:3]]
            escalated_titles = [
                f"[{page_titles_by_path.get(path, path)}](../../{path})" for path in escalated_pages[:3]
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
            lines.append(f"- [{title}](../../{path}) | occurred `{occurred_at or 'unknown'}` | {detail}")
    lines.extend(["", "## 最近认知事件"])
    if not recent_events:
        lines.append("- 当前还没有 review history 事件。")
    else:
        for reviewed_at, title, path, entry in recent_events[:20]:
            lines.append(
                f"- [{title}](../../{path}) | reviewed `{reviewed_at or 'unknown'}` | "
                f"{entry.replace(f'- `{reviewed_at}` | ', '') if reviewed_at else entry}"
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
        lines.append(
            f"- 复查最近 `{min(len(judgment_relation_events), 5)}` 次 judgment relation 变更，确认支持/反证关系仍然有效。"
        )
    if nightly_escalation_events:
        lines.append(f"- 优先处理最近 `{min(len(nightly_escalation_events), 5)}` 次 nightly 升级事件里仍然活跃的页面。")
    if rewrite_events:
        lines.append(
            f"- 检查最近 `{min(len(rewrite_events), 5)}` 个 concept rewrite 事件，确认 verify / revert 闭环已经跑通。"
        )
    if not any(
        (drifted_pages, snapshot_gap_pages, long_history_pages, judgment_relation_events, nightly_escalation_events)
    ):
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
