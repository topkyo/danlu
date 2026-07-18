"""Protocol domain TypedDict contracts."""

from __future__ import annotations

from typing import TypedDict


class ProtocolDescriptorPaths(TypedDict, total=False):
    index: str
    taxonomy: str
    decision: str
    judgment: str
    review: str
    nightly: str
    query: str


class ProtocolDescriptor(TypedDict, total=False):
    slug: str
    title: str
    summary: str
    paths: ProtocolDescriptorPaths


class ProtocolState(TypedDict, total=False):
    version: int
    active_protocol: str
    available_protocols: list[str]
    protocols: list[ProtocolDescriptor]
    state_path: str


class ProtocolRuntimeRule(TypedDict, total=False):
    capabilities: list[str]
    decision: str
    execution_band: str
    execution_policy: str
    policy_summary: str


class ProtocolRuntimeExecutionPolicy(TypedDict, total=False):
    accepted_rules: dict[str, ProtocolRuntimeRule]


class ProtocolRuntimeQueryRoutes(TypedDict, total=False):
    default_strategy: str
    strategy_order: list[str]
    source_markers: list[str]
    graph_markers: list[str]


class ProtocolRuntimeSchema(TypedDict, total=False):
    version: int
    slug: str
    title: str
    summary: str
    review_windows: dict[str, list[int]]
    output_guidance: dict[str, list[str]]
    execution_policy: ProtocolRuntimeExecutionPolicy
    query_routes: ProtocolRuntimeQueryRoutes
