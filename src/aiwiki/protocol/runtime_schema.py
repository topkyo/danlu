"""Protocol runtime schema validation and I/O helpers extracted from app_protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ..state.constants import DEFAULT_PROTOCOL
from ..utils.io import atomic_write_text
from ..utils.path import relative_path
from .descriptors import protocol_title
from .library import PROTOCOL_LIBRARY
from .runtime_config import (
    PROTOCOL_EXECUTION_POLICY_RULES,
    PROTOCOL_OUTPUT_GUIDANCE,
    PROTOCOL_PROMOTION_PREFIXES,
    PROTOCOL_QUERY_ROUTE_CONFIG,
    PROTOCOL_REVIEW_WINDOWS,
)
from .types import ProtocolRuntimeSchema

PROTOCOL_RUNTIME_ALLOWED_KEYS = {
    "version",
    "slug",
    "title",
    "summary",
    "review_windows",
    "output_guidance",
    "execution_policy",
    "query_routes",
}


def protocol_runtime_schema_error(path_ref: str, message: str) -> RuntimeError:
    return RuntimeError(f"Invalid protocol runtime schema `{path_ref}`: {message}")


def validate_protocol_runtime_string_list(path_ref: str, field: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        raise protocol_runtime_schema_error(path_ref, f"`{field}` must be a list of strings.")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise protocol_runtime_schema_error(path_ref, f"`{field}[{index}]` must be a non-empty string.")
        normalized.append(item.strip())
    return normalized


def validate_protocol_runtime_review_windows(path_ref: str, value: Any) -> dict[str, list[int]]:
    if not isinstance(value, dict):
        raise protocol_runtime_schema_error(path_ref, "`review_windows` must be an object.")
    review_windows: dict[str, list[int]] = {}
    for key, window in value.items():
        if not isinstance(key, str) or not key.strip():
            raise protocol_runtime_schema_error(path_ref, "`review_windows` keys must be non-empty strings.")
        if not isinstance(window, list) or len(window) != 2:
            raise protocol_runtime_schema_error(path_ref, f"`review_windows.{key}` must contain exactly two integers.")
        if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in window):
            raise protocol_runtime_schema_error(path_ref, f"`review_windows.{key}` must contain non-negative integers.")
        review_windows[key.strip()] = [int(window[0]), int(window[1])]
    return review_windows


def validate_protocol_runtime_output_guidance(path_ref: str, value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise protocol_runtime_schema_error(path_ref, "`output_guidance` must be an object.")
    return {
        key.strip(): validate_protocol_runtime_string_list(path_ref, f"output_guidance.{key}", lines)
        for key, lines in value.items()
        if isinstance(key, str) and key.strip()
    }


def validate_protocol_runtime_execution_policy(path_ref: str, value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise protocol_runtime_schema_error(path_ref, "`execution_policy` must be an object.")
    accepted_rules = value.get("accepted_rules")
    if not isinstance(accepted_rules, dict):
        raise protocol_runtime_schema_error(path_ref, "`execution_policy.accepted_rules` must be an object.")
    normalized_rules: dict[str, dict[str, Any]] = {}
    for rule_id, rule_payload in accepted_rules.items():
        if not isinstance(rule_id, str) or not rule_id.strip():
            raise protocol_runtime_schema_error(path_ref, "Execution policy rule ids must be non-empty strings.")
        if not isinstance(rule_payload, dict):
            raise protocol_runtime_schema_error(
                path_ref, f"`execution_policy.accepted_rules.{rule_id}` must be an object."
            )
        normalized_rule = dict(rule_payload)
        if "capabilities" in normalized_rule:
            normalized_rule["capabilities"] = validate_protocol_runtime_string_list(
                path_ref,
                f"execution_policy.accepted_rules.{rule_id}.capabilities",
                normalized_rule["capabilities"],
            )
        for field in ("decision", "execution_band", "execution_policy", "policy_summary"):
            if field in normalized_rule and not isinstance(normalized_rule[field], str):
                raise protocol_runtime_schema_error(
                    path_ref,
                    f"`execution_policy.accepted_rules.{rule_id}.{field}` must be a string.",
                )
        normalized_rules[rule_id.strip()] = normalized_rule
    return {"accepted_rules": normalized_rules}


def validate_protocol_runtime_query_routes(
    path_ref: str,
    value: Any,
    default_routes: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise protocol_runtime_schema_error(path_ref, "`query_routes` must be an object.")
    default_strategy = value.get("default_strategy", default_routes.get("default_strategy", "concept-first"))
    if not isinstance(default_strategy, str) or not default_strategy.strip():
        raise protocol_runtime_schema_error(path_ref, "`query_routes.default_strategy` must be a non-empty string.")
    return {
        "default_strategy": default_strategy.strip(),
        "strategy_order": validate_protocol_runtime_string_list(
            path_ref,
            "query_routes.strategy_order",
            value.get("strategy_order", default_routes.get("strategy_order", [])),
        ),
        "source_markers": validate_protocol_runtime_string_list(
            path_ref,
            "query_routes.source_markers",
            value.get("source_markers", default_routes.get("source_markers", [])),
        ),
        "graph_markers": validate_protocol_runtime_string_list(
            path_ref,
            "query_routes.graph_markers",
            value.get("graph_markers", default_routes.get("graph_markers", [])),
        ),
    }


def merge_protocol_runtime_schema(
    *,
    payload: dict[str, Any],
    default_schema: ProtocolRuntimeSchema,
    slug: str,
    path_ref: str,
) -> ProtocolRuntimeSchema:
    unknown_keys = sorted(set(payload) - PROTOCOL_RUNTIME_ALLOWED_KEYS)
    if unknown_keys:
        raise protocol_runtime_schema_error(path_ref, f"Unsupported top-level keys: {', '.join(unknown_keys)}.")
    merged: ProtocolRuntimeSchema = cast(ProtocolRuntimeSchema, dict(default_schema))
    if "version" in payload:
        version = payload["version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise protocol_runtime_schema_error(path_ref, "`version` must be an integer.")
        merged["version"] = int(version)
    if "slug" in payload:
        payload_slug = payload["slug"]
        if not isinstance(payload_slug, str) or not payload_slug.strip():
            raise protocol_runtime_schema_error(path_ref, "`slug` must be a non-empty string.")
        if payload_slug != slug:
            raise protocol_runtime_schema_error(path_ref, f"`slug` must match the directory name `{slug}`.")
        merged["slug"] = payload_slug
    for field in ("title", "summary"):
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str):
            raise protocol_runtime_schema_error(path_ref, f"`{field}` must be a string.")
        merged[field] = value
    if "output_guidance" in payload:
        merged["output_guidance"] = validate_protocol_runtime_output_guidance(path_ref, payload["output_guidance"])
    if "execution_policy" in payload:
        merged["execution_policy"] = cast(
            Any,
            validate_protocol_runtime_execution_policy(path_ref, payload["execution_policy"]),
        )
    if "query_routes" in payload:
        merged["query_routes"] = cast(
            Any,
            validate_protocol_runtime_query_routes(
                path_ref,
                payload["query_routes"],
                dict(default_schema.get("query_routes", {})),
            ),
        )
    if "review_windows" in payload:
        merged["review_windows"] = validate_protocol_runtime_review_windows(path_ref, payload["review_windows"])
    return merged


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
