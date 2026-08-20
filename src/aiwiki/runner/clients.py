"""LLM client lifecycle helpers for runner workflows."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from aiwiki.config import LLMConfig
from aiwiki.llm import (
    create_backend_client,
    probe_available_backends,
    probe_backend,
)
from aiwiki.runner.interfaces import SupportsComplete


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
        result["probe"] = next(
            (probe for probe in probes if probe.get("backend") == config.backend), probes[0] if probes else None
        )
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
    return _client_model_name(client)


def _client_backend_requested(client: SupportsComplete) -> str:
    config = getattr(client, "config", None)
    requested = getattr(config, "backend_requested", None) or getattr(config, "backend", None)
    return str(requested or "")


def _client_backend_name(client: SupportsComplete) -> str:
    config = getattr(client, "config", None)
    backend = getattr(config, "backend", None)
    return str(backend or "")


def _append_fallback_stage(stages: list[str], stage: str) -> None:
    if stage and stage not in stages:
        stages.append(stage)


def _fallback_stage_label(stages: list[str]) -> str:
    return "+".join(stage for stage in stages if stage)
