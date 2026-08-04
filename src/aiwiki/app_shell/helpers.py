from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..execution.history import load_llm_receipt_history
from ..input_router import is_obsidian_open_link

LLM_FRONTDOOR_EVENTS = {
    "run-ask-frontdoor",
    "run-ask",
    "run-compile",
    "run-compile-concept",
    "run-compile-concept-rewrite-proposal",
    "run-compile-summary",
    "run-lint",
    "run-nightly",
}
LLM_PRIMARY_HEALTH_EVENTS = ("run-ask-frontdoor", "run-ask")


def _latest_llm_receipt(root: Path, *, preferred_events: tuple[str, ...] = ()) -> dict[str, Any]:
    history = load_llm_receipt_history(root)
    if preferred_events:
        for event in reversed(history):
            if not isinstance(event, dict):
                continue
            if is_obsidian_open_link(str(event.get("question") or "")):
                continue
            if str(event.get("event") or "") in preferred_events:
                return dict(event)
    for event in reversed(history):
        if not isinstance(event, dict):
            continue
        if is_obsidian_open_link(str(event.get("question") or "")):
            continue
        if str(event.get("event") or "") in LLM_FRONTDOOR_EVENTS:
            return dict(event)
    return {}


def _first_non_empty(event: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _build_llm_rerun_command(event: dict[str, Any]) -> str:
    event_name = str(event.get("event") or "")
    target = str(event.get("target") or "")
    prompt_profile = str(event.get("prompt_profile") or "")
    command_parts = ["./scripts/aiwiki-launcher.sh"]
    if event_name in {"run-ask", "run-ask-frontdoor"}:
        question = str(event.get("question") or "").strip()
        output_format = str(event.get("format") or "report").strip() or "report"
        if not question:
            return ""
        command_parts.extend(["advanced", "run-ask", json.dumps(question), "--format", output_format])
        if prompt_profile == "lean":
            command_parts.append("--lean")
        return " ".join(command_parts)
    if event_name == "run-compile-summary":
        command_parts.extend(["advanced", "compile"])
        return " ".join(command_parts)
    if event_name == "run-lint":
        command_parts.extend(["advanced", "lint"])
        return " ".join(command_parts)
    if event_name == "run-nightly":
        limit = int(event.get("compile_limit", 5) or 5)
        command_parts.extend(["advanced", "run-nightly", "--compile-limit", str(limit)])
        return " ".join(command_parts)
    if target:
        command_parts.extend(["advanced", event_name, target])
        return " ".join(command_parts)
    return ""
