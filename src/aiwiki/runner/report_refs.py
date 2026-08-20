"""Report reference parsing and output CSS class constants for run-ask."""

from __future__ import annotations

import re
from urllib.parse import unquote

from aiwiki.utils.text import human_query_title

OUTPUT_OBSIDIAN_CSSCLASS = "aiwiki-output"
OUTPUT_REPORT_LEAF_CSSCLASS = "aiwiki-report-leaf"

_REPORT_REFERENCE_RE = re.compile(
    r"引用报告\s*[:：]\s*(?:"
    r"`(?P<backtick>output/reports/[^`\r\n]+?)(?:\.md)?`|"
    r"<(?P<angle>output/reports/[^>\r\n]+?)(?:\.md)?>|"
    r"\[\[(?P<wiki>output/reports/[^\]\|\r\n]+?)(?:\.md)?(?:\|[^\]\r\n]*)?\]\]|"
    r"\[[^\]\r\n]*\]\((?P<markdown>output/reports/[^)\r\n]+?)(?:\.md)?\)|"
    r"(?P<plain_md>output/reports/[^\r\n`<>\[]+?\.md)|"
    r"(?P<plain_token>output/reports/[^\s`<>\[]+)"
    r")",
    flags=re.IGNORECASE,
)


def _normalize_report_reference_path(raw: str) -> str:
    text = unquote(str(raw or "").strip()).strip("` <>")
    text = text.split("#", 1)[0].strip()
    text = re.sub(r"[\s,，;；。.!！?？]+$", "", text).strip()
    if not text.startswith("output/reports/"):
        return ""
    if not text.endswith(".md"):
        text = f"{text}.md"
    return text


def extract_report_reference_paths(question: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in _REPORT_REFERENCE_RE.finditer(str(question or "")):
        raw = next((value for value in match.groupdict().values() if value), "")
        path = _normalize_report_reference_path(raw)
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def clean_report_reference_question(question: str) -> str:
    text = _REPORT_REFERENCE_RE.sub("", str(question or "")).strip()
    text = human_query_title(text)
    text = _REPORT_REFERENCE_RE.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text or "未命名问题"


__all__ = [
    "OUTPUT_OBSIDIAN_CSSCLASS",
    "OUTPUT_REPORT_LEAF_CSSCLASS",
    "clean_report_reference_question",
    "extract_report_reference_paths",
]
