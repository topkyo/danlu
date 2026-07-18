"""Local deterministic stats intents extracted from runner/workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aiwiki.app_queries import human_query_title
from aiwiki.execution.alchemy import CANDIDATE_ELIXIR_DIR
from aiwiki.utils.markdown import parse_frontmatter, render_frontmatter, strip_frontmatter
from aiwiki.utils.path import relative_path

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


def clean_local_intent_question(question: str) -> str:
    text = clean_report_reference_question(question)
    text = re.sub(r"valut", "vault", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text or human_query_title(question)


def is_elixir_count_question(question: str) -> bool:
    text = clean_local_intent_question(question).lower()
    if not text:
        return False
    has_elixir = "金丹" in text or "elixir" in text or "elixirs" in text
    has_count = any(marker in text for marker in ("几个", "多少", "数量", "count", "how many", "num"))
    has_local = any(marker in text for marker in ("炼丹炉", "vault", "仓库", "当前", "本地", "这个"))
    return has_elixir and has_count and has_local


def is_markdown_count_question(question: str) -> bool:
    text = clean_local_intent_question(question).lower()
    if not text:
        return False
    has_markdown = "md" in text or "markdown" in text or "markdown 文件" in text or "md文件" in text
    has_count = any(marker in text for marker in ("几个", "多少", "数量", "count", "how many", "num"))
    has_local = any(marker in text for marker in ("炼丹炉", "vault", "仓库", "当前", "本地", "这个"))
    return has_markdown and has_count and has_local


def _markdown_count_bucket(path: Path) -> str:
    parts = path.parts
    if not parts:
        return "other"
    return parts[0] if parts[0] in {"raw", "wiki", "output", "prompts"} else "other"


def collect_markdown_counts(root: Path) -> dict[str, Any]:
    ignored_dirs = {".git", ".obsidian", ".aiwiki", ".codex", ".claude", ".opencode", "node_modules", ".venv"}
    counts = {"raw": 0, "wiki": 0, "output": 0, "prompts": 0, "other": 0}
    examples: dict[str, list[str]] = {key: [] for key in counts}
    total = 0
    for path in sorted(root.rglob("*.md")):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in ignored_dirs for part in relative.parts):
            continue
        bucket = _markdown_count_bucket(relative)
        counts[bucket] += 1
        total += 1
        if len(examples[bucket]) < 8:
            examples[bucket].append(relative.as_posix())
    return {"total": total, "by_top_level": counts, "examples": examples}


def local_markdown_count_artifact_markdown(
    *,
    artifact_id: str,
    question: str,
    protocol: str,
    created_at: str,
    stats: dict[str, Any],
) -> str:
    title = clean_local_intent_question(question)
    counts = dict(stats.get("by_top_level", {}))
    examples = dict(stats.get("examples", {}))
    frontmatter = {
        "id": artifact_id,
        "kind": "output",
        "format": "note",
        "cssclasses": [OUTPUT_OBSIDIAN_CSSCLASS],
        "query": question,
        "protocol": protocol,
        "generated_by": "aiwiki-local-markdown-stats",
        "created_at": created_at,
        "delivery_mode": "local-deterministic",
        "markdown_file_count": int(stats.get("total") or 0),
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# {title}",
        "",
        "## 回答",
        f"- 当前 vault 中可见 Markdown 文件共 **{int(stats.get('total') or 0)} 个**。",
        f"- `raw/`：{int(counts.get('raw') or 0)} 个。",
        f"- `wiki/`：{int(counts.get('wiki') or 0)} 个。",
        f"- `output/`：{int(counts.get('output') or 0)} 个。",
        f"- `prompts/`：{int(counts.get('prompts') or 0)} 个。",
        f"- 其他可见目录：{int(counts.get('other') or 0)} 个。",
        "",
        "## 示例路径",
    ]
    for bucket in ("raw", "wiki", "output", "prompts", "other"):
        bucket_examples = [str(item) for item in examples.get(bucket, [])]
        if not bucket_examples:
            continue
        lines.append(f"### `{bucket}/`")
        for item in bucket_examples:
            lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            "## 口径",
            "- 统计对象：当前 vault 内可见的 `*.md` 文件。",
            "- 排除目录：`.git/`、`.obsidian/`、`.aiwiki/`、local harness 目录、`node_modules/`、`.venv/`。",
            "- 本回答由本地文件系统确定性统计生成，没有调用 LLM。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _elixir_markdown_title(path: Path, frontmatter: dict[str, Any]) -> str:
    for key in ("topic", "title", "id"):
        value = str(frontmatter.get(key) or "").strip()
        if value and value.lower() != "elixir":
            return value
    body = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")) if path.exists() else ""
    for line in body.splitlines():
        heading = line.strip()
        if heading.startswith("#"):
            title = heading.lstrip("#").strip()
            if title and title.lower() != "elixir":
                return title
    return path.stem


def collect_elixir_counts(root: Path) -> dict[str, Any]:
    settled: list[dict[str, str]] = []
    elixir_dir = root / "wiki" / "elixirs"
    for path in sorted(elixir_dir.glob("*.md")) if elixir_dir.exists() else []:
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        state = str(frontmatter.get("elixir_state") or "").strip()
        if state and state != "settled":
            continue
        settled.append(
            {
                "path": relative_path(root, path),
                "title": _elixir_markdown_title(path, frontmatter),
                "state": state or "settled",
            }
        )
    candidate_dir = root / CANDIDATE_ELIXIR_DIR
    candidates = (
        [relative_path(root, path) for path in sorted(candidate_dir.glob("*.md"))] if candidate_dir.exists() else []
    )
    return {"settled": settled, "candidates": candidates}


def local_elixir_count_artifact_markdown(
    *,
    artifact_id: str,
    question: str,
    protocol: str,
    created_at: str,
    stats: dict[str, Any],
) -> str:
    title = clean_local_intent_question(question)
    settled = list(stats.get("settled", []))
    candidates = [str(item) for item in stats.get("candidates", [])]
    frontmatter = {
        "id": artifact_id,
        "kind": "output",
        "format": "note",
        "cssclasses": [OUTPUT_OBSIDIAN_CSSCLASS],
        "query": question,
        "protocol": protocol,
        "generated_by": "aiwiki-local-elixir-stats",
        "created_at": created_at,
        "delivery_mode": "local-deterministic",
        "settled_elixir_count": len(settled),
        "candidate_elixir_count": len(candidates),
    }
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# {title}",
        "",
        "## 回答",
        f"- 当前 vault 已沉淀金丹 **{len(settled)} 个**。",
        f"- 另有候选金丹 **{len(candidates)} 个**，位于 `{CANDIDATE_ELIXIR_DIR}/`。",
        "",
        "## 已沉淀金丹",
    ]
    if settled:
        for item in settled:
            lines.append(f"- [{item['title']}]({item['path']}) — `{item['path']}`")
    else:
        lines.append("- 当前没有 settled 金丹文件。")
    lines.extend(["", "## 候选金丹"])
    if candidates:
        for path in candidates[:20]:
            lines.append(f"- `{path}`")
    else:
        lines.append("- 当前没有候选金丹文件。")
    lines.extend(
        [
            "",
            "## 口径",
            "- settled 金丹：`wiki/elixirs/*.md` 且 `elixir_state` 为空或 `settled`。",
            f"- 候选金丹：`{CANDIDATE_ELIXIR_DIR}/*.md`。",
            "- 本回答由本地文件系统确定性统计生成，没有调用 LLM。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "OUTPUT_OBSIDIAN_CSSCLASS",
    "OUTPUT_REPORT_LEAF_CSSCLASS",
    "clean_local_intent_question",
    "clean_report_reference_question",
    "collect_elixir_counts",
    "collect_markdown_counts",
    "is_elixir_count_question",
    "is_markdown_count_question",
    "local_elixir_count_artifact_markdown",
    "local_markdown_count_artifact_markdown",
]
