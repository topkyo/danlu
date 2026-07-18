"""Machine-memory snapshot builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.concepts import concept_label_to_slug, normalize_concept_hardness, parse_causal_links
from ..content.io import source_summary_or_preview
from ..utils.markdown import parse_frontmatter
from ..utils.text import tokenize


def build_machine_memory(
    root: Path,
    entries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    previews: dict[str, str],
    entry_terms: dict[str, list[str]],
    compiled_at: str,
) -> dict[str, Any]:
    term_index: dict[str, dict[str, set[str]]] = {}
    source_nodes: list[dict[str, Any]] = []
    concept_nodes: list[dict[str, Any]] = []
    source_to_concept: list[dict[str, str]] = []
    concept_to_concept: list[dict[str, str]] = []
    concept_causal: list[dict[str, str]] = []
    citation_map: list[dict[str, Any]] = []

    def index_term(
        term: str,
        *,
        source_id: str | None = None,
        concept_slug: str | None = None,
        judgment_page_id: str | None = None,
        elixir_id: str | None = None,
    ) -> None:
        bucket = term_index.setdefault(
            term,
            {
                "source_ids": set(),
                "concept_slugs": set(),
                "judgment_page_ids": set(),
                "elixir_ids": set(),
            },
        )
        if source_id:
            bucket["source_ids"].add(source_id)
        if concept_slug:
            bucket["concept_slugs"].add(concept_slug)
        if judgment_page_id:
            bucket["judgment_page_ids"].add(judgment_page_id)
        if elixir_id:
            bucket["elixir_ids"].add(elixir_id)

    for entry in entries:
        concept_slugs = [concept_label_to_slug(label) for label in entry_terms.get(entry["id"], [])]
        source_page = f"wiki/sources/{entry['id']}.md"
        summary = source_summary_or_preview(root, entry, previews[entry["id"]])
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "source_type": entry["source_type"],
                "kind": entry["kind"],
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
                "source_page": source_page,
                "concept_slugs": concept_slugs,
            }
        )
        citation_map.append(
            {
                "source_page": source_page,
                "stored_path": entry["stored_path"],
                "original_path": entry["original_path"],
                "sha256": entry["sha256"],
            }
        )
        for slug in concept_slugs:
            source_to_concept.append({"source_id": entry["id"], "concept_slug": slug})
        for token in tokenize(f"{entry['title']}\n{summary}"):
            index_term(token, source_id=entry["id"])

    for record in concepts:
        page = root / "wiki" / "concepts" / f"{record['slug']}.md"
        frontmatter = parse_frontmatter(page.read_text(encoding="utf-8", errors="replace")) if page.exists() else {}
        causal_links = parse_causal_links(frontmatter)
        concept_nodes.append(
            {
                "slug": record["slug"],
                "title": record["title"],
                "path": f"wiki/concepts/{record['slug']}.md",
                "source_pages": [f"wiki/sources/{entry_id}.md" for entry_id in record["entry_ids"]],
                "related_slugs": record.get("related_slugs", []),
                "source_signature": record["source_signature"],
                "confidence": str(frontmatter.get("confidence") or ""),
                "hardness": normalize_concept_hardness(frontmatter.get("hardness"), default="soft"),
                "causal_links": causal_links,
            }
        )
        for related_slug in record.get("related_slugs", []):
            concept_to_concept.append({"from": record["slug"], "to": related_slug})
        for link in causal_links:
            concept_causal.append(
                {
                    "from": record["slug"],
                    "to": link["target"],
                    "relation": link["relation"],
                    "evidence": link["evidence"],
                }
            )
        for token in tokenize(record["title"]):
            index_term(token, concept_slug=record["slug"])

    drift = {
        "missing_raw_files": [entry["stored_path"] for entry in entries if not (root / entry["stored_path"]).exists()],
        "missing_source_pages": [
            f"wiki/sources/{entry['id']}.md"
            for entry in entries
            if not (root / "wiki" / "sources" / f"{entry['id']}.md").exists()
        ],
        "missing_concept_pages": [
            f"wiki/concepts/{record['slug']}.md"
            for record in concepts
            if not (root / "wiki" / "concepts" / f"{record['slug']}.md").exists()
        ],
        "sources_without_concepts": [entry["id"] for entry in entries if not entry_terms.get(entry["id"])],
    }

    return {
        "version": 1,
        "compiled_at": compiled_at,
        "source_nodes": sorted(source_nodes, key=lambda item: item["id"]),
        "concept_nodes": sorted(concept_nodes, key=lambda item: item["slug"]),
        "edges": {
            "source_to_concept": sorted(source_to_concept, key=lambda item: (item["source_id"], item["concept_slug"])),
            "concept_to_concept": sorted(concept_to_concept, key=lambda item: (item["from"], item["to"])),
            "concept_causal": sorted(concept_causal, key=lambda item: (item["from"], item["to"], item["relation"])),
        },
        "citation_map": sorted(citation_map, key=lambda item: item["source_page"]),
        "term_index": {
            term: {
                "source_ids": sorted(payload["source_ids"]),
                "concept_slugs": sorted(payload["concept_slugs"]),
                "judgment_page_ids": sorted(payload["judgment_page_ids"]),
                "elixir_ids": sorted(payload["elixir_ids"]),
            }
            for term, payload in sorted(term_index.items())
        },
        "drift": drift,
    }
