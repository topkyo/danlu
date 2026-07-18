"""Curated page markdown templates."""

from __future__ import annotations

import re
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
    "Summarize benchmark",
    "Summarize user signal",
    "Summarize incident",
    "Record the main risks",
    "Record the regression risks",
    "Record what user",
    "Record what would falsify",
    "Keep confidence explicit",
    "Pending counter evidence.",
    "Pending invalidation conditions.",
    "Pending next signals.",
    "Default revisit window:",
    "Default escalation window:",
    "review the supporting artifact before confirmation.",
    "review before approving any action.",
    "Evidence is preserved in the supporting artifact",
    "No explicit counter evidence was found in the filed artifact.",
    "No explicit counter-thesis was found in the filed artifact.",
    "No counter evidence was found in the filed artifact; verify this during review.",
    "Revisit after `",
    "Revisit this judgment after `",
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


def curated_structured_value_is_placeholder(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return bool(items) and all(_text_has_instruction_marker(item) for item in items)
    text = str(value).strip()
    return bool(text) and _text_has_instruction_marker(text)


def _replace_section_if_placeholder(markdown: str, heading: str, lines: list[str]) -> str:
    if not _section_is_placeholder(markdown, heading):
        return markdown
    replacement = f"## {heading}\n" + "\n".join(lines).strip() + "\n\n"
    pattern = rf"(?ms)^## {re.escape(heading)}\n.*?(?=^## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, replacement, markdown, count=1)
    return markdown.rstrip() + "\n\n" + replacement.rstrip() + "\n"


def curated_asset_section_overrides(
    *, supporting_body: str, revisit_after: str, escalate_after: str
) -> dict[str, list[str]]:
    risks = _section_lines(
        supporting_body,
        "risks",
        fallback=["- No counter evidence was found in the filed artifact; verify this during review."],
    )
    signals = _section_lines(
        supporting_body,
        "signals",
        fallback=[
            f"- Revisit this judgment after `{revisit_after or 'none'}` or when cited evidence changes.",
            f"- Escalate after `{escalate_after or 'none'}` if the evidence chain breaks.",
        ],
    )
    return {"Counter Evidence": risks, "Invalidation": risks, "Next Signals": signals}


def curated_frontmatter_hints(*, kind: str, protocol: str, supporting_body: str) -> dict[str, Any]:
    _ = protocol
    risks = _section_lines(supporting_body, "risks", fallback=[])
    signals = _section_lines(supporting_body, "signals", fallback=[])
    hints: dict[str, Any] = {}
    if kind in {"decision", "judgment"}:
        if risks:
            hints["counter_evidence"] = [re.sub(r"^-+\s*", "", item).strip() for item in risks if item.strip()]
            hints["invalidation_rule"] = _first_plain_line(risks)
        if signals:
            hints["next_signals"] = [re.sub(r"^-+\s*", "", item).strip() for item in signals if item.strip()]
    return {key: value for key, value in hints.items() if value}


def repair_curated_page_body(
    *,
    kind: str,
    protocol: str,
    body: str,
    artifact_ref: str,
    revisit_after: str,
    escalate_after: str,
) -> str:
    _ = protocol
    if "## Supporting Artifact" in body:
        supporting = body.split("## Supporting Artifact", 1)[1].strip()
    elif "## Filed Content" in body:
        supporting = body.split("## Filed Content", 1)[1].strip()
    else:
        supporting = body
    conclusion = _section_lines(
        supporting,
        "conclusion",
        fallback=[f"- Filed from `{artifact_ref}`; review the supporting artifact before confirmation."],
    )
    evidence = _section_lines(
        supporting,
        "evidence",
        fallback=[f"- Evidence is preserved in the supporting artifact `{artifact_ref}`."],
    )
    risks = _section_lines(
        supporting, "risks", fallback=["- No explicit counter evidence was found in the filed artifact."]
    )
    signals = _section_lines(
        supporting,
        "signals",
        fallback=[f"- Revisit after `{revisit_after or 'none'}` or when cited evidence changes."],
    )

    repaired = body
    if kind == "judgment":
        replacements = {
            "Judgment": conclusion,
            "Signals": evidence,
            "Counterevidence": risks,
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
            supporting_body,
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
        "## Counterevidence",
        "- Record what could make this judgment wrong.",
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
        supporting_body,
    ]
