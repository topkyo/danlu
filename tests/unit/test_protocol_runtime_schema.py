from __future__ import annotations

import pytest

from aiwiki.app_protocol import default_protocol_runtime_schema
from aiwiki.protocol.runtime_schema import merge_protocol_runtime_schema


def test_merge_protocol_runtime_schema_keeps_defaults_and_normalizes_lists():
    default_schema = default_protocol_runtime_schema("research")

    merged = merge_protocol_runtime_schema(
        payload={
            "version": 2,
            "slug": "research",
            "title": "Research Runtime",
            "query_routes": {
                "default_strategy": "source-first",
                "strategy_order": ["source-first", "graph-walk"],
                "source_markers": [" paper ", "benchmark"],
                "graph_markers": ["causal"],
            },
            "review_windows": {"decision:proposed": [1, 3]},
        },
        default_schema=default_schema,
        slug="research",
        path_ref="schema/protocols/research/runtime.yaml",
    )

    assert merged["version"] == 2
    assert merged["slug"] == "research"
    assert merged["title"] == "Research Runtime"
    assert merged["summary"] == default_schema["summary"]
    assert merged["query_routes"] == {
        "default_strategy": "source-first",
        "strategy_order": ["source-first", "graph-walk"],
        "source_markers": ["paper", "benchmark"],
        "graph_markers": ["causal"],
    }
    assert merged["review_windows"] == {"decision:proposed": [1, 3]}
    assert merged["execution_policy"] == default_schema["execution_policy"]


def test_merge_protocol_runtime_schema_rejects_unknown_and_invalid_values():
    default_schema = default_protocol_runtime_schema("research")

    with pytest.raises(RuntimeError, match="Unsupported top-level keys: extra"):
        merge_protocol_runtime_schema(
            payload={"extra": True},
            default_schema=default_schema,
            slug="research",
            path_ref="schema/protocols/research/runtime.yaml",
        )

    with pytest.raises(RuntimeError, match="`slug` must match the directory name `research`"):
        merge_protocol_runtime_schema(
            payload={"slug": "ops"},
            default_schema=default_schema,
            slug="research",
            path_ref="schema/protocols/research/runtime.yaml",
        )

    with pytest.raises(RuntimeError, match="query_routes.strategy_order"):
        merge_protocol_runtime_schema(
            payload={"query_routes": {"strategy_order": "source-first"}},
            default_schema=default_schema,
            slug="research",
            path_ref="schema/protocols/research/runtime.yaml",
        )

    with pytest.raises(RuntimeError, match="review_windows.decision:proposed"):
        merge_protocol_runtime_schema(
            payload={"review_windows": {"decision:proposed": [1, -1]}},
            default_schema=default_schema,
            slug="research",
            path_ref="schema/protocols/research/runtime.yaml",
        )
