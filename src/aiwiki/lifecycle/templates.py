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


def curated_asset_section_overrides(*, supporting_body: str, revisit_after: str, escalate_after: str) -> dict[str, list[str]]:
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
    risks = _section_lines(supporting_body, "risks", fallback=[])
    signals = _section_lines(supporting_body, "signals", fallback=[])
    conclusion = _section_lines(supporting_body, "conclusion", fallback=[])
    evidence = _section_lines(supporting_body, "evidence", fallback=[])
    hints: dict[str, Any] = {}
    if kind in {"decision", "judgment"}:
        if risks:
            hints["counter_evidence"] = [re.sub(r"^-+\s*", "", item).strip() for item in risks if item.strip()]
            hints["invalidation_rule"] = _first_plain_line(risks)
        if signals:
            hints["next_signals"] = [re.sub(r"^-+\s*", "", item).strip() for item in signals if item.strip()]
    if protocol == "investing":
        if conclusion:
            hints["thesis"] = _first_plain_line(conclusion)
        if evidence:
            hints["catalyst"] = [re.sub(r"^-+\s*", "", item).strip() for item in evidence if item.strip()]
        if risks:
            hints["risk"] = [re.sub(r"^-+\s*", "", item).strip() for item in risks if item.strip()]
            hints["invalidation_threshold"] = _first_plain_line(risks)
    if protocol == "research" and conclusion:
        hints["hypothesis"] = _first_plain_line(conclusion)
    if protocol == "product" and conclusion:
        hints["user_value_claim"] = _first_plain_line(conclusion)
    if protocol == "ops" and risks:
        hints["blast_radius"] = _first_plain_line(risks)
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
    risks = _section_lines(supporting, "risks", fallback=["- No explicit counter evidence was found in the filed artifact."])
    signals = _section_lines(
        supporting,
        "signals",
        fallback=[f"- Revisit after `{revisit_after or 'none'}` or when cited evidence changes."],
    )

    repaired = body
    if kind == "judgment":
        if protocol == "investing":
            replacements = {
                "Investment Judgment": conclusion,
                "Drivers And Catalysts": evidence,
                "Risks And Invalidation": risks,
                "Confidence And Watchlist": signals,
            }
        elif protocol == "research":
            replacements = {"Research Judgment": conclusion, "Supporting Evidence": evidence, "Counter Evidence": risks, "Open Questions": signals}
        elif protocol == "product":
            replacements = {"Product Judgment": conclusion, "User Signal And Evidence": evidence, "Counter Signals": risks, "Confidence And Next Validation": signals}
        elif protocol == "ops":
            replacements = {"Ops Judgment": conclusion, "Incident Evidence": evidence, "Counter Evidence": risks, "Confidence And Follow-up": signals}
        else:
            replacements = {"Judgment": conclusion, "Signals": evidence, "Counterevidence": risks, "Confidence And Follow-up": signals}
    elif kind == "decision":
        replacements = {"Decision": conclusion, "Evidence": evidence, "Risks And Revisit": risks + signals}
        if protocol == "investing":
            replacements = {
                "Position Decision": conclusion,
                "Thesis": evidence,
                "Bear Case And Invalidation": risks,
                "Catalysts And Revisit": signals,
            }
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
        if protocol == "investing":
            asset_overrides = curated_asset_section_overrides(
                supporting_body=supporting_body,
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            )
            decision_lines = _section_lines(
                supporting_body,
                "conclusion",
                fallback=[f"- Filed from `{artifact_ref}`; review before approving any action."],
            )
            evidence_lines = _section_lines(
                supporting_body,
                "evidence",
                fallback=[f"- Evidence is preserved in the supporting artifact `{artifact_ref}`."],
            )
            risk_lines = _section_lines(
                supporting_body,
                "risks",
                fallback=["- No explicit counter-thesis was found in the filed artifact."],
            )
            signal_lines = _section_lines(
                supporting_body,
                "signals",
                fallback=[f"- Revisit after `{revisit_after or 'none'}` or when cited evidence changes."],
            )
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Position Decision",
                *decision_lines,
                "",
                "## Scope And Sizing",
                f"- Scope is the filed artifact `{artifact_ref}` until a reviewer narrows or expands it.",
                "",
                "## Thesis",
                *evidence_lines,
                "",
                "## Evidence",
                *evidence_lines,
                "",
                "## Bear Case And Invalidation",
                *risk_lines,
                "",
                "## Catalysts And Revisit",
                *signal_lines,
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                    section_overrides=asset_overrides,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the action is approved, resized, exited, or invalidated.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "research":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Architecture Decision",
                "- State the action: adopt, reject, defer, migrate, or rollback.",
                "",
                "## Affected Surface",
                "- Record the systems, components, teams, or experiments affected.",
                "",
                "## Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "",
                "## Validation Plan",
                "- Define the benchmark, test, or rollout signal that would validate this decision.",
                "",
                "## Rollback And Risks",
                "- Record regression risks, rollback path, and explicit failure conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the rollout result, benchmark, or regression signal changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "product":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Product Decision",
                "- State the action: prioritize, launch, roll out, deprecate, or pause.",
                "",
                "## User Problem And Bet",
                "- Record the target user problem, the product bet, and the expected behavior change.",
                "",
                "## Metric And Validation",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the primary metric, rollout checkpoint, or validation signal.",
                "",
                "## Launch Risks And Rollback",
                "- Record launch blockers, segment risk, and rollback/containment conditions.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when launch readiness, metric movement, or the product bet changes.",
                "",
                "## Review Notes",
                "- No review has been recorded yet.",
                *render_review_history_section(),
                "",
                "## Supporting Artifact",
                supporting_body,
            ]
        if protocol == "ops":
            return [
                f"# {title}",
                "",
                *origin_block,
                "## Incident Decision",
                "- State the action: mitigate, roll back, fail over, isolate, escalate, or follow up.",
                "",
                "## Incident Scope",
                "- Record the impacted service, blast radius, owner, and current operational state.",
                "",
                "## Mitigation Evidence",
                f"- Review `{artifact_ref}` and cite `wiki/sources/*.md` or `raw/` evidence explicitly.",
                "- Name the signal that shows mitigation is working.",
                "",
                "## Residual Risk And Follow-up",
                "- Record rollback/failover paths, residual risk, and follow-up owner.",
                f"- Default revisit window: `{revisit_after or 'none'}`",
                f"- Default escalation window: `{escalate_after or 'none'}`",
                *render_curated_asset_sections(
                    revisit_after=revisit_after,
                    escalate_after=escalate_after,
                ),
                "",
                "## Review Status",
                "- Current status: `proposed`",
                "- Review this page when the incident state, blast radius, or owner changes.",
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
    if protocol == "investing":
        asset_overrides = curated_asset_section_overrides(
            supporting_body=supporting_body,
            revisit_after=revisit_after,
            escalate_after=escalate_after,
        )
        judgment_lines = _section_lines(
            supporting_body,
            "conclusion",
            fallback=[f"- Filed from `{artifact_ref}`; review before confirming this judgment."],
        )
        evidence_lines = _section_lines(
            supporting_body,
            "evidence",
            fallback=[f"- Evidence is preserved in the supporting artifact `{artifact_ref}`."],
        )
        risk_lines = _section_lines(
            supporting_body,
            "risks",
            fallback=["- No explicit counter evidence was found in the filed artifact."],
        )
        signal_lines = _section_lines(
            supporting_body,
            "signals",
            fallback=[f"- Revisit after `{revisit_after or 'none'}` or when cited evidence changes."],
        )
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Investment Judgment",
            *judgment_lines,
            "",
            "## Drivers And Catalysts",
            *evidence_lines,
            "",
            "## Risks And Invalidation",
            *risk_lines,
            "",
            "## Confidence And Watchlist",
            *signal_lines,
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
                section_overrides=asset_overrides,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the thesis strengthens, weakens, or is invalidated.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "research":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Research Judgment",
            "- State the hypothesis, expected gain, or architecture judgment here.",
            "",
            "## Supporting Evidence",
            f"- Summarize benchmark, experiment, or source evidence from `{artifact_ref}` and `wiki/sources/*.md`.",
            "",
            "## Counter Evidence",
            "- Record the regression risks, weak signals, or conflicting results.",
            "",
            "## Open Questions",
            "- List what remains uncertain and what experiment should resolve it.",
            "",
            "## Confidence And Next Experiment",
            "- Keep confidence explicit and name the next benchmark or follow-up check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new benchmark, regression, or experiment evidence arrives.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "product":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Product Judgment",
            "- State the insight, product bet, or launch-readiness judgment here.",
            "",
            "## User Signal And Evidence",
            f"- Summarize user signal, metric evidence, or rollout data from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Signals",
            "- Record what user, metric, or launch evidence could invalidate this judgment.",
            "",
            "## Confidence And Next Validation",
            "- Keep confidence explicit and name the next validation checkpoint, release, or metric review.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when the signal strengthens, weakens, or the launch plan changes.",
            "",
            "## Review Notes",
            "- No review has been recorded yet.",
            *render_review_history_section(),
            "",
            "## Supporting Artifact",
            supporting_body,
        ]
    if protocol == "ops":
        return [
            f"# {title}",
            "",
            *origin_block,
            "## Ops Judgment",
            "- State the root-cause, blast-radius, or operational-risk judgment here.",
            "",
            "## Incident Evidence",
            f"- Summarize incident timeline, logs, or runbook evidence from `{artifact_ref}` and supporting sources.",
            "",
            "## Counter Evidence",
            "- Record what would falsify this root-cause or operational-risk judgment.",
            "",
            "## Confidence And Follow-up",
            "- Keep confidence explicit and name the next incident review, runbook update, or mitigation check.",
            f"- Default revisit window: `{revisit_after or 'none'}`",
            f"- Default escalation window: `{escalate_after or 'none'}`",
            *render_curated_asset_sections(
                revisit_after=revisit_after,
                escalate_after=escalate_after,
            ),
            "",
            "## Review Status",
            "- Current status: `tentative`",
            "- Review this page when new incident evidence, residual risk, or follow-up status arrives.",
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
