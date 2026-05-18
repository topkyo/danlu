"""LLM client lifecycle helpers for runner workflows."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from aiwiki.config import LLMConfig
from aiwiki.llm import (
    advance_client_model,
    create_backend_client,
    probe_available_backends,
    probe_backend,
)
from aiwiki.runner.interfaces import SupportsComplete

FALLBACK_STAGE_BACKEND_FAILOVER = "backend-failover"
FALLBACK_STAGE_MODEL_CHAIN = "model-chain"


def llm_status() -> dict[str, Any]:
    return LLMConfig.status_from_env()


def llm_probe(root: Path, probe_all: bool = False, timeout_seconds: int = 20) -> dict[str, Any]:
    status = llm_status()
    result = dict(status)
    result["probe_timeout_seconds"] = timeout_seconds
    if not status.get("configured"):
        result["probe"] = None
        result["probes"] = []
        return result
    config = LLMConfig.from_env()
    if probe_all:
        probes = probe_available_backends(config, root, timeout_seconds=timeout_seconds)
        result["probes"] = probes
        result["probe"] = next((probe for probe in probes if probe.get("backend") == config.backend), probes[0] if probes else None)
        return result
    result["probe"] = probe_backend(config, root, timeout_seconds=timeout_seconds)
    result["probes"] = []
    return result


def create_client(root: Path, timeout_seconds: int | None = None) -> SupportsComplete:
    config = LLMConfig.from_env()
    if timeout_seconds is not None:
        config = replace(config, timeout_seconds=timeout_seconds)
    return create_backend_client(config, root)


def _client_model_name(client: SupportsComplete) -> str:
    config = getattr(client, "config", None)
    model = getattr(config, "model", None)
    return str(model or "")


def _client_selected_model_name(client: SupportsComplete) -> str:
    configs = getattr(client, "client_configs", None)
    if isinstance(configs, list) and configs:
        return str(getattr(configs[0], "model", "") or "")
    primary_config = getattr(client, "primary_config", None)
    if primary_config is not None:
        return str(getattr(primary_config, "model", "") or "")
    return _client_model_name(client)


def _client_backend_requested(client: SupportsComplete) -> str:
    for config in (getattr(client, "primary_config", None), getattr(client, "config", None)):
        if config is None:
            continue
        requested = getattr(config, "backend_requested", None) or getattr(config, "backend", None)
        if requested:
            return str(requested)
    return ""


def _client_backend_name(client: SupportsComplete) -> str:
    for config in (getattr(client, "config", None), getattr(client, "primary_config", None)):
        if config is None:
            continue
        backend = getattr(config, "backend", None)
        if backend:
            return str(backend)
    return ""


def _fallback_stage_for_client_transition(client: SupportsComplete, *, before_backend: str) -> str:
    after_backend = _client_backend_name(client)
    if before_backend and after_backend and before_backend != after_backend:
        return FALLBACK_STAGE_BACKEND_FAILOVER
    return FALLBACK_STAGE_MODEL_CHAIN


def _append_fallback_stage(stages: list[str], stage: str) -> None:
    if stage and stage not in stages:
        stages.append(stage)


def _fallback_stage_label(stages: list[str]) -> str:
    return "+".join(stage for stage in stages if stage)


def _fallback_to_next_model(client: SupportsComplete, operation: str, exc: Exception) -> bool:
    current_backend = _client_backend_name(client)
    current_model = _client_model_name(client)
    if not advance_client_model(client):
        return False
    next_backend = _client_backend_name(client)
    next_model = _client_model_name(client)
    logging.getLogger("aiwiki").warning(
        "%s failed with %s/%s: %s; retrying with %s/%s",
        operation,
        current_backend or "(default)",
        current_model or "(default)",
        exc,
        next_backend or "(default)",
        next_model or "(default)",
    )
    return True


def _fallback_to_next_model_with_stage(client: SupportsComplete, operation: str, exc: Exception) -> str:
    before_backend = _client_backend_name(client)
    if not _fallback_to_next_model(client, operation, exc):
        return ""
    return _fallback_stage_for_client_transition(client, before_backend=before_backend)
