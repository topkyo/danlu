"""Backend preflight checks for run-compile / run-ask entry points."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from aiwiki.config import LLMConfig
from aiwiki.llm import probe_backend

_LOGGER = logging.getLogger("aiwiki")
_REQUIRE_COMPATIBLE_ENV = "AIWIKI_REQUIRE_COMPATIBLE_BACKEND"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _is_truthy_env(value: str) -> bool:
    return value.strip().lower() in _TRUTHY_VALUES


def _sentinel_snapshot(reason: str) -> dict[str, Any]:
    return {
        "compatibility": "unknown",
        "compatibility_hint": f"preflight probe failed: {reason}",
        "error_class": "preflight_probe_error",
    }


def _probe_snapshot(config: LLMConfig, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend_requested": str(getattr(config, "backend", "") or ""),
        "backend": str(result.get("backend") or ""),
        "model_requested": str(getattr(config, "model", "") or ""),
        "model": str(result.get("model") or ""),
        "compatibility": str(result.get("compatibility") or ""),
        "compatibility_hint": str(result.get("compatibility_hint") or ""),
        "raw_response_path": str(result.get("raw_response_path") or ""),
        "error_class": str(result.get("error_class") or ""),
    }


def preflight_check_backend(root: Path, *, timeout_seconds: int = 30) -> dict[str, Any]:
    """Run a single LLM compatibility probe against the effective backend.

    Behavior:
      - compatible: silent return with snapshot.
      - degraded: emit a warning line, continue with snapshot.
      - unavailable / requires_credential: emit a warning line, continue with sentinel.
      - With AIWIKI_REQUIRE_COMPATIBLE_BACKEND truthy: raise RuntimeError instead.
      - config/probe exceptions: fail-soft warning, continue with sentinel.
    """
    require_compatible = _is_truthy_env(os.environ.get(_REQUIRE_COMPATIBLE_ENV, ""))
    try:
        config = LLMConfig.from_env()
        result = probe_backend(config, root, timeout_seconds=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 — fail-soft is intentional
        _LOGGER.warning("preflight probe failed: %s; continuing without preflight", exc)
        return _sentinel_snapshot(str(exc))

    compatibility = str(result.get("compatibility", "")) if isinstance(result, dict) else ""
    if compatibility == "compatible":
        return _probe_snapshot(config, result)

    backend = str(result.get("backend", "")) if isinstance(result, dict) else ""
    model = str(result.get("model", "")) if isinstance(result, dict) else ""
    hint = str(result.get("compatibility_hint", "")) if isinstance(result, dict) else ""
    message_template = (
        "backend %s/%s probe=%s; hint=%s; "
        "see 'aiwiki llm-check --probe-all --format human'"
    )

    if require_compatible:
        raise RuntimeError(
            f"backend {backend}/{model} probe={compatibility or 'unknown'} "
            f"(hint={hint or '-'}); "
            f"{_REQUIRE_COMPATIBLE_ENV} blocks non-compatible backends. "
            f"See 'aiwiki llm-check --probe-all --format human' to diagnose."
        )

    _LOGGER.warning(message_template, backend, model, compatibility or "unknown", hint or "-")
    if compatibility in {"unavailable", "requires_credential"}:
        return _sentinel_snapshot(f"preflight probe returned {compatibility}: {hint}")
    return _probe_snapshot(config, result)


def preflight_check_backend_chain(root: Path, *, timeout_seconds: int = 10) -> dict[str, Any]:
    """Probe the configured primary backend."""

    try:
        config = LLMConfig.from_env()
    except Exception as exc:  # noqa: BLE001 - submit should stay fail-soft and report snapshot.
        return {
            "kind": "backend-chain-preflight",
            "status": "unavailable",
            "primary": _sentinel_snapshot(str(exc)),
            "fallbacks": [],
        }

    primary = _probe_chain_item(config, root, timeout_seconds=timeout_seconds, role="primary")
    return {
        "kind": "backend-chain-preflight",
        "status": "compatible" if primary.get("compatibility") == "compatible" else "degraded",
        "primary": primary,
        "fallbacks": [],
    }


def _probe_chain_item(config: LLMConfig, root: Path, *, timeout_seconds: int, role: str) -> dict[str, Any]:
    try:
        result = probe_backend(config, root, timeout_seconds=timeout_seconds)
        snapshot = _probe_snapshot(config, result)
    except Exception as exc:  # noqa: BLE001 - chain snapshot should be best-effort.
        snapshot = _sentinel_snapshot(str(exc))
        snapshot["backend_requested"] = config.backend_requested or config.backend
        snapshot["backend"] = config.backend
        snapshot["model_requested"] = config.model_requested
        snapshot["model"] = config.model
    snapshot["role"] = role
    snapshot["available"] = snapshot.get("compatibility") == "compatible"
    return snapshot
