"""Curated page markdown templates."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..content.io import render_curated_asset_sections, render_review_history_section

_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "conclusion": (
        "结论",
        "Conclusion",
        "Investment Judgment",
        "Position Decision",
        "Research Judgment",
        "Product Judgment",
        "Ops Judgment",
        "Decision",
        "Judgment",
    ),
    "evidence": (
        "关键证据",
        "Evidence",
        "Drivers And Catalysts",
        "Thesis",
        "Supporting Evidence",
        "User Signal And Evidence",
        "Incident Evidence",
    ),
    "risks": (
        "反证与不确定性",
        "Risks And Invalidation",
        "Bear Case And Invalidation",
        "Counter Evidence",
        "Counter Signals",
        "Roll Back And Risks",
        "Rollback And Risks",
        "Risks And Revisit",
    ),
    "actions": ("行动建议", "Action Items", "Recommendations"),
    "signals": (
        "下次观察信号",
        "Next Signals",
        "Confidence And Watchlist",
        "Catalysts And Revisit",
        "Confidence And Next Validation",
        "Confidence And Follow-up",
        "Open Questions",
    ),
}

_INSTRUCTION_MARKERS = (
    "State the thesis",
    "State the judgment",
    "State the hypothesis",
    "State the insight",
    "State the root-cause",
    "Summarize the key",
    "Summarize the signals",
    "Summarize benchmark",
    "Summarize user signal",
    "Summarize incident",
    "Record the main risks",
    "Record the regression risks",
    "Record what user",
    "Record what could",
    "Record what would falsify",
    "Keep confidence explicit",
    "Pending counter evidence.",
    "Pending invalidation conditions.",
    "Pending next signals.",
    "Default revisit window:",
    "Default escalation window:",
    "Filed from `",
    "review the supporting artifact before confirmation.",
    "review before approving any action.",
    "Evidence is preserved in the supporting artifact",
    "No explicit counter evidence was found in the filed artifact.",
    "No explicit counter-thesis was found in the filed artifact.",
    "No counter evidence was found in the filed artifact; verify this during review.",
    "Revisit after `",
    "Revisit this judgment after `",
)

_LIMITED_EVIDENCE_MARKERS = (
    "truncated",
    "截断",
    "limited evidence",
    "uncertainty limit",
    "incomplete evidence",
    "partial evidence",
    "README truncated",
    "证据不足",
    "信息有限",
)


def _text_has_instruction_marker(text: str) -> bool:
    return any(marker in text for marker in _INSTRUCTION_MARKERS)


def _section_text(markdown: str, headings: tuple[str, ...]) -> str:
    for heading in headings:
        match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown)
        if match:
            section = match.group(1).strip()
            if section:
                return section
    return ""


def _section_lines(markdown: str, key: str, *, fallback: list[str], max_lines: int = 6) -> list[str]:
    section = _section_text(markdown, _SECTION_ALIASES[key])
    lines: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```") or line.startswith("#"):
            continue
        if "_LLM:" in line or "机器记忆提示" in line or "查询入口：" in line:
            continue
        if line.startswith(("相关来源", "当前协议")):
            continue
        if not line.startswith(("-", "1.", "2.", "3.", "4.", "5.")):
            line = f"- {line}"
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines or list(fallback)


def _first_plain_line(lines: list[str]) -> str:
    for line in lines:
        value = re.sub(r"^-+\s*", "", line).strip()
        value = re.sub(r"^\d+\.\s*", "", value).strip()
        if value:
            return value
    return ""


def _section_is_placeholder(markdown: str, heading: str) -> bool:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", markdown)
    if not match:
        return True
    lines = [
        line.strip()
        for line in match.group(1).splitlines()
        if line.strip() and not line.strip().startswith("```") and not line.strip().startswith("#")
    ]
    if not lines:
        return True
    return all(_text_has_instruction_marker(line) for line in lines)


def curated_section_is_placeholder(markdown: str, heading: str) -> bool:
    return _section_is_placeholder(markdown, heading)


def _line_has_instruction_marker(line: str) -> bool:
    plain = re.sub(r"^-+\s*", "", line).strip()
    plain = re.sub(r"^\d+\.\s*", "", plain).strip()
    return _text_has_instruction_marker(line) or _text_has_instruction_marker(plain)


def _filter_non_placeholder_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if not _line_has_instruction_marker(line)]


def _free_markdown_prose_lines(markdown: str, *, max_lines: int = 6) -> list[str]:
    """First meaningful paragraph or bullet list from free markdown (no structured headings)."""
    bullet_lines: list[str] = []
    paragraph: list[str] = []
    saw_title = False
    collecting_bullets = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph:
                break
            if collecting_bullets and bullet_lines:
                break
            continue
        if line.startswith("```"):
            continue
        if line.startswith("# ") and not saw_title:
            saw_title = True
            continue
        if line.startswith("## "):
            if paragraph or bullet_lines:
                break
            continue
        if _line_has_instruction_marker(line):
            continue
        if "_LLM:" in line or "机器记忆提示" in line or line.startswith(("相关来源", "当前协议")):
            continue
        if "evidence-graph" in line or "关系图谱" in line:
            continue
        if line.startswith(("-", "*")) or re.match(r"^\d+\.", line):
            if paragraph:
                break
            collecting_bullets = True
            value = re.sub(r"^[-*]\s+", "", line)
            value = re.sub(r"^\d+\.\s*", "", value).strip()
            if value and not _line_has_instruction_marker(value):
                bullet_lines.append(f"- {value}")
                if len(bullet_lines) >= max_lines:
                    break
            continue
        if collecting_bullets and bullet_lines:
            break
        paragraph.append(line)
        if len(paragraph) >= max_lines:
            break

    if bullet_lines:
        return bullet_lines
    if paragraph:
        text = " ".join(paragraph).strip()
        if text and not _text_has_instruction_marker(text):
            return [f"- {text}"]
    return []


def _limited_evidence_lines(supporting: str, *, max_lines: int = 3) -> list[str]:
    lines_out: list[str] = []
    for raw_line in supporting.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if not any(marker in lower or marker in line for marker in _LIMITED_EVIDENCE_MARKERS):
            continue
        if _line_has_instruction_marker(line):
            continue
        if line.startswith("- "):
            lines_out.append(line)
        else:
            lines_out.append(f"- {line}")
        if len(lines_out) >= max_lines:
            break
    return lines_out


def _judgment_conclusion_lines(supporting: str, *, max_lines: int = 6) -> list[str]:
    structured = _filter_non_placeholder_lines(
        _section_lines(supporting, "conclusion", fallback=[], max_lines=max_lines)
    )
    if structured:
        return structured
    return _free_markdown_prose_lines(supporting, max_lines=max_lines)


def _curated_risk_lines(supporting: str, *, max_lines: int = 6) -> list[str]:
    structured = _filter_non_placeholder_lines(_section_lines(supporting, "risks", fallback=[], max_lines=max_lines))
    if structured:
        return structured
    return _limited_evidence_lines(supporting, max_lines=max_lines)


def curated_structured_value_is_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return bool(items) and all(_text_has_instruction_marker(item) for item in items)
    text = str(value).strip()
    return bool(text) and _text_has_instruction_marker(text)


def _replace_section_if_placeholder(markdown: str, heading: str, lines: list[str]) -> str:
    meaningful = _filter_non_placeholder_lines(lines)
    if not meaningful:
        return markdown
    if not _section_is_placeholder(markdown, heading):
        return markdown
    replacement = f"## {heading}\n" + "\n".join(meaningful).strip() + "\n\n"
    pattern = rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, replacement, markdown, count=1)
    return markdown.rstrip() + "\n\n" + replacement.rstrip() + "\n"


_MACHINE_APPENDED_HEADINGS = ("关系图谱锚点",)


def _strip_machine_appended_sections(markdown: str) -> str:
    cleaned = markdown
    for heading in _MACHINE_APPENDED_HEADINGS:
        cleaned = re.sub(rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)", "", cleaned)
    return cleaned.strip()


def supporting_artifact_link_lines(*, artifact_ref: str) -> list[str]:
    return [
        f"- Linked report: `{artifact_ref}`",
        "- Full report content lives at the linked path; review before confirmation.",
    ]


def _extract_supporting_artifact_raw(body: str) -> str:
    if "## Supporting Artifact" in body:
        return body.split("## Supporting Artifact", 1)[1].strip()
    if "## Filed Content" in body:
        return body.split("## Filed Content", 1)[1].strip()
    return ""


def _supporting_section_is_link_only(raw: str) -> bool:
    if not raw.strip():
        return True
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return True
    link_markers = ("Linked report:", "Full report content lives at the linked path")
    return all(any(marker in line for marker in link_markers) for line in lines)


def resolve_curated_supporting_body(
    *,
    root: Path | None = None,
    body: str = "",
    source_files: list[str] | None = None,
    explicit: str | None = None,
) -> str:
    if explicit is not None:
        return explicit
    raw = _extract_supporting_artifact_raw(body)
    if raw and not _supporting_section_is_link_only(raw):
        return raw
    artifact_ref = ""
    if source_files:
        artifact_ref = str(source_files[0]).strip()
    if not artifact_ref and raw:
        for line in raw.splitlines():
            match = re.search(r"`([^`]+\.(?:md|markdown|txt))`", line)
            if match:
                artifact_ref = match.group(1)
                break
    if root is not None and artifact_ref:
        from ..utils.markdown import strip_frontmatter
        from ..utils.security import PathOutsideWorkspaceError, safe_resolve_within

        try:
            candidate = safe_resolve_within(root / artifact_ref, root)
        except (OSError, PathOutsideWorkspaceError, ValueError):
            return raw
        if candidate.is_file():
            resolved = strip_frontmatter(candidate.read_text(encoding="utf-8", errors="replace")).strip()
            return _strip_machine_appended_sections(resolved)
    return raw


def curated_body_structured_fields(
    *,
    root: Path | None,
    content: str,
    frontmatter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ..utils.markdown import strip_frontmatter

    frontmatter = frontmatter or {}
    body = strip_frontmatter(content)
    source_files = [
        str(item) for item in frontmatter.get("source_files", []) if isinstance(item, str) and item.strip()
    ]
    supporting = resolve_curated_supporting_body(root=root, body=body, source_files=source_files or None)
    risks = _curated_risk_lines(supporting)
    signals = _filter_non_placeholder_lines(
        _section_lines(
            supporting,
            "signals",
            fallback=[],
            max_lines=6,
        )
    )
    fields: dict[str, Any] = {}
    if risks:
        fields["counter_evidence"] = [re.sub(r"^-+\s*", "", item).strip() for item in risks if item.strip()]
        fields["invalidation_rule"] = _first_plain_line(risks)
    if signals:
        fields["next_signals"] = [re.sub(r"^-+\s*", "", item).strip() for item in signals if item.strip()]
    return fields


def curated_asset_section_overrides(
    *, supporting_body: str, revisit_after: str, escalate_after: str
) -> dict[str, list[str]]:
    risks = _curated_risk_lines(supporting_body)
    signals = _filter_non_placeholder_lines(
        _section_lines(
            supporting_body,
            "signals",
            fallback=[],
            max_lines=6,
        )
    )
    overrides: dict[str, list[str]] = {}
    if risks:
        overrides["Counter Evidence"] = risks
    if signals:
        overrides["Next Signals"] = signals
    _ = (revisit_after, escalate_after)
    return overrides


def curated_frontmatter_hints(*, kind: str, protocol: str, supporting_body: str) -> dict[str, Any]:
    _ = (kind, protocol, supporting_body)
    return {}


def repair_curated_page_body(
    *,
    kind: str,
    protocol: str,
    body: str,
    artifact_ref: str,
    revisit_after: str,
    escalate_after: str,
    supporting_body: str | None = None,
    root: Path | None = None,
    source_files: list[str] | None = None,
) -> str:
    _ = protocol
    supporting = resolve_curated_supporting_body(
        root=root,
        body=body,
        source_files=source_files,
        explicit=supporting_body,
    )
    if not supporting:
        supporting = body
    conclusion = _judgment_conclusion_lines(supporting)
    evidence = _filter_non_placeholder_lines(
        _section_lines(
            supporting,
            "evidence",
            fallback=[],
            max_lines=6,
        )
    )
    risks = _curated_risk_lines(supporting)
    signals = _filter_non_placeholder_lines(
        _section_lines(
            supporting,
            "signals",
            fallback=[],
            max_lines=6,
        )
    )
    _ = (artifact_ref, revisit_after, escalate_after)

    repaired = body
    if kind == "judgment":
        replacements = {
            "Judgment": conclusion,
            "Signals": evidence,
            "Confidence And Follow-up": signals,
        }
    elif kind == "decision":
        replacements = {"Decision": conclusion, "Evidence": evidence, "Risks And Revisit": risks + signals}
    else:
        replacements = {}
    for heading, lines in replacements.items():
        repaired = _replace_section_if_placeholder(repaired, heading, lines)
    for heading, lines in curated_asset_section_overrides(
        supporting_body=supporting,
        revisit_after=revisit_after,
        escalate_after=escalate_after,
    ).items():
        repaired = _replace_section_if_placeholder(repaired, heading, lines)
    return repaired


def curated_page_template(
    *,
    kind: str,
    protocol: str,
    title: str,
    artifact_ref: str,
    filed_at: str,
    revisit_after: str,
    escalate_after: str,
    supporting_body: str,
) -> list[str]:
    origin_block = [
        "## Origin",
        f"- Filed from: `{artifact_ref}`",
        f"- Filed at: `{filed_at}`",
        f"- Protocol: `{protocol}`",
        "",
    ]
    if kind == "derived":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Filed Content",
            supporting_body,
        ]
    if kind == "decision":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Decision",
            "- State the concrete decision here.",
            "",
            "## Why",
            "- Summarize the rationale and tradeoffs.",
            "",
            "## Evidence",
            f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
            "",
            "## Risks And Revisit",
            "- Record what could invalidate this decision and when to revisit it.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `proposed`",
            "- Review this page when the decision is approved, superseded, or needs revisit.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            *supporting_artifact_link_lines(artifact_ref=artifact_ref),
        ]
    return [
        f"# {title}",
        "",
        *origin_block,
        "## Judgment",
        "- State the judgment call here.",
        "",
        "## Signals",
        f"- Summarize the signals from `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence.",
        "",
        "## Confidence And Follow-up",
        "- Keep confidence explicit and list what to watch next.",
        f"- Default revisit window: `{revisit_after or 'none'}`",
        f"- Default escalation window: `{escalate_after or 'none'}`",
        *render_curated_asset_sections(
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        ),
        "",
        "## Review Status",
        "- Current status: `tentative`",
        "- Review this page when the judgment is confirmed, rejected, or moved to active tracking.",
        "",
        "## Review Notes",
        "- No review has been recorded yet.",
        *render_review_history_section(),
        "",
        "## Supporting Artifact",
        *supporting_artifact_link_lines(artifact_ref=artifact_ref),
    ]
