"""Concept rendering, quality scoring, and rewrite strategy symbols extracted from app_content (EP-017C step 2)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..compile.build import load_concept_build_state
from ..corpus.parse import (
    concept_label_to_slug,
    concept_source_pages,
    normalize_concept_hardness,
    parse_causal_links,
)
from ..corpus.snapshots import (
    concept_page_snapshot as concept_page_snapshot,
)
from ..corpus.snapshots import (
    concept_summary_matches_legacy_placeholder,
    normalize_summary_snippet,
)
from ..corpus.snapshots import (
    placeholder_concept_slugs as placeholder_concept_slugs,
)
from ..protocol.runtime_config import (
    CONCEPT_HARDNESS_LEVELS,
    CONFLICT_SIGNAL_PAIRS,
    EVIDENCE_GAP_MARKERS,
)
from ..utils.hash import sha256_bytes
from ..utils.markdown import (
    parse_frontmatter,
    render_frontmatter,
)
from ..utils.text import STOP_WORDS, tokenize
from .io import load_source_page_context, preserved_section, source_summary_or_preview

# Local aliases kept for in-module call sites.
_normalize_summary_snippet = normalize_summary_snippet
_concept_summary_matches_legacy_placeholder = concept_summary_matches_legacy_placeholder

CONCEPT_RENDER_SCHEMA_VERSION = 4

# Bump when concept extraction noise floor (STOP_WORDS, length filter, digit filter, etc.)
# changes, to invalidate cached `concept-build-state.json` entries and force retroactive
# re-extraction on the next compile. See F-new-13 (Round 6) / P4-INV-2 (Round 57).
# v12: drop generic verbs/adjectives (build, queryable, agents) from single-token concepts
# and introduce _PHRASE_WEAK_TOKENS to stop filename-derived title-prefix phrases
# (e.g. plugin-llm-vault, obsidian-framework-agents) from becoming concept slugs.
# v13: extend with gerund/past-participle verb forms and pronouns that leak from
# ingested article titles (building, powered, maintain, you, base, systems).
# v14: drop generic adjectives/adverbs and duplicate plurals from article titles
# (digital, personal, privately, llms, local, ideas, component, systems).
CONCEPT_NOISE_FLOOR_VERSION = 16

CAUSAL_RELATION_LABELS = {
    "causes": "→ causes",
    "enables": "→ enables",
    "constrains": "⊣ constrains",
    "conflicts_with": "⊘ conflicts with",
}

_CONCEPT_QUARTER_TAG_PATTERN = re.compile(r"^(?:[12]\d{3}q[1-4]|q[1-4][12]\d{3})$")


def concept_candidates(entries: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in entries:
        for token in tokenize(entry["title"]):
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:10]]



def concept_label_to_title(label: str) -> str:
    words = [word for word in label.split() if word]
    if not words:
        return "Concept"
    return " ".join(word.capitalize() for word in words)


_GENERIC_SOURCE_TITLE_TERMS = {
    "readme",
    "readmemd",
    "file",
    "document",
    "untitled",
    "notes",
    "note",
    "github",
    "ar9av",
}

# Auxiliary / modal verbs and other common tokens that tokenize() does not drop
# but which are not useful as concept slugs.
_CONCEPT_EXTRA_STOP_WORDS = {
    "are",
    "was",
    "were",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "can",
    "may",
    "might",
    "shall",
    "must",
    "new",
    "turn",
    "through",
    "using",
    "based",
    "via",
    "your",
    "our",
    "them",
    "they",
    "make",
    "made",
    "use",
    "used",
    "uses",
    "get",
    "gets",
    "got",
    # v12: empirically observed noise tokens from dogfood vault concept pages.
    # "build" is a generic verb that fires on every "how to build X" title;
    # "queryable" is a technical adjective that adds no concept weight;
    # "agents" is the plural of a domain noun already covered by the singular
    # "agent" concept and by specific agent-* phrases when they are meaningful.
    # v13: gerund/past-participle verb forms and pronouns leaking from article
    # titles ("building", "powered", "maintain", "you") plus the generic noun
    # "base" which fires on every "X knowledge base" title.
    # v14: generic adjectives/adverbs and duplicate plurals from article titles
    # ("digital", "personal", "privately", "llms", "local", "ideas",
    # "component", "systems") that add no concept weight in this domain.
    "build",
    "building",
    "queryable",
    "agents",
    "powered",
    "maintain",
    "maintaining",
    "maintained",
    "you",
    "yourself",
    "base",
    "bases",
    "digital",
    "personal",
    "privately",
    "llms",
    "local",
    "ideas",
    "component",
    "components",
    "systems",
}

# Broad domain labels that are meaningful as standalone single-token concepts
# but create noise when jammed together into a multi-word phrase slug from a
# filename-derived title prefix (e.g. "plugin llm vault" -> plugin-llm-vault,
# "obsidian framework agents" -> obsidian-framework-agents). When building a
# title-prefix phrase, if ANY constituent token is phrase-weak the phrase is
# skipped so the individual tokens compete on their own merit instead.
_PHRASE_WEAK_TOKENS = {
    "plugin",
    "llm",
    "vault",
    "obsidian",
    "framework",
    "wiki",
    "data",
    "api",
    "systems",
    "knowledge",
}


def _valid_concept_term(term: str) -> bool:
    if not term:
        return False
    # CJK tokenize emits length-2 bigrams; Latin tokens stay 3+ via tokenize().
    # A uniform len<3 gate would discard every Chinese concept term.
    if re.search(r"[\u4e00-\u9fff]", term):
        if len(term) < 2:
            return False
    elif len(term) < 3:
        return False
    if term.isdigit():
        return False
    if term in STOP_WORDS or term in _CONCEPT_EXTRA_STOP_WORDS:
        return False
    if term in _GENERIC_SOURCE_TITLE_TERMS:
        return False
    if _CONCEPT_QUARTER_TAG_PATTERN.match(term):
        return False
    return True


def entry_concept_terms(entry: dict[str, Any], context: str, max_terms: int = 5) -> list[str]:
    scores: dict[str, int] = {}
    title_tokens = [t for t in tokenize(entry["title"]) if _valid_concept_term(t)]
    deduped_title_tokens = list(dict.fromkeys(title_tokens))
    phrase_tokens = deduped_title_tokens[:3]
    # v12: skip title-prefix phrases that are just filename-derived concatenations
    # of broad domain labels (e.g. "plugin llm vault"). If any constituent token
    # is phrase-weak, the phrase is noise; let the tokens compete individually.
    if (
        len(phrase_tokens) >= 2
        and not any(token in _PHRASE_WEAK_TOKENS for token in phrase_tokens)
        and not any(any("\u4e00" <= ch <= "\u9fff" for ch in token) for token in phrase_tokens)
    ):
        phrase = " ".join(phrase_tokens)
        scores[phrase] = scores.get(phrase, 0) + 8
    for token in deduped_title_tokens[:4]:
        scores[token] = scores.get(token, 0) + 5
    title_token_set = set(deduped_title_tokens)
    context_counts: dict[str, int] = {}
    for token in tokenize(context):
        if _valid_concept_term(token):
            context_counts[token] = context_counts.get(token, 0) + 1
    for token, count in context_counts.items():
        if token in title_token_set or count >= 2:
            scores[token] = scores.get(token, 0) + count
    ranked = sorted(scores.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [label for label, _score in ranked[:max_terms]]


def concept_source_input_signature(entry: dict[str, Any], context: str, manual_slugs: list[str]) -> str:
    payload = {
        "entry_id": str(entry.get("id") or ""),
        "title": str(entry.get("title") or ""),
        "source_sha256": str(entry.get("sha256") or ""),
        "context": context,
        "manual_slugs": sorted(str(slug) for slug in manual_slugs if str(slug)),
        "noise_floor_version": CONCEPT_NOISE_FLOOR_VERSION,
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def build_concept_records(
    root: Path,
    entries: list[dict[str, Any]],
    previews: dict[str, str],
    *,
    generated_at: str,
) -> tuple[list[dict[str, Any]], dict[str, list[str]], dict[str, Any]]:
    concept_map: dict[str, dict[str, Any]] = {}
    entry_terms: dict[str, list[str]] = {}
    previous_state = load_concept_build_state(root)
    previous_records = previous_state.get("entry_records", {})
    if not isinstance(previous_records, dict):
        previous_records = {}
    manual_links = _active_manual_source_concept_links(root)
    dirty_concept_source_ids: list[str] = []
    clean_concept_source_ids: list[str] = []
    entry_records: dict[str, dict[str, Any]] = {}
    for entry in entries:
        entry_id = str(entry["id"])
        context = source_summary_or_preview(root, entry, previews[entry["id"]])
        manual_slugs = sorted(manual_links.get(entry_id, set()))
        input_signature = concept_source_input_signature(entry, context, manual_slugs)
        previous_record = previous_records.get(entry_id, {})
        cached_terms = previous_record.get("terms", []) if isinstance(previous_record, dict) else []
        if (
            isinstance(previous_record, dict)
            and str(previous_record.get("input_signature") or "") == input_signature
            and isinstance(cached_terms, list)
        ):
            terms = [str(label) for label in cached_terms if str(label)]
            clean_concept_source_ids.append(entry_id)
        else:
            terms = entry_concept_terms(entry, context)
            dirty_concept_source_ids.append(entry_id)
        for manual_slug in manual_slugs:
            manual_label = manual_slug.replace("-", " ")
            if manual_label not in terms:
                terms.append(manual_label)
        entry_terms[entry_id] = terms
        entry_records[entry_id] = {
            "input_signature": input_signature,
            "terms": list(terms),
        }
        for label in terms:
            slug = concept_label_to_slug(label)
            record = concept_map.setdefault(
                slug,
                {
                    "slug": slug,
                    "label": label,
                    "title": concept_label_to_title(label),
                    "entries": [],
                    "score": 0,
                    "manual_source_ids": set(),
                },
            )
            record["entries"].append(entry)
            record["score"] += 1
            if slug in manual_links.get(entry_id, set()):
                record["manual_source_ids"].add(entry_id)

    ranked_records = sorted(concept_map.values(), key=lambda item: (-item["score"], item["title"].lower()))[:30]
    allowed = {record["slug"] for record in ranked_records}
    filtered_entry_terms: dict[str, list[str]] = {}
    for entry_id, labels in entry_terms.items():
        filtered = [label for label in labels if concept_label_to_slug(label) in allowed]
        filtered_entry_terms[entry_id] = filtered[:5]

    by_slug = {record["slug"]: record for record in ranked_records}
    for record in ranked_records:
        record["manual_source_ids"] = sorted(record.get("manual_source_ids", set()))
        related_counts: dict[str, int] = {}
        for entry in record["entries"]:
            for label in filtered_entry_terms[entry["id"]]:
                other_slug = concept_label_to_slug(label)
                if other_slug == record["slug"] or other_slug not in by_slug:
                    continue
                related_counts[other_slug] = related_counts.get(other_slug, 0) + 1
        related = sorted(related_counts.items(), key=lambda item: (-item[1], by_slug[item[0]]["title"].lower()))
        record["related_slugs"] = [slug for slug, _count in related[:6]]
        record["entry_ids"] = [entry["id"] for entry in record["entries"]]
        record["source_signature"] = concept_source_signature(record)
    state_document = {
        "version": 2,
        "generated_at": generated_at,
        "entry_records": entry_records,
    }
    return (
        ranked_records,
        filtered_entry_terms,
        {
            "state_document": state_document,
            "dirty_concept_source_ids": dirty_concept_source_ids,
            "clean_concept_source_ids": clean_concept_source_ids,
        },
    )


def concept_source_signature(record: dict[str, Any]) -> str:
    payload = {
        "slug": record["slug"],
        "entry_ids": sorted(record["entry_ids"]),
        "entry_sources": sorted(f"{entry['id']}:{entry['sha256']}" for entry in record["entries"]),
        "related_slugs": sorted(record.get("related_slugs", [])),
        "manual_source_ids": sorted(record.get("manual_source_ids", [])),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))



def concept_render_signature(root: Path, record: dict[str, Any]) -> str:
    source_contexts = [load_source_page_context(root, relative) for relative in concept_source_pages(record)]
    payload = {
        "render_schema_version": CONCEPT_RENDER_SCHEMA_VERSION,
        "title": record["title"],
        "source_signature": record["source_signature"],
        "source_pages": concept_source_pages(record),
        "source_contexts": [
            {
                "path": context.get("path", ""),
                "title": context.get("title", ""),
                "status": context.get("status", ""),
                "summary": context.get("summary", ""),
            }
            for context in source_contexts
        ],
    }
    return sha256_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))




def _concept_clue_from_context(context: dict[str, str]) -> str:
    summary = str(context.get("summary") or "")
    preview_bits: list[str] = []
    for line in summary.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Deterministic preview:"):
            preview_bits.append(stripped.removeprefix("- Deterministic preview:").strip())
    if preview_bits:
        return " ".join(preview_bits[:3])[:480]
    normalized = _normalize_summary_snippet(summary)
    lowered = normalized.lower()
    if lowered.startswith("pending llm summary") or not normalized:
        return ""
    return normalized[:480]


def _concept_material_excerpt_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for context in source_contexts[:3]:
        summary = str(context.get("summary") or "")
        title = str(context.get("title") or Path(str(context.get("path") or "source")).stem)
        for raw_line in summary.splitlines():
            stripped = raw_line.strip()
            if not stripped.startswith("- Deterministic preview:"):
                continue
            excerpt = stripped.removeprefix("- Deterministic preview:").strip()
            if excerpt:
                lines.append(f"- **{title}**：{excerpt[:320]}")
            if len(lines) >= 5:
                return lines
    return lines


def _concept_reading_guide_lines(root: Path, entry_ids: list[str]) -> list[str]:
    lines = ["- 概念页是机器记忆索引，不是原料正文副本；完整原文请看下方链接。"]
    for entry_id in entry_ids[:4]:
        source_path = root / "wiki" / "sources" / f"{entry_id}.md"
        if not source_path.is_file():
            continue
        text = source_path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)
        title = str(frontmatter.get("title") or entry_id)
        lines.append(f"- 来源页：`{title}`（`wiki/sources/{entry_id}.md`）")
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("- [[raw/"):
                lines.append(f"- 原料原文：`{stripped.removeprefix('- ').strip()}`")
                break
    return lines


def render_concept_summary_fallback(record: dict[str, Any], source_contexts: list[dict[str, str]]) -> str:
    source_links: list[str] = []
    for context in source_contexts[:4]:
        source_path = str(context.get("path") or "").strip()
        source_title = str(context.get("title") or "").strip() or Path(source_path or "source").stem
        if source_path:
            source_links.append(f"`{source_title}`（`{source_path}`）")
        else:
            source_links.append(f"`{source_title}`")
    source_count = len(record.get("entries", []))
    summary_lines = [
        f"- 当前概念汇总了 `{source_count}` 个 source page：{', '.join(source_links) or '暂无来源链接'}。",
    ]
    first_signal = next(
        (_concept_clue_from_context(context) for context in source_contexts if _concept_clue_from_context(context)),
        "",
    )
    if first_signal:
        extra_sources = max(len(source_contexts) - 1, 0)
        detail_suffix = f"；另外 `{extra_sources}` 个来源补充了边界或上下文。" if extra_sources else ""
        summary_lines.append(f"- 材料线索：{first_signal}{detail_suffix}")
    elif source_contexts:
        summary_lines.append("- 当前 source page 仍以原始材料为主，建议补充更明确的摘要后再抬高 hardness。")
    else:
        summary_lines.append("- 目前还没有可引用的 source page 摘要，先补材料再进行稳定归纳。")
    if len(source_contexts) <= 1:
        summary_lines.append("- 这还是单来源概念页；继续补充证据、冲突和例外后再升级为更硬的判断。")
    else:
        summary_lines.append("- 下一步优先收敛多来源共识、冲突点与适用边界，再把稳定结论沉淀到这里。")
    return "\n".join(summary_lines)



def concept_hardness_rank(value: Any) -> int:
    return {label: index for index, label in enumerate(CONCEPT_HARDNESS_LEVELS)}.get(
        normalize_concept_hardness(value),
        0,
    )



def render_concept_conflict_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    signals = detect_concept_conflict_signals(source_contexts)
    if not signals:
        return ["- 当前没有显式冲突信号。"]
    lines: list[str] = []
    for signal in signals[:6]:
        lines.append(f"- `{signal['label']}` | sources `{', '.join(signal.get('source_pages', [])) or 'none'}`")
    return lines


def render_concept_gap_lines(source_contexts: list[dict[str, str]]) -> list[str]:
    gaps = detect_concept_gap_signals(source_contexts)
    if not gaps:
        return ["- 当前没有显式证据缺口。"]
    lines: list[str] = []
    for gap in gaps[:6]:
        lines.append(
            f"- `{gap.get('kind', 'unknown')}` | source `{gap.get('path', 'n/a')}` | markers `{', '.join(gap.get('markers', [])) or 'none'}`"
        )
    return lines


def render_concept_causal_lines(
    causal_links: list[dict[str, str]],
    record_lookup: dict[str, dict[str, Any]],
) -> list[str]:
    if not causal_links:
        return ["- 当前没有显式因果关系。补充 `causal_links` frontmatter 可建立因果网络。"]
    lines: list[str] = []
    for link in causal_links:
        target = link["target"]
        relation = CAUSAL_RELATION_LABELS.get(link["relation"], link["relation"])
        evidence = link.get("evidence", "")
        target_record = record_lookup.get(target)
        if target_record:
            target_label = f"[{target_record['title']}](./{target}.md)"
        else:
            target_label = f"`{target}`"
        line = f"- {relation} {target_label}"
        if evidence:
            line += f" — {evidence}"
        lines.append(line)
    return lines


def render_concept_page(record: dict[str, Any], compiled_at: str, existing_page: str) -> str:
    existing_frontmatter = parse_frontmatter(existing_page)
    source_changed = existing_frontmatter.get("source_signature") not in ("", record["source_signature"])
    citations = existing_frontmatter.get("citations", []) if not source_changed else []
    if not isinstance(citations, list):
        citations = []
    confidence = existing_frontmatter.get("confidence", "medium") if not source_changed else "medium"
    if not isinstance(confidence, str) or not confidence:
        confidence = "medium"
    hardness = (
        normalize_concept_hardness(existing_frontmatter.get("hardness"), default="soft")
        if not source_changed
        else "soft"
    )
    causal_links = parse_causal_links(existing_frontmatter) if not source_changed else []
    source_pages = concept_source_pages(record)
    # Thin / noisy concepts stay soft even if an old medium/hard value lingered.
    if len(source_pages) <= 1:
        hardness = "soft"
    render_signature = str(record.get("render_signature") or concept_render_signature(record["root"], record))
    source_contexts = [
        load_source_page_context(record["root"], f"wiki/sources/{entry_id}.md") for entry_id in record["entry_ids"]
    ]
    summary_fallback = render_concept_summary_fallback(record, source_contexts)
    existing_summary = preserved_section(existing_page, "Summary", "").strip() if not source_changed else ""
    legacy_placeholder_summary = _concept_summary_matches_legacy_placeholder(existing_summary)
    if source_changed or not existing_summary or legacy_placeholder_summary:
        summary = summary_fallback
        if legacy_placeholder_summary and not source_changed:
            hardness = "soft"
    else:
        summary = existing_summary
    related_source_lines = [
        f"- `{entry['title']}`（`wiki/sources/{entry['id']}.md`）"
        for entry in sorted(record["entries"], key=lambda item: item["title"].lower())
    ] or ["- 暂无相关来源页。"]
    related_concepts = record.get("related_slugs", [])
    related_concept_lines = [
        f"- `{record_for_slug['title']}`（`wiki/concepts/{record_for_slug['slug']}.md`）"
        for record_for_slug in sorted(
            [record["record_lookup"][slug] for slug in related_concepts if slug in record["record_lookup"]],
            key=lambda item: item["title"].lower(),
        )
    ] or ["- 暂无相关概念。"]
    frontmatter_data: dict[str, Any] = {
        "id": f"concept-{record['slug']}",
        "kind": "concept",
        "status": "compiled",
        "title": record["title"],
        "source_pages": source_pages,
        "source_signature": record["source_signature"],
        "render_signature": render_signature,
        "citations": citations,
        "generated_by": "aiwiki-compile",
        "last_compiled_at": compiled_at,
        "confidence": confidence,
        "hardness": hardness,
    }
    if causal_links:
        frontmatter_data["causal_links"] = [
            f"{link['target']}|{link['relation']}|{link.get('evidence', '')}" for link in causal_links
        ]
    frontmatter = render_frontmatter(frontmatter_data)
    material_excerpt = _concept_material_excerpt_lines(source_contexts)
    reading_guide = _concept_reading_guide_lines(record["root"], record["entry_ids"])
    lines = [
        frontmatter,
        "",
        f"# {record['title']}",
        "",
        "## 摘要",
        summary,
        "",
        "## 阅读全文",
        *reading_guide,
        "",
        "## 材料摘录",
        *(material_excerpt or ["- 暂无自动摘录；请打开「阅读全文」中的来源页或原料文件。"]),
        "",
        "## 相关来源",
        *related_source_lines,
        "",
        "## 相关概念",
        *related_concept_lines,
        "",
        "## 因果网络",
        *render_concept_causal_lines(causal_links, record.get("record_lookup", {})),
        "",
        "## 冲突信号",
        *render_concept_conflict_lines(source_contexts),
        "",
        "## 证据缺口",
        *render_concept_gap_lines(source_contexts),
        "",
        "## 维护说明",
        "- 稳定结论写在这里，避免在多篇来源页重复同一综合。",
        "- 矛盾与缺失证据保持显式可见。",
    ]
    return "\n".join(lines) + "\n"


def render_sources_index(entries: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 来源索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 来源总数：`{len(entries)}`",
        "",
        "## 来源列表",
    ]
    if not entries:
        lines.append("- 还没有登记任何来源。")
    else:
        for entry in entries:
            lines.append(f"- [{entry['title']}](../sources/{entry['id']}.md) ({entry['kind']}, {entry['source_type']})")
    return "\n".join(lines) + "\n"


def render_concepts_index(concepts: list[dict[str, Any]], compiled_at: str) -> str:
    lines = [
        "# 概念索引",
        "",
        f"- 最近编译时间：`{compiled_at}`",
        f"- 概念页总数：`{len(concepts)}`",
        "",
        "## 概念列表",
    ]
    if not concepts:
        lines.append("- 还没有编译出概念页。")
    else:
        for concept in concepts:
            lines.append(
                f"- [{concept['title']}](../concepts/{concept['slug']}.md) ({len(concept['entries'])} source(s))"
            )
    return "\n".join(lines) + "\n"


def detect_concept_conflict_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_path = {
        context["path"]: str(context.get("summary") or "").lower()
        for context in source_contexts
        if context.get("status") == "ready" and context.get("summary")
    }
    signals: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for positive, negative, label in CONFLICT_SIGNAL_PAIRS:
        positive_hits = sorted(path for path, summary in by_path.items() if positive in summary)
        negative_hits = sorted(path for path, summary in by_path.items() if negative in summary)
        if not positive_hits or not negative_hits:
            continue
        touched_paths = sorted(set(positive_hits) | set(negative_hits))
        if len(touched_paths) < 2 or label in seen_labels:
            continue
        seen_labels.add(label)
        signals.append(
            {
                "label": label,
                "positive": positive,
                "negative": negative,
                "source_pages": touched_paths,
                "source_titles": [
                    next(
                        (
                            str(context.get("title") or path)
                            for context in source_contexts
                            if context.get("path") == path
                        ),
                        path,
                    )
                    for path in touched_paths
                ],
            }
        )
    return signals


def detect_concept_gap_signals(source_contexts: list[dict[str, str]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for context in source_contexts:
        path = str(context.get("path") or "")
        title = str(context.get("title") or path)
        status = str(context.get("status") or "")
        summary = str(context.get("summary") or "").lower()
        if status == "missing":
            gaps.append(
                {"kind": "missing-source-page", "path": path, "title": title, "markers": ["missing-source-page"]}
            )
            continue
        if status == "placeholder":
            gaps.append(
                {"kind": "pending-source-summary", "path": path, "title": title, "markers": ["pending-source-summary"]}
            )
            continue
        markers = sorted({marker for marker in EVIDENCE_GAP_MARKERS if marker in summary})
        if markers:
            gaps.append({"kind": "evidence-gap", "path": path, "title": title, "markers": markers})
    return gaps


def _active_manual_source_concept_links(root: Path) -> dict[str, set[str]]:
    from .io import active_manual_source_concept_links

    return active_manual_source_concept_links(root)



