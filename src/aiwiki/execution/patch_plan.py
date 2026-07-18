"""Patch-plan domain logic (EP-017C step 4a).

Split out of ``aiwiki.content.memory``: patch-role / section / summary / mode
resolution, patch-plan templates and auxiliary path maps, and the
``build_page_patch_plan`` assembler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app_protocol import DEFAULT_PROTOCOL
from ..memory.action_core import action_supports_low_risk_apply, safe_apply_preview
from ..utils.markdown import parse_frontmatter

PATCH_ROLE_LABELS = {
    "source": "来源页",
    "concept": "概念页",
    "index": "索引页",
    "state": "状态文件",
    "output": "输出页",
    "other": "页面",
}


PATCH_PLAN_TEMPLATES: dict[str, dict[str, Any]] = {
    "add-source-concept-link": {
        "summary": "补 source/concept 双向链接，并把新证据吸收到概念页摘要里。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Related Concepts", "Summary", "Citations"),
                "summary": "在来源页补 concept 引用，并保留 raw/source provenance。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary", "Related Concepts"),
                "summary": "把来源页纳入概念页，并更新 grounded synthesis。",
            },
            "state": {
                "mode": "semi-auto-apply",
                "sections": ("source_to_concept",),
                "summary": "通过 manual-link state 注入低风险补链，让 compile 收敛页面链接。",
            },
        },
    },
    "connect-isolated-source": {
        "summary": "把孤立来源接回稳定概念层，并明确为什么要接入。",
        "roles": {
            "source": {
                "mode": "update",
                "sections": ("Summary", "Related Concepts", "Citations"),
                "summary": "从来源页抽出候选概念并补引用。",
            },
            "concept": {
                "mode": "update",
                "sections": ("Related Sources", "Summary"),
                "summary": "优先把来源接到已有稳定概念，而不是盲目新建概念。",
            },
            "index": {
                "mode": "review",
                "sections": ("Concept Coverage", "Open Questions"),
                "summary": "在索引层确认是否还缺概念覆盖或需要新概念。",
            },
        },
    },
    "expand-singleton-concept": {
        "summary": "扩展单节点概念的来源覆盖，并收紧其适用边界。",
        "roles": {
            "concept": {
                "mode": "update",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "补来源覆盖、显式有限证据，并更新相关概念边界。",
            },
            "index": {
                "mode": "review",
                "sections": ("Rewrite Priority", "Open Questions"),
                "summary": "在概念质量和索引层确认是否需要持续重写或补料。",
            },
        },
    },
    "split-overloaded-concept": {
        "summary": "把过载概念拆成更窄的主题，并把来源重新分流。",
        "roles": {
            "concept": {
                "mode": "rewrite",
                "sections": ("Summary", "Related Sources", "Related Concepts"),
                "summary": "缩窄概念边界、保留拆分说明，并给出后续子概念方向。",
            },
            "index": {
                "mode": "review",
                "sections": ("Merge Candidates", "Rewrite Priority"),
                "summary": "在概念质量层复核拆分理由和后续子概念候选。",
            },
        },
    },
    "monitor-bridge-concept": {
        "summary": "确认桥接概念仍有必要，并记录跨簇连接的理由。",
        "roles": {
            "concept": {
                "mode": "review",
                "sections": ("Summary", "Related Concepts", "Related Sources"),
                "summary": "补 bridge maintenance note，明确为什么这个桥接概念还成立。",
            },
            "index": {
                "mode": "review",
                "sections": ("Bridge Concepts", "Repair Signals"),
                "summary": "在图谱健康层确认桥接信号是否稳定，避免误删关键连接。",
            },
        },
    },
    "refresh-citation-snapshots": {
        "summary": "刷新判断页的 citation snapshot metadata，不改正文结论。",
        "roles": {
            "other": {
                "mode": "semi-auto-apply",
                "sections": ("frontmatter", "Citations"),
                "summary": "重建 citation_snapshots，让 review / drift 检测重新收敛。",
            },
        },
    },
}


PATCH_PLAN_AUXILIARY_PATHS: dict[str, tuple[str, ...]] = {
    "connect-isolated-source": ("wiki/indexes/concepts.md",),
    "expand-singleton-concept": ("wiki/indexes/concept-quality.md",),
    "split-overloaded-concept": ("wiki/indexes/concept-quality.md", "wiki/indexes/rewrite-proposals.md"),
    "monitor-bridge-concept": ("wiki/indexes/graph-health.md",),
}


PROTOCOL_PATCH_HINTS: dict[str, tuple[str, ...]] = {
    "general": (),
}


def patch_role_for_path(path: str) -> str:
    if path.startswith("wiki/sources/"):
        return "source"
    if path.startswith("wiki/concepts/"):
        return "concept"
    if path.startswith("wiki/indexes/"):
        return "index"
    if path.startswith(".aiwiki/state/"):
        return "state"
    if path.startswith("output/"):
        return "output"
    return "other"


def patch_sections_for_action(kind: str, role: str) -> tuple[str, ...]:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return tuple(roles[role].get("sections", ()))
    fallback = {
        "source": ("Summary", "Citations"),
        "concept": ("Summary", "Related Sources", "Related Concepts"),
        "index": ("Status", "Open Questions"),
        "state": ("state",),
        "output": ("Summary",),
        "other": ("Summary",),
    }
    return fallback.get(role, ("Summary",))


def patch_summary_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("summary") or "")
    return str(template.get("summary") or "检查相关页面并补充修复说明。")


def patch_mode_for_action(kind: str, role: str) -> str:
    template = PATCH_PLAN_TEMPLATES.get(kind, {})
    roles = template.get("roles", {})
    if role in roles:
        return str(roles[role].get("mode") or "update")
    return "update"


def build_page_patch_plan(
    root: Path, action: dict[str, Any], *, active_protocol: str = DEFAULT_PROTOCOL
) -> list[dict[str, Any]]:
    kind = str(action.get("kind") or "")
    seen_paths: set[str] = set()
    ordered_paths: list[str] = []
    for raw_path in (
        str(action.get("primary_path") or ""),
        str(action.get("secondary_path") or ""),
        *PATCH_PLAN_AUXILIARY_PATHS.get(kind, ()),
    ):
        path = raw_path.strip()
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        ordered_paths.append(path)
    if action_supports_low_risk_apply(action):
        preview = safe_apply_preview(root, action)
        state_path = str(preview.get("state_path") or "") if isinstance(preview, dict) else ""
        if state_path and state_path not in seen_paths:
            seen_paths.add(state_path)
            ordered_paths.append(state_path)

    plan: list[dict[str, Any]] = []
    for path in ordered_paths:
        role = patch_role_for_path(path)
        absolute = root / path
        title = absolute.stem
        if absolute.is_file() and role != "state":
            frontmatter = parse_frontmatter(absolute.read_text(encoding="utf-8", errors="replace"))
            title = str(frontmatter.get("title") or title)
        summary = patch_summary_for_action(kind, role)
        protocol_hints = PROTOCOL_PATCH_HINTS.get(active_protocol, ())
        if protocol_hints and role in {"source", "concept", "index"}:
            summary = f"{summary} {protocol_hints[0]}".strip()
        plan.append(
            {
                "path": path,
                "title": title,
                "role": role,
                "role_label": PATCH_ROLE_LABELS.get(role, role),
                "exists": absolute.is_file(),
                "mode": patch_mode_for_action(kind, role),
                "sections": list(patch_sections_for_action(kind, role)),
                "summary": summary,
                "command_hint": str(action.get("command_hint") or ""),
            }
        )
    return plan
