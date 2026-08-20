"""Output artifact collection and recurring-promotion annotation.

Extracted from content.io (hub single seam 2026-08-05).
"""

from __future__ import annotations

from pathlib import Path

from ..input_router import is_obsidian_open_link
from ..protocol.runtime_config import AUTO_PROMOTION_FORMATS
from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import atomic_write_text
from ..utils.markdown import (
    build_citation_snapshots,
    extract_provenance_paths,
    first_markdown_heading,
    parse_frontmatter,
    render_frontmatter,
    replace_first_markdown_heading,
    strip_frontmatter,
    upsert_markdown_section,
)
from ..utils.path import relative_path
from .outputs import normalize_query_signature


def collect_output_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") != "output":
                continue
            query = str(frontmatter.get("query") or "").strip()
            output_format = str(frontmatter.get("format") or "").strip()
            if not query or output_format not in AUTO_PROMOTION_FORMATS:
                continue
            if is_obsidian_open_link(query):
                continue
            artifacts.append(
                {
                    "path": relative_path(root, path),
                    "query": query,
                    "query_signature": normalize_query_signature(query),
                    "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                    "format": output_format,
                    "created_at": str(frontmatter.get("created_at") or ""),
                    "title": first_markdown_heading(content) or path.stem,
                }
            )
    return sorted(artifacts, key=lambda item: (item["query_signature"], item["created_at"], item["path"]))


def collect_output_density_artifacts(root: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") == "output":
                query = str(frontmatter.get("query") or "").strip()
                if is_obsidian_open_link(query):
                    continue
                artifacts.append(
                    {
                        "path": relative_path(root, path),
                        "query": query,
                        "format": str(frontmatter.get("format") or "").strip(),
                        "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                        "created_at": str(frontmatter.get("created_at") or ""),
                        "title": first_markdown_heading(content) or path.stem,
                        "run_id": str(frontmatter.get("run_id") or ""),
                        "run_notes_path": str(frontmatter.get("run_notes_path") or ""),
                    }
                )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]))


def collect_recent_output_artifacts(root: Path, *, limit: int = 12) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for relative in ("output/reports", "output/slides", "output/figures"):
        for path in sorted((root / relative).glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter = parse_frontmatter(content)
            if frontmatter.get("kind") == "output" and str(frontmatter.get("generated_by") or "") != "aiwiki-compile":
                background_status = str(frontmatter.get("background_status") or "")
                title = first_markdown_heading(content) or path.stem
                delivery_mode = str(frontmatter.get("delivery_mode") or "")
                llm_status = str(frontmatter.get("llm_status") or "")
                contains_placeholder = "_LLM:" in content
                query = str(frontmatter.get("query") or "").strip()
                artifact_quality_hint = str(frontmatter.get("artifact_quality") or "").strip()
                if (
                    is_obsidian_open_link(query)
                    or (contains_placeholder and llm_status in {"", "pending"})
                    or llm_status == "pending"
                    or artifact_quality_hint == "placeholder"
                    or delivery_mode in {"llm-pending", "pending"}
                ):
                    continue
                degraded = (
                    delivery_mode == "deterministic-fallback"
                    or llm_status in {"timeout_or_unavailable", "validation_failed", "pending", "failed", "degraded", "material_unreadable"}
                    or background_status == "degraded"
                    or title.startswith("LLM 未完成")
                    or artifact_quality_hint == "degraded"
                )
                if artifact_quality_hint == "no-evidence":
                    artifact_quality = "no-evidence"
                elif degraded:
                    artifact_quality = "degraded"
                else:
                    artifact_quality = "deliverable"
                artifacts.append(
                    {
                        "path": relative_path(root, path),
                        "query": query,
                        "format": str(frontmatter.get("format") or "").strip(),
                        "protocol": str(frontmatter.get("protocol") or DEFAULT_PROTOCOL),
                        "created_at": str(frontmatter.get("created_at") or ""),
                        "title": title,
                        "run_id": str(frontmatter.get("run_id") or ""),
                        "run_notes_path": str(frontmatter.get("run_notes_path") or ""),
                        "delivery_mode": delivery_mode,
                        "llm_status": llm_status,
                        "llm_backend": str(frontmatter.get("llm_backend") or ""),
                        "llm_model": str(frontmatter.get("llm_model") or ""),
                        "llm_failure_reason": str(frontmatter.get("llm_failure_reason") or ""),
                        "background_status": background_status,
                        "artifact_quality": artifact_quality,
                        "contains_llm_placeholder": "true" if contains_placeholder else "false",
                    }
                )
    return sorted(artifacts, key=lambda item: (item["created_at"], item["path"]), reverse=True)[:limit]


def find_promoted_curated_page(root: Path, kind: str, query_signature: str, protocol: str) -> Path | None:
    folder = "decisions" if kind == "decision" else "judgments"
    for path in sorted((root / "wiki" / folder).glob("*.md")):
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        if (
            frontmatter.get("kind") == kind
            and str(frontmatter.get("promotion_query_signature") or "") == query_signature
        ):
            page_protocol = str(frontmatter.get("protocol") or "")
            if page_protocol == protocol or (not page_protocol and protocol == DEFAULT_PROTOCOL):
                return path
    return None


def recurring_promotion_needs_refresh(page_path: Path, artifacts: list[dict[str, str]]) -> bool:
    frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8", errors="replace"))
    current_count = str(frontmatter.get("promotion_count") or "")
    current_last_artifact = str(frontmatter.get("promotion_last_artifact") or "")
    current_sources = {
        str(path) for path in frontmatter.get("source_files", []) if isinstance(path, str) and path.strip()
    }
    desired_count = str(len(artifacts))
    desired_last_artifact = artifacts[-1]["path"]
    desired_sources = {artifact["path"] for artifact in artifacts}
    return (
        current_count != desired_count
        or current_last_artifact != desired_last_artifact
        or not desired_sources.issubset(current_sources)
    )


def annotate_recurring_promotion(
    root: Path,
    page_path: Path,
    *,
    kind: str,
    protocol: str,
    query: str,
    query_signature: str,
    artifacts: list[dict[str, str]],
    generated_at: str,
) -> None:
    content = page_path.read_text(encoding="utf-8", errors="replace")
    frontmatter = parse_frontmatter(content)
    source_files = [str(path) for path in frontmatter.get("source_files", []) if isinstance(path, str) and path.strip()]
    for artifact in artifacts:
        if artifact["path"] not in source_files:
            source_files.append(artifact["path"])
    citations = [str(path) for path in frontmatter.get("citations", []) if isinstance(path, str) and path.strip()]
    seen_citations = set(citations)
    for artifact in artifacts:
        artifact_path = root / artifact["path"]
        if artifact_path.exists():
            for citation in extract_provenance_paths(root, artifact_path.read_text(encoding="utf-8", errors="replace")):
                if citation not in seen_citations:
                    seen_citations.add(citation)
                    citations.append(citation)
    formats = sorted({artifact["format"] for artifact in artifacts})
    from .outputs import promotion_page_title

    title = promotion_page_title(kind, query, protocol)
    citation_snapshots = build_citation_snapshots(root, citations)
    frontmatter.update(
        {
            "title": title,
            "protocol": protocol,
            "source_files": source_files,
            "citations": citations,
            "citation_snapshots": citation_snapshots,
            "promotion_origin": "nightly-recurring-output",
            "promotion_query": query,
            "promotion_query_signature": query_signature,
            "promotion_count": str(len(artifacts)),
            "promotion_formats": formats,
            "promotion_last_artifact": artifacts[-1]["path"],
            "last_compiled_at": generated_at,
        }
    )
    body = replace_first_markdown_heading(strip_frontmatter(content).strip(), title).strip()
    auto_lines = [
        "- Rule: `nightly-recurring-output`",
        f"- Protocol: `{protocol}`",
        f"- Query: `{query}`",
        f"- Signature: `{query_signature}`",
        f"- Matching outputs: `{len(artifacts)}`",
        f"- Latest artifact: `{artifacts[-1]['path']}`",
        f"- Formats: `{', '.join(formats)}`",
    ]
    for artifact in artifacts[-5:]:
        auto_lines.append(f"- Supporting artifact: `{artifact['path']}`")
    section = upsert_markdown_section(body, "Auto Promotion", "\n".join(auto_lines)).strip()
    atomic_write_text(page_path, f"{render_frontmatter(frontmatter)}\n\n{section}\n")

