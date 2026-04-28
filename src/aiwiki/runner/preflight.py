"""Backend preflight checks for run-compile / run-ask entry points."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiwiki.config import LLMConfig
from aiwiki.llm import probe_backend

_LOGGER = logging.getLogger("aiwiki")
_REQUIRE_COMPATIBLE_ENV = "AIWIKI_REQUIRE_COMPATIBLE_BACKEND"
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _is_truthy_env(value: str) -> bool:
    return value.strip().lower() in _TRUTHY_VALUES


def preflight_check_backend(root: Path, *, timeout_seconds: int = 30) -> None:
    """Run a single LLM compatibility probe against the effective backend.

    Behavior:
      - compatible: silent return.
      - degraded / unavailable / requires_credential: emit a warning line, continue.
      - With AIWIKI_REQUIRE_COMPATIBLE_BACKEND truthy: raise RuntimeError instead.
      - probe_backend itself raising any exception: fail-soft warning, continue.
    """
    require_compatible = _is_truthy_env(os.environ.get(_REQUIRE_COMPATIBLE_ENV, ""))
    try:
        config = LLMConfig.from_env()
        result = probe_backend(config, root, timeout_seconds=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 — fail-soft is intentional
        _LOGGER.warning("preflight probe failed: %s; continuing without preflight", exc)
        return

    compatibility = str(result.get("compatibility", "")) if isinstance(result, dict) else ""
    if compatibility == "compatible":
        return

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
