"""Markdown renderer for the judgment assets index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_protocol import protocol_title
from ..app_state import DEFAULT_PROTOCOL
from ..app_utils import parse_frontmatter
from .views import judgment_asset_summary, render_curated_page_summary


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
