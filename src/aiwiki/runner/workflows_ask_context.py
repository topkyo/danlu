"""Context preparation helpers for run-ask workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiwiki.runner.report_refs import clean_report_reference_question, extract_report_reference_paths
from aiwiki.state.manifest import load_manifest
from aiwiki.utils.markdown import strip_frontmatter


def _load_compound_context_pages(
    root: Path,
    machine_query: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    subgraph = machine_query.get("query_subgraph", {}) or {}
    judgment_pages: list[tuple[str, str]] = []
    for node in subgraph.get("judgments", []) or []:
        if not isinstance(node, dict):
            continue
        page_id = str(node.get("page_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not page_id or not path:
            continue
        page = root / path
        if page.exists():
            judgment_pages.append((page_id, page.read_text(encoding="utf-8", errors="replace")))
    elixir_pages: list[tuple[str, str]] = []
    for node in subgraph.get("elixirs", []) or []:
        if not isinstance(node, dict):
            continue
        elixir_id = str(node.get("elixir_id") or "").strip()
        path = str(node.get("path") or "").strip()
        if not elixir_id or not path:
            continue
        page = root / path
        if page.exists():
            elixir_pages.append((elixir_id, page.read_text(encoding="utf-8", errors="replace")))
    return judgment_pages, elixir_pages


def _run_ask_prepared_context(root: Path, question: str, artifact: dict[str, Any]) -> dict[str, Any]:
    manifest = load_manifest(root)
    entry_map = {entry["id"]: entry for entry in manifest["entries"]}
    source_ids = artifact["ranked_sources"]
    source_pages = []
    for source_id in source_ids:
        entry = entry_map.get(source_id)
        if entry is None:
            continue
        page = root / "wiki" / "sources" / f"{source_id}.md"
        if page.exists():
            source_pages.append((entry, page.read_text(encoding="utf-8", errors="replace")))
    concept_pages = []
    for slug in artifact.get("ranked_concepts", []):
        page = root / "wiki" / "concepts" / f"{slug}.md"
        if page.exists():
            concept_pages.append((slug, page.read_text(encoding="utf-8", errors="replace")))
    protocol_pages = []
    for relative in artifact.get("protocol_pages", []):
        page = root / relative
        if page.exists():
            protocol_pages.append((relative, page.read_text(encoding="utf-8", errors="replace")))
    index_pages = []
    for relative in artifact.get("index_pages", []):
        page = root / relative
        if page.exists():
            index_pages.append((relative, page.read_text(encoding="utf-8", errors="replace")))
    machine_query = artifact.get("machine_memory_query", {}) or {}
    judgment_pages, elixir_pages = _load_compound_context_pages(root, machine_query)
    target = root / artifact["path"]
    current_artifact = _strip_run_notes_prompt_fields(target.read_text(encoding="utf-8", errors="replace"))
    return {
        "source_ids": source_ids,
        "source_pages": source_pages,
        "concept_pages": concept_pages,
        "protocol_pages": protocol_pages,
        "index_pages": index_pages,
        "judgment_pages": judgment_pages,
        "elixir_pages": elixir_pages,
        "target": target,
        "current_artifact": current_artifact,
        "question": question,
    }


def _strip_run_notes_prompt_fields(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return _strip_pending_llm_placeholder_body(markdown)
    close_idx: int | None = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            close_idx = idx
            break
    if close_idx is None:
        return _strip_pending_llm_placeholder_body(markdown)
    control_prefixes = (
        "run_id:",
        "run_notes_path:",
        "background_job_id:",
        "background_status:",
        "delivery_mode:",
        "llm_status:",
        "llm_failure_reason:",
        "llm_backend:",
        "llm_model:",
        "artifact_quality:",
    )
    filtered = [line for line in lines[: close_idx + 1] if not line.startswith(control_prefixes)]
    filtered.extend(lines[close_idx + 1 :])
    cleaned = "\n".join(filtered) + ("\n" if markdown.endswith("\n") else "")
    return _strip_pending_llm_placeholder_body(cleaned)


def _strip_pending_llm_placeholder_body(markdown: str) -> str:
    """Keep scaffold refs for the model, but do not feed `_LLM:` placeholder lines."""

    lines = str(markdown or "").splitlines()
    if not any(line.lstrip().startswith("_LLM:") for line in lines):
        return markdown
    kept: list[str] = []
    replaced = False
    for line in lines:
        if line.lstrip().startswith("_LLM:"):
            if not replaced:
                kept.append("_Runtime note: replace this whole body with the final answer. Do not keep `_LLM:` lines._")
                replaced = True
            continue
        kept.append(line)
    return "\n".join(kept) + ("\n" if str(markdown).endswith("\n") else "")


def _material_hint_paths(question: str) -> list[str]:
    text = str(question or "")
    paths: list[str] = []
    for marker in ("材料路径供系统路由使用：", "本次投喂材料路径："):
        if marker not in text:
            continue
        tail = text.split(marker, 1)[1]
        tail = tail.split("用户问题：", 1)[0]
        for raw_item in tail.replace("、", "\n").replace(",", "\n").splitlines():
            item = raw_item.strip().lstrip("- ").strip()
            if item and any(item.startswith(prefix) for prefix in ("raw/", "wiki/", "output/", ".aiwiki/")):
                paths.append(item.strip("`"))
    return paths


def _quoted_report_reference_paths(question: str) -> list[str]:
    return extract_report_reference_paths(question)


def _safe_quoted_report_reference_paths(root: Path, refs: list[str]) -> list[str]:
    safe_refs: list[str] = []
    seen: set[str] = set()
    try:
        root_resolved = root.resolve()
        reports_root = (root / "output" / "reports").resolve()
    except OSError:
        return []
    for ref in refs:
        text = str(ref or "").strip().strip("` ")
        if not text or "\\" in text or text.startswith("/"):
            continue
        if not text.startswith("output/reports/") or not text.endswith(".md"):
            continue
        candidate = root / text
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root_resolved)
            resolved.relative_to(reports_root)
        except (OSError, ValueError):
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if resolved.suffix.lower() != ".md":
            continue
        if text in seen:
            continue
        seen.add(text)
        safe_refs.append(text)
    return safe_refs


def _quoted_report_material_refs(root: Path, question: str) -> list[str]:
    quoted_refs = _quoted_report_reference_paths(question)
    if not quoted_refs:
        return []
    safe_refs = _safe_quoted_report_reference_paths(root, quoted_refs)
    safe_set = set(safe_refs)
    invalid_refs = [ref for ref in quoted_refs if ref not in safe_set]
    if invalid_refs:
        missing = ", ".join(invalid_refs)
        raise ValueError(f"quoted report reference is missing or unsafe: {missing}")
    return safe_refs


def _clean_report_reference_question(question: str) -> str:
    return clean_report_reference_question(question)


def _read_material_context(root: Path, refs: list[str], *, max_chars: int = 6000) -> dict[str, Any]:
    snippets: list[str] = []
    used_context_refs: list[dict[str, Any]] = []
    remaining = max_chars
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root
    for ref in refs:
        if remaining <= 0:
            break
        path = root / ref
        try:
            path = path.resolve()
            path.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        if not path.exists() or path.is_dir():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace")).strip()
        if not text:
            continue
        excerpt = text[:remaining]
        snippets.append(f"## {ref}\n\n{excerpt}")
        used_context_refs.append(
            {
                "path": ref,
                "kind": _context_kind_for_path(ref),
                "excerpt_chars": len(excerpt),
                "selection_reason": "explicit-material-ref",
            }
        )
        remaining -= len(excerpt)
    return {
        "text": "\n\n".join(snippets).strip(),
        "used_context_refs": used_context_refs,
        "context_budget": {"explicit_material_refs": len(refs), "max_chars": max_chars},
    }


def _context_kind_for_path(relative: str) -> str:
    if relative.startswith("wiki/elixirs/"):
        return "elixir"
    if relative.startswith("wiki/judgments/"):
        return "judgment"
    if relative.startswith("wiki/decisions/"):
        return "decision"
    if relative.startswith("wiki/sources/"):
        return "source"
    if relative.startswith("wiki/concepts/"):
        return "concept"
    if relative.startswith("output/reports/"):
        return "material-report"
    if relative.startswith("raw/"):
        return "raw-material"
    return "material"


def _context_ref_paths(records: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for record in records:
        path = str(record.get("path") or "").strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _material_refs_unreadable(root: Path, refs: list[str], context_text: str) -> bool:
    """True when refs are present but no usable textual material context was loaded."""

    cleaned_refs = [str(item).strip() for item in refs if str(item).strip()]
    if not cleaned_refs:
        return False
    if str(context_text or "").strip():
        return False
    return True


def _build_unreadable_material_ask_markdown(
    *,
    question: str,
    material_refs: list[str],
    frontmatter: dict[str, Any],
) -> str:
    from aiwiki.utils.markdown import render_frontmatter
    from aiwiki.utils.text import human_query_title

    refs = [str(item).strip() for item in material_refs if str(item).strip()]
    title = human_query_title(question) if question else "材料不可读"
    lines = [
        render_frontmatter(frontmatter),
        "",
        f"# {title}",
        "",
        "**答案**：材料已登记，但当前无法读取其内容（例如图片尚无可用视觉摘要，或路径不是可读文本）。"
        "因此不能分析附件内容，也不会用其它 wiki 来源冒充回答。",
        "",
        "## 已登记材料",
    ]
    if refs:
        lines.extend(f"- `{ref}`" for ref in refs)
    else:
        lines.append("- （无路径）")
    lines.extend(
        [
            "",
            "## 建议",
            "- 若是图片：先确认视觉分析可用，或改投文字 / Markdown 摘要后再问。",
            "- 若是文本材料：确认路径存在且为 `.md` / `.txt` 后重试。",
            "",
            "## 参考",
            "- 本回答未引用无关 wiki 来源。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
