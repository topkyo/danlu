"""Protocol runtime schema validation helpers extracted from app_protocol."""

from __future__ import annotations

from typing import Any, cast

from ..app_types import ProtocolRuntimeSchema

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
            raise protocol_runtime_schema_error(path_ref, f"`execution_policy.accepted_rules.{rule_id}` must be an object.")
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
