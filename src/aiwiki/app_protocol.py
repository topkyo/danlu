"""Protocol/runtime base extracted from aiwiki.app.

OWNER STATUS: legacy owner. CENTRAL HUB - extra caution required.
New large logic blocks should be extracted to a dedicated subpackage
(e.g. `aiwiki.protocol.*`) rather than added here. See AGENTS.md migration
policy. Do not refactor this file casually: it is depended on by most other
modules and circular-import risk is high.
"""

from __future__ import annotations

import fcntl
import functools
import hashlib
import html
import json
import os
import re
import shutil
import threading
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from .app_state_paths import manifest_path
from .app_types import ProtocolDescriptor, ProtocolRuntimeSchema, ProtocolState
from .config import LLMConfig
from .protocol.descriptors import (
    AGENT_PACK_LIBRARY,
    protocol_summary,
    protocol_title,
    render_protocol_library_index,
    render_protocol_overview,
    render_protocol_section,
)
from .protocol.library import (
    PROTOCOL_JUDGMENT_EXTRA_FIELDS,
    PROTOCOL_LIBRARY,
    protocol_judgment_extra_fields,
)
from .protocol.runtime_config import (
    ACTION_STATUSES,
    ACTIVE_CORPUS_STATUSES,
    ACTIVE_CORPUS_TTL,
    AGING_WINDOWS_DAYS,
    ARCHIVE_CANDIDATE_STATUSES,
    ARCHIVE_QUERY_STALE_AFTER,
    AUTO_PROMOTION_FORMATS,
    AUTO_PROMOTION_MIN_OCCURRENCES,
    CAUSAL_RELATION_TYPES,
    CONCEPT_HARDNESS_LEVELS,
    CONFLICT_SIGNAL_PAIRS,
    DECISION_QUERY_MARKERS,
    DECISION_STATUSES,
    EVIDENCE_GAP_MARKERS,
    EXECUTION_BAND_LABELS,
    JUDGMENT_QUERY_MARKERS,
    JUDGMENT_STATUSES,
    LOW_RISK_APPLYABLE_ACTION_KINDS,
    PENDING_ACTION_STATUSES,
    PENDING_DECISION_REVIEW_STATUSES,
    PENDING_JUDGMENT_REVIEW_STATUSES,
    PENDING_REWRITE_PROPOSAL_STATUSES,
    PROTOCOL_ACTION_KIND_WEIGHTS,
    PROTOCOL_CLASSIFICATION_MARKERS,
    PROTOCOL_ELIXIR_REVIEW_DAYS,
    PROTOCOL_EXECUTION_POLICY_RULES,
    PROTOCOL_FOCUS_KEYWORDS,
    PROTOCOL_OUTPUT_GUIDANCE,
    PROTOCOL_PROMOTION_PREFIXES,
    PROTOCOL_QUERY_ROUTE_CONFIG,
    PROTOCOL_REVIEW_WINDOWS,
    RESOLVABLE_MONITOR_ACTION_KINDS,
    REWRITE_PROPOSAL_STATUSES,
)
from .protocol.runtime_schema import merge_protocol_runtime_schema, protocol_runtime_schema_error
from .protocol.templates import (
    CURATED_ASSET_SECTION_ORDER,
    DEFAULT_DASHBOARD_FILES,
    DEFAULT_SCHEMA_FILES,
    LAYOUT_DIRS,
    MANAGED_DASHBOARD_TEMPLATE_FILES,
    PROTOCOL_SECTION_FILES,
    PROTOCOL_SECTION_TITLES,
)
from .state.constants import DEFAULT_PROTOCOL
from .state.io import load_json_document_strict
from .utils.io import atomic_write_text
from .utils.path import relative_path
from .utils.time import parse_iso_datetime


def ensure_layout(root: Path) -> None:
    for relative in LAYOUT_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)
    ensure_runtime_schema(root)
    ensure_protocol_scaffold(root)
    ensure_runtime_dashboards(root)
    from .vault_obsidian_graph import sync_obsidian_native_graph_config

    sync_obsidian_native_graph_config(root)


def ensure_runtime_schema(root: Path) -> None:
    for relative, content in DEFAULT_SCHEMA_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def ensure_runtime_dashboards(root: Path, *, overwrite: bool = False) -> None:
    for relative, content in DEFAULT_DASHBOARD_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not path.exists():
            path.write_text(content, encoding="utf-8")


def protocol_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "protocol.json"


def default_protocol_state() -> ProtocolState:
    return {"version": 1, "active_protocol": DEFAULT_PROTOCOL}


def protocol_runtime_schema_path(root: Path, slug: str) -> Path:
    return root / "schema" / "protocols" / slug / "runtime.yaml"


def default_protocol_runtime_schema(slug: str) -> ProtocolRuntimeSchema:
    metadata = PROTOCOL_LIBRARY[slug]
    review_windows = {
        f"{kind}:{status}": [window[0], window[1]]
        for (kind, status), window in PROTOCOL_REVIEW_WINDOWS.get(slug, {}).items()
    }
    execution_policy_rules = dict(PROTOCOL_EXECUTION_POLICY_RULES.get(DEFAULT_PROTOCOL, {}))
    execution_policy_rules.update(PROTOCOL_EXECUTION_POLICY_RULES.get(slug, {}))
    route_config = dict(PROTOCOL_QUERY_ROUTE_CONFIG.get(DEFAULT_PROTOCOL, {}))
    route_config.update(PROTOCOL_QUERY_ROUTE_CONFIG.get(slug, {}))
    return cast(
        ProtocolRuntimeSchema,
        {
            "version": 1,
            "slug": slug,
            "title": metadata["title"],
            "summary": metadata["summary"],
            "review_windows": review_windows,
            "output_guidance": {
                output_format: list(lines)
                for output_format, lines in PROTOCOL_OUTPUT_GUIDANCE.get(
                    slug, PROTOCOL_OUTPUT_GUIDANCE[DEFAULT_PROTOCOL]
                ).items()
            },
            "execution_policy": {
                "accepted_rules": execution_policy_rules,
            },
            "query_routes": {
                "default_strategy": str(route_config.get("default_strategy") or "concept-first"),
                "strategy_order": list(
                    route_config.get("strategy_order") or ["concept-first", "graph-walk", "source-first"]
                ),
                "source_markers": list(route_config.get("source_markers") or []),
                "graph_markers": list(route_config.get("graph_markers") or []),
            },
        },
    )


def load_protocol_runtime_schema(root: Path, slug: str) -> ProtocolRuntimeSchema:
    path = protocol_runtime_schema_path(root, slug)
    default_schema = default_protocol_runtime_schema(slug)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(default_schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return default_schema
    path_ref = relative_path(root, path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise protocol_runtime_schema_error(
            path_ref,
            f"expected JSON-compatible YAML/JSON ({exc.msg} at line {exc.lineno} column {exc.colno}).",
        ) from exc
    if not isinstance(payload, dict):
        raise protocol_runtime_schema_error(path_ref, "Top-level payload must be an object.")
    return merge_protocol_runtime_schema(
        payload=payload,
        default_schema=default_schema,
        slug=slug,
        path_ref=path_ref,
    )


def ensure_protocol_scaffold(root: Path) -> None:
    base = root / "schema" / "protocols"
    base.mkdir(parents=True, exist_ok=True)
    index_path = base / "index.md"
    if not index_path.exists():
        index_path.write_text(render_protocol_library_index(), encoding="utf-8")
    slug = DEFAULT_PROTOCOL
    runtime_schema = protocol_runtime_schema_path(root, slug)
    runtime_schema.parent.mkdir(parents=True, exist_ok=True)
    if not runtime_schema.exists():
        atomic_write_text(
            runtime_schema,
            json.dumps(default_protocol_runtime_schema(slug), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    overview = base / slug / "index.md"
    overview.parent.mkdir(parents=True, exist_ok=True)
    if not overview.exists():
        overview.write_text(render_protocol_overview(slug), encoding="utf-8")
    for section in PROTOCOL_SECTION_FILES:
        path = base / slug / f"{section}.md"
        if not path.exists():
            path.write_text(render_protocol_section(slug, section), encoding="utf-8")
    state = protocol_state_path(root)
    if not state.exists():
        atomic_write_text(state, json.dumps(default_protocol_state(), indent=2, sort_keys=True) + "\n")


def available_protocols(root: Path) -> list[str]:
    ensure_protocol_scaffold(root)
    return [DEFAULT_PROTOCOL]


def protocol_descriptor(root: Path, slug: str) -> ProtocolDescriptor:
    base = root / "schema" / "protocols" / slug
    return cast(
        ProtocolDescriptor,
        {
            "slug": slug,
            "title": protocol_title(slug),
            "summary": protocol_summary(slug),
            "paths": {
                "index": relative_path(root, base / "index.md"),
                **{section: relative_path(root, base / f"{section}.md") for section in PROTOCOL_SECTION_FILES},
            },
        },
    )


def load_protocol_state(root: Path) -> ProtocolState:
    ensure_protocol_scaffold(root)
    path = protocol_state_path(root)
    state = load_json_document_strict(path) if path.exists() else default_protocol_state()
    available = available_protocols(root)
    active = str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    if active != DEFAULT_PROTOCOL:
        active = DEFAULT_PROTOCOL
    normalized = {"version": 1, "active_protocol": active}
    if state != normalized:
        atomic_write_text(path, json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    return cast(
        ProtocolState,
        {
            **normalized,
            "available_protocols": available,
            "protocols": [protocol_descriptor(root, slug) for slug in available],
            "state_path": relative_path(root, path),
        },
    )


def resolve_protocol(root: Path, protocol: str | None = None) -> str:
    state = load_protocol_state(root)
    if protocol is None:
        return str(state.get("active_protocol") or DEFAULT_PROTOCOL)
    candidate = protocol.strip().lower()
    if candidate != DEFAULT_PROTOCOL:
        raise ValueError(f"Unknown protocol: {protocol}. Only '{DEFAULT_PROTOCOL}' is supported.")
    return candidate


def protocol_runtime_summary(slug: str) -> list[str]:
    windows = PROTOCOL_REVIEW_WINDOWS.get(slug, {})
    lines = [f"- 默认协议：`{slug}` ({protocol_title(slug)})"]
    if not windows:
        lines.append("- Review window：沿通用默认窗口。")
    else:
        lines.append("- Review window overrides:")
        for (kind, status), (revisit_days, escalate_days) in sorted(windows.items()):
            lines.append(f"  - `{kind}:{status}` -> revisit `{revisit_days}`d / escalate `{escalate_days}`d")
    prefixes = PROTOCOL_PROMOTION_PREFIXES.get(slug, PROTOCOL_PROMOTION_PREFIXES[DEFAULT_PROTOCOL])
    lines.append(f"- Auto-promotion 标题前缀：decision `{prefixes['decision']}` / judgment `{prefixes['judgment']}`")
    review_focus = PROTOCOL_LIBRARY.get(slug, {}).get("review", [])
    nightly_focus = PROTOCOL_LIBRARY.get(slug, {}).get("nightly", [])
    if review_focus:
        lines.append(f"- Review focus：`{' / '.join(review_focus[:2])}`")
    if nightly_focus:
        lines.append(f"- Nightly focus：`{' / '.join(nightly_focus[:2])}`")
    return lines


def protocol_focus_score(protocol: str, text: str) -> int:
    normalized = " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()))
    return sum(1 for marker in PROTOCOL_FOCUS_KEYWORDS.get(protocol, ()) if marker in normalized)


def page_focus_score(active_protocol: str, page: dict[str, str]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(page.get("title") or ""),
                str(page.get("path") or ""),
                str(page.get("status") or ""),
            ]
        ),
    )
    if str(page.get("protocol") or "") == active_protocol:
        score += 10
    return score


def action_focus_score(active_protocol: str, action: dict[str, Any]) -> int:
    score = protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(action.get("title") or ""),
                str(action.get("reason") or ""),
                str(action.get("primary_path") or ""),
                str(action.get("secondary_path") or ""),
            ]
        ),
    )
    score += PROTOCOL_ACTION_KIND_WEIGHTS.get(active_protocol, {}).get(str(action.get("kind") or ""), 0)
    return score


def entry_focus_score(active_protocol: str, entry: dict[str, Any], summary_or_preview: str) -> int:
    return protocol_focus_score(
        active_protocol,
        " ".join(
            [
                str(entry.get("title") or ""),
                str(entry.get("source_type") or ""),
                summary_or_preview,
            ]
        ),
    )


def concept_focus_score(active_protocol: str, title: str, content: str) -> int:
    return protocol_focus_score(active_protocol, f"{title}\n{content}")


def protocol_output_guidance(root: Path, protocol: str, output_format: str) -> tuple[str, ...]:
    default_guidance = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("output_guidance", {})
    protocol_guidance = load_protocol_runtime_schema(root, protocol).get("output_guidance", default_guidance)
    if not isinstance(default_guidance, dict):
        default_guidance = {}
    if not isinstance(protocol_guidance, dict):
        protocol_guidance = default_guidance
    return tuple(protocol_guidance.get(output_format, default_guidance.get(output_format, ())))


def protocol_execution_policy_rule(root: Path, protocol: str, action_kind: str) -> dict[str, Any]:
    default_rules = (
        default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("execution_policy", {}).get("accepted_rules", {})
    )
    protocol_rules = load_protocol_runtime_schema(root, protocol).get("execution_policy", {}).get("accepted_rules", {})
    rule = protocol_rules.get(action_kind) or default_rules.get(action_kind) or {}
    if not isinstance(rule, dict):
        return {}
    return {
        "decision": str(rule.get("decision") or "review"),
        "execution_policy": str(rule.get("execution_policy") or "manual-repair"),
        "execution_band": str(rule.get("execution_band") or "manual-repair"),
        "capabilities": [str(item) for item in rule.get("capabilities", []) if isinstance(item, str) and item],
        "policy_summary": str(rule.get("policy_summary") or ""),
    }


def protocol_query_route_config(root: Path, protocol: str) -> dict[str, Any]:
    default_config = default_protocol_runtime_schema(DEFAULT_PROTOCOL).get("query_routes", {})
    protocol_config = load_protocol_runtime_schema(root, protocol).get("query_routes", default_config)
    if not isinstance(default_config, dict):
        default_config = {}
    if not isinstance(protocol_config, dict):
        protocol_config = default_config
    return {
        "default_strategy": str(
            protocol_config.get("default_strategy") or default_config.get("default_strategy") or "concept-first"
        ),
        "strategy_order": [
            str(item)
            for item in protocol_config.get("strategy_order", default_config.get("strategy_order", []))
            if isinstance(item, str) and item
        ],
        "source_markers": [
            str(item)
            for item in protocol_config.get("source_markers", default_config.get("source_markers", []))
            if isinstance(item, str) and item
        ],
        "graph_markers": [
            str(item)
            for item in protocol_config.get("graph_markers", default_config.get("graph_markers", []))
            if isinstance(item, str) and item
        ],
    }


def protocol_paths(root: Path, protocol: str | None = None) -> list[str]:
    slug = resolve_protocol(root, protocol)
    base = root / "schema" / "protocols" / slug
    paths = [relative_path(root, base / "index.md")]
    paths.extend(relative_path(root, base / f"{section}.md") for section in PROTOCOL_SECTION_FILES)
    return paths


def schedule_review_windows(
    kind: str,
    status: str,
    base_timestamp: str,
    *,
    protocol: str = DEFAULT_PROTOCOL,
    root: Path | None = None,
) -> tuple[str, str]:
    windows = AGING_WINDOWS_DAYS.get((kind, status))
    if root is not None:
        runtime_schema = load_protocol_runtime_schema(root, protocol)
        review_windows = runtime_schema.get("review_windows", {}) if isinstance(runtime_schema, dict) else {}
        candidate = review_windows.get(f"{kind}:{status}") if isinstance(review_windows, dict) else None
        if isinstance(candidate, list) and len(candidate) == 2 and all(isinstance(item, int) for item in candidate):
            windows = (candidate[0], candidate[1])
    elif protocol in PROTOCOL_REVIEW_WINDOWS:
        windows = PROTOCOL_REVIEW_WINDOWS.get(protocol, {}).get((kind, status), windows)
    if not windows:
        return "", ""
    base = parse_iso_datetime(base_timestamp) or datetime.now(timezone.utc)
    revisit_days, escalate_days = windows
    revisit_after = (base + timedelta(days=revisit_days)).replace(microsecond=0).isoformat()
    escalate_after = (base + timedelta(days=escalate_days)).replace(microsecond=0).isoformat()
    return revisit_after, escalate_after


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    ensure_layout(root)
    path = manifest_path(root)
    atomic_write_text(path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
