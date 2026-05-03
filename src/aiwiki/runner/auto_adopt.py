"""Nightly auto-adoption of L1 / L2 governance backlog.

Extends the nightly agent loop beyond deterministic light-primitive apply
(compile / lint / nightly) into *semantic-candidate adoption*. The original
boundary kept L1 candidate-only and L2 gate-only; this module changes the
design so that 炼丹炉 can silently auto-adopt safe-category items by default.

Opt-in per level via env vars:
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L1=1`` — auto-adopt L1 semantic candidates
- ``AIWIKI_NIGHTLY_AUTO_ADOPT_L2=1`` — auto-adopt L2 machine-memory actions

Policy (deliberately permissive, aligned with 炼丹炉 philosophy):
  L1 — concept backlog / revisit / source-concept links
  L2 — concept splits (deterministic overloaded-concept proposals)
  Judgment — counter-evidence / judgment review (LLM-powered, nightly path)

Explicitly EXCLUDED from auto-adopt:
  L3 proposals — remain gate-only (prompt / policy changes)
  judgment_review_actions that require reading evidence chains
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..app_shell.controls import shell_execution_controls, shell_review_controls
from ..app_state import load_machine_memory, load_planner_state
from ..execution.lifecycle import review_concepts_batch
from ..execution.machine_memory_actions import review_machine_memory_actions_batch
from ..execution.machine_memory_batch import apply_machine_memory_actions_batch


def _build_controls(root: Path):
    """Load the review and execution control surfaces."""
    from ..app_compile import collect_aging_signals, review_queue
    from ..app_state import (
        DEFAULT_PROTOCOL,
        load_compile_state,
    )

    compile_state = load_compile_state(root)
    memory = load_machine_memory(root)
    planner_state = load_planner_state(root)
    decisions = compile_state.get("decisions", [])
    judgments = compile_state.get("judgments", [])
    active_protocol = str(planner_state.get("active_protocol") or DEFAULT_PROTOCOL)
    queue = review_queue(decisions, judgments, active_protocol=active_protocol)
    aging = collect_aging_signals(decisions, judgments, active_protocol=active_protocol)
    counter_evidence_scan = memory.get("health", {}).get("counter_evidence_scan", {})
    judgment_review_actions = memory.get("health", {}).get("judgment_review_actions", [])
    review_ctrl = shell_review_controls(
        root,
        queue=queue,
        aging=aging,
        active_protocol=active_protocol,
        counter_evidence_scan=counter_evidence_scan if isinstance(counter_evidence_scan, dict) else {},
        review_actions=judgment_review_actions if isinstance(judgment_review_actions, list) else [],
    )
    exec_ctrl = shell_execution_controls(root, memory)
    return review_ctrl, exec_ctrl

_logger = logging.getLogger(__name__)

_L1_CONCEPT_STATUS = "active"
_L1_REVISIT_STATUS = "deferred"
_L1_ACTION_STATUS = "accepted"
_L2_CONCEPT_SPLIT_STATUS = "accepted"


def _env_flag(name: str) -> bool:
    import os

    value = os.environ.get(name, "0")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def auto_adopt_l1(root: Path) -> dict[str, Any]:
    """Auto-adopt L1 semantic candidates.

    Covers: concept backlog, revisit concepts, source-concept link actions.
    Counter-evidence is handled by LLM-powered judgment review, not here.
    """
    results: dict[str, Any] = {"level": "L1", "applied": False, "items": []}
    try:
        review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"control surface unavailable: {exc}"
        return results

    # --- L1a: concept backlog → active ---
    concept_backlog = [
        item.get("slug", "")
        for item in review_ctrl.get("concept_backlog", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["concept_backlog_pending"] = len(concept_backlog)
    if concept_backlog:
        try:
            r = review_concepts_batch(root, concept_backlog, status=_L1_CONCEPT_STATUS, note="nightly L1 auto-adopt: concept backlog → active")
            results["items"].append({"kind": "concept_backlog", "count": r.get("count", 0), "status": _L1_CONCEPT_STATUS})
        except Exception as exc:
            results["items"].append({"kind": "concept_backlog", "error": str(exc)})

    # --- L1b: revisit concepts → deferred ---
    revisit = [
        item.get("slug", "")
        for item in review_ctrl.get("revisit_concepts", [])
        if isinstance(item, dict) and item.get("slug")
    ]
    results["revisit_concepts_pending"] = len(revisit)
    if revisit:
        try:
            r = review_concepts_batch(root, revisit, status=_L1_REVISIT_STATUS, note="nightly L1 auto-adopt: revisit → deferred")
            results["items"].append({"kind": "revisit_concepts", "count": r.get("count", 0), "status": _L1_REVISIT_STATUS})
        except Exception as exc:
            results["items"].append({"kind": "revisit_concepts", "error": str(exc)})

    # --- L1c: source-concept link actions → accepted + apply ---
    link_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "add-source-concept-link"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    link_actions = [aid for aid in link_actions if aid]
    results["source_concept_links_pending"] = len(link_actions)
    if link_actions:
        try:
            r = review_machine_memory_actions_batch(root, link_actions, status=_L1_ACTION_STATUS, note="nightly L1 auto-adopt: source-concept link accepted")
            results["items"].append({"kind": "source_concept_links", "status": _L1_ACTION_STATUS, "count": r.get("count", 0)})
        except Exception as exc:
            results["items"].append({"kind": "source_concept_links", "error": str(exc)})

    # Apply all accepted low-risk actions (covers the links we just accepted)
    apply_ids = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict) and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    apply_ids = [aid for aid in apply_ids if aid]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L1 auto-adopt: apply accepted low-risk", dry_run=False)
            results["items"].append({"kind": "apply_accepted", "count": r.get("applied_count", r.get("count", 0))})
        except Exception as exc:
            results["items"].append({"kind": "apply_accepted", "error": str(exc)})

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


def auto_adopt_l2(root: Path) -> dict[str, Any]:
    """Auto-adopt L2 machine-memory actions (concept splits only).

    Concept splits are deterministic proposals from the overloaded-concept
    detector. They are low-risk structural changes.
    """
    results: dict[str, Any] = {"level": "L2", "applied": False, "items": []}
    try:
        _review_ctrl, exec_ctrl = _build_controls(root)
    except Exception as exc:
        results["error"] = f"execution control unavailable: {exc}"
        return results

    split_actions = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict)
        and a.get("kind") == "split-overloaded-concept"
        and a.get("status") == "proposed"
        and str(a.get("can_review", "")).lower() in {"true", "1", "yes"}
    ]
    results["concept_splits_pending"] = len(split_actions)
    if split_actions:
        try:
            r = review_machine_memory_actions_batch(root, split_actions, status=_L2_CONCEPT_SPLIT_STATUS, note="nightly L2 auto-adopt: concept split accepted")
            results["items"].append({"kind": "concept_splits_accepted", "count": r.get("count", 0)})
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_accepted", "error": str(exc)})

    # Apply accepted splits
    apply_ids = [
        a.get("action_id", "")
        for a in exec_ctrl.get("actions", [])
        if isinstance(a, dict) and a.get("kind") == "split-overloaded-concept" and str(a.get("can_apply", "")).lower() in {"true", "1", "yes"}
    ]
    if apply_ids:
        try:
            r = apply_machine_memory_actions_batch(root, apply_ids, note="nightly L2 auto-adopt: apply concept splits", dry_run=False)
            results["items"].append({"kind": "concept_splits_applied", "count": r.get("applied_count", r.get("count", 0))})
        except Exception as exc:
            results["items"].append({"kind": "concept_splits_applied", "error": str(exc)})

    applied = any(item.get("count", 0) > 0 for item in results["items"] if "count" in item)
    results["applied"] = applied
    return results


def auto_adopt_judgments(
    root: Path,
    client: Any,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """LLM-powered judgment review for counter-evidence pages.

    Reads each judgment page, the new sources that may refute it, and asks the
    LLM to produce a structured review. The review is appended as a review
    history entry on the judgment page.

    Args:
        root: Vault root path.
        client: An LLM client implementing ``SupportsComplete``.
        limit: Max pages to review per nightly run (default 5).
    """
    import json as _json

    results: dict[str, Any] = {"level": "Judgment", "applied": False, "items": []}

    try:
        from ..app_state import load_machine_memory

        memory = load_machine_memory(root)
    except Exception as exc:
        results["error"] = f"memory unavailable: {exc}"
        return results

    scan = memory.get("health", {}).get("counter_evidence_scan", {})
    pages = scan.get("pages") if isinstance(scan, dict) else []
    if not isinstance(pages, list) or not pages:
        results["message"] = "no counter-evidence pages to review"
        return results

    reviewed = 0
    for page in pages[:limit]:
        if not isinstance(page, dict):
            continue
        page_path_str = str(page.get("page_path") or "").strip()
        source_ids = page.get("source_ids")
        if not page_path_str or not isinstance(source_ids, list) or not source_ids:
            continue

        page_path = root / page_path_str
        if not page_path.exists():
            continue

        try:
            judgment_text = page_path.read_text(encoding="utf-8")
            sources_text = _read_source_pages(root, source_ids, max_chars=8000)
            conclusion = _llm_review_judgment(client, judgment_text, sources_text, str(page.get("page_title") or page_path_str))
            _write_review_entry(root, page_path_str, conclusion)
            results["items"].append({
                "page": page_path_str,
                "conclusion": conclusion.get("conclusion", "?"),
                "confidence": conclusion.get("confidence", "?"),
            })
            reviewed += 1
        except Exception as exc:
            results["items"].append({"page": page_path_str, "error": str(exc)})

    results["reviewed"] = reviewed
    results["total_candidates"] = len(pages)
    results["applied"] = reviewed > 0
    return results


def _read_source_pages(root: Path, source_ids: list[str], max_chars: int = 8000) -> str:
    """Read up to 4 new source pages, truncating to ``max_chars`` total."""
    parts: list[str] = []
    total = 0
    for sid in source_ids[:4]:
        if not isinstance(sid, str) or not sid.strip():
            continue
        # Normalize: source_ids may be bare ids or wiki/sources/<id>.md paths
        source_path = root / "wiki" / "sources" / f"{sid}.md"
        if not source_path.exists():
            # Try as-is path
            source_path = root / sid
        if not source_path.exists():
            continue
        content = source_path.read_text(encoding="utf-8")
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n…(truncated)"
        parts.append(f"--- 来源: {sid} ---\n{content}")
        total += len(content)
    return "\n\n".join(parts) if parts else "(无新来源内容可读)"


_JUDGMENT_SYSTEM_PROMPT = """你是炼丹炉的判断复核 Agent。读取一个已有的判断页和可能反驳它的新来源材料，分析新证据是否动摇了原始判断。

返回纯 JSON（不要 markdown 包裹）：
{
  "conclusion": "upheld" | "weakened" | "refuted",
  "confidence": "high" | "medium" | "low",
  "counter_evidence_found": true | false,
  "key_findings": ["发现1", "发现2"],
  "recommendation": "一句话建议：是否需要人工复审，或判断是否仍然成立"
}

判断标准：
- upheld：新来源与原始判断一致或无关，判断仍然成立
- weakened：新来源引入了一些不确定性，但不足以推翻原始判断
- refuted：新来源明确反驳了原始判断的核心论点
"""


def _llm_review_judgment(
    client: Any,
    judgment_text: str,
    sources_text: str,
    title: str,
) -> dict[str, Any]:
    """Call the LLM to review a judgment with new evidence."""
    import json as _json
    import re

    user_prompt = f"""## 原始判断

{judgment_text[:12000]}

## 新来源材料

{sources_text}

请分析新来源是否反驳了原始判断，返回 JSON。"""
    try:
        result = client.complete(
            system_prompt=_JUDGMENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        text = str(getattr(result, "text", "") or "")
    except Exception as exc:
        return {"conclusion": "error", "confidence": "low", "error": str(exc)}

    # Extract JSON from potential markdown fences
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"conclusion": "unparsed", "confidence": "low", "raw": text[:500]}
    try:
        return _json.loads(match.group(0))
    except (_json.JSONDecodeError, TypeError):
        return {"conclusion": "unparsed", "confidence": "low", "raw": text[:500]}


def _write_review_entry(root: Path, page_path: str, conclusion: dict[str, Any]) -> None:
    """Append a review history entry to a judgment page."""
    from datetime import timezone as _tz

    page = root / page_path
    if not page.exists():
        return
    content = page.read_text(encoding="utf-8")
    now = __import__("datetime").datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conclusion_text = str(conclusion.get("conclusion") or "unknown")
    confidence_text = str(conclusion.get("confidence") or "unknown")
    findings = conclusion.get("key_findings", [])
    if isinstance(findings, list):
        findings_str = "; ".join(str(f) for f in findings[:3])
    else:
        findings_str = ""
    recommendation = str(conclusion.get("recommendation") or "")

    entry = (
        f"- {now} | AI-reviewed (counter-evidence) | conclusion: {conclusion_text} "
        f"| confidence: {confidence_text}"
    )
    if findings_str:
        entry += f" | findings: {findings_str}"
    if recommendation:
        entry += f" | recommendation: {recommendation}"

    if "## Review History" in content:
        content = content.replace("## Review History", f"## Review History\n{entry}")
    elif "## 审阅历史" in content:
        content = content.replace("## 审阅历史", f"## 审阅历史\n{entry}")
    else:
        content += f"\n\n## Review History\n{entry}\n"

    page.write_text(content, encoding="utf-8")


__all__ = ["auto_adopt_l1", "auto_adopt_l2", "auto_adopt_judgments", "_env_flag"]
