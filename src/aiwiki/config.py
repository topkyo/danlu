"""Environment-backed configuration for aiwiki LLM backends."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_BACKEND = "auto"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_OPENAI_API_MODEL = "gpt-4.1-mini"
DEFAULT_ANTHROPIC_API_MODEL = "claude-sonnet-4-20250514"
BACKEND_OPENAI_API = "openai-api"
BACKEND_ANTHROPIC_API = "anthropic-api"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_CLAUDE_CLI = "claude-cli"
SUPPORTED_BACKENDS = {BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API, BACKEND_CODEX_CLI, BACKEND_CLAUDE_CLI}


@dataclass
class LLMConfig:
    backend: str
    model: str = ""
    api_key: str = ""
    anthropic_api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    anthropic_base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    timeout_seconds: int = 120
    temperature: float = 0.2
    max_context_chars: int = 24000
    codex_command: str = "codex"
    claude_command: str = "claude"
    codex_path: str = ""
    claude_path: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        values = _read_env()
        backend = _resolve_backend(values)
        effective_model = _effective_model(values["model"], backend)
        if backend == BACKEND_OPENAI_API:
            if not values["api_key"]:
                raise RuntimeError("Missing LLM configuration: AIWIKI_LLM_API_KEY or OPENAI_API_KEY")
        elif backend == BACKEND_ANTHROPIC_API:
            if not values["anthropic_api_key"]:
                raise RuntimeError("Missing LLM configuration: AIWIKI_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY")
        elif backend == BACKEND_CODEX_CLI:
            if not values["codex_path"]:
                raise RuntimeError(
                    f"Requested backend `{BACKEND_CODEX_CLI}` but `{values['codex_command']}` is not available."
                )
        elif backend == BACKEND_CLAUDE_CLI:
            if not values["claude_path"]:
                raise RuntimeError(
                    f"Requested backend `{BACKEND_CLAUDE_CLI}` but `{values['claude_command']}` is not available."
                )
        else:
            raise RuntimeError(_missing_backend_message(values))

        return cls(
            backend=backend,
            model=effective_model,
            api_key=values["api_key"],
            anthropic_api_key=values["anthropic_api_key"],
            base_url=values["base_url"],
            anthropic_base_url=values["anthropic_base_url"],
            timeout_seconds=values["timeout_seconds"],
            temperature=values["temperature"],
            max_context_chars=values["max_context_chars"],
            codex_command=values["codex_command"],
            claude_command=values["claude_command"],
            codex_path=values["codex_path"],
            claude_path=values["claude_path"],
        )

    @classmethod
    def status_from_env(cls) -> dict[str, Any]:
        values = _read_env()
        requested = values["requested_backend"]
        try:
            backend = _resolve_backend(values)
            configured = True
            missing = []
            message = ""
            effective_model = _effective_model(values["model"], backend)
        except RuntimeError as exc:
            backend = ""
            configured = False
            missing = _missing_items(values)
            message = str(exc)
            effective_model = ""
        return {
            "configured": configured,
            "backend_requested": requested,
            "backend": backend,
            "image_analysis_supported": _backend_supports_image_analysis(backend),
            "available_backends": _available_backends(values),
            "model_requested": values["model"],
            "model": effective_model or values["model"],
            "effective_model": effective_model,
            "api_key_present": bool(values["api_key"]),
            "anthropic_api_key_present": bool(values["anthropic_api_key"]),
            "base_url": values["base_url"],
            "anthropic_base_url": values["anthropic_base_url"],
            "timeout_seconds": values["timeout_seconds"],
            "temperature": values["temperature"],
            "max_context_chars": values["max_context_chars"],
            "codex_command": values["codex_command"],
            "codex_available": bool(values["codex_path"]),
            "codex_path": values["codex_path"],
            "claude_command": values["claude_command"],
            "claude_available": bool(values["claude_path"]),
            "claude_path": values["claude_path"],
            "auth_mode": _auth_mode_for_backend(backend),
            "usage_visibility": _usage_visibility_for_backend(backend),
            "usage_accounting": _usage_accounting_for_backend(backend),
            "missing": missing,
            "message": message,
        }

    def redacted(self) -> dict[str, Any]:
        data = asdict(self)
        if data["api_key"]:
            data["api_key"] = "***"
        if data["anthropic_api_key"]:
            data["anthropic_api_key"] = "***"
        return data


def _read_env() -> dict[str, Any]:
    requested_backend = (os.environ.get("AIWIKI_LLM_BACKEND") or DEFAULT_BACKEND).strip().lower()
    model = (os.environ.get("AIWIKI_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    api_key = (os.environ.get("AIWIKI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    anthropic_api_key = (
        os.environ.get("AIWIKI_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    ).strip()
    base_url = (
        os.environ.get("AIWIKI_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    anthropic_base_url = (
        os.environ.get("AIWIKI_ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL
    ).rstrip("/")
    timeout_seconds = int(os.environ.get("AIWIKI_LLM_TIMEOUT", "120"))
    temperature = float(os.environ.get("AIWIKI_LLM_TEMPERATURE", "0.2"))
    max_context_chars = int(os.environ.get("AIWIKI_LLM_MAX_CONTEXT_CHARS", "24000"))
    codex_command = (os.environ.get("AIWIKI_CODEX_COMMAND") or "codex").strip()
    claude_command = (os.environ.get("AIWIKI_CLAUDE_COMMAND") or "claude").strip()
    explicit_codex_path = (os.environ.get("AIWIKI_CODEX_PATH") or "").strip()
    explicit_claude_path = (os.environ.get("AIWIKI_CLAUDE_PATH") or "").strip()
    codex_path = explicit_codex_path or shutil.which(codex_command) or ""
    claude_path = explicit_claude_path or shutil.which(claude_command) or ""
    return {
        "requested_backend": requested_backend,
        "model": model,
        "api_key": api_key,
        "anthropic_api_key": anthropic_api_key,
        "base_url": base_url,
        "anthropic_base_url": anthropic_base_url,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "max_context_chars": max_context_chars,
        "codex_command": codex_command,
        "claude_command": claude_command,
        "codex_path": codex_path,
        "claude_path": claude_path,
    }


def _resolve_backend(values: dict[str, Any]) -> str:
    requested = values["requested_backend"]
    if requested and requested != DEFAULT_BACKEND:
        if requested not in SUPPORTED_BACKENDS:
            supported = ", ".join(sorted(SUPPORTED_BACKENDS))
            raise RuntimeError(f"Unsupported AIWIKI_LLM_BACKEND `{requested}`. Expected one of: {supported}, auto.")
        return _validate_requested_backend(requested, values)

    if values["api_key"]:
        return BACKEND_OPENAI_API
    if values["anthropic_api_key"]:
        return BACKEND_ANTHROPIC_API
    if values["codex_path"]:
        return BACKEND_CODEX_CLI
    if values["claude_path"]:
        return BACKEND_CLAUDE_CLI
    raise RuntimeError(_missing_backend_message(values))


def _validate_requested_backend(requested: str, values: dict[str, Any]) -> str:
    if requested == BACKEND_OPENAI_API:
        if not values["api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_ANTHROPIC_API:
        if not values["anthropic_api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_CODEX_CLI:
        if not values["codex_path"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_CLAUDE_CLI:
        if not values["claude_path"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    raise RuntimeError(_missing_backend_message(values))


def _effective_model(requested_model: str, backend: str) -> str:
    model = requested_model.strip()
    if model:
        return model
    if backend == BACKEND_CODEX_CLI:
        return DEFAULT_CODEX_MODEL
    if backend == BACKEND_OPENAI_API:
        return DEFAULT_OPENAI_API_MODEL
    if backend == BACKEND_ANTHROPIC_API:
        return DEFAULT_ANTHROPIC_API_MODEL
    return ""


def _available_backends(values: dict[str, Any]) -> list[str]:
    available: list[str] = []
    if values["api_key"]:
        available.append(BACKEND_OPENAI_API)
    if values["anthropic_api_key"]:
        available.append(BACKEND_ANTHROPIC_API)
    if values["codex_path"]:
        available.append(BACKEND_CODEX_CLI)
    if values["claude_path"]:
        available.append(BACKEND_CLAUDE_CLI)
    return available


def _missing_items(values: dict[str, Any]) -> list[str]:
    requested = values["requested_backend"]
    missing: list[str] = []
    if requested in ("", DEFAULT_BACKEND):
        if not values["api_key"]:
            missing.append("OPENAI-compatible API key")
        if not values["anthropic_api_key"]:
            missing.append("Anthropic API key")
        if not values["codex_path"]:
            missing.append(f"CLI command `{values['codex_command']}`")
        if not values["claude_path"]:
            missing.append(f"CLI command `{values['claude_command']}`")
        return missing
    if requested == BACKEND_OPENAI_API:
        if not values["api_key"]:
            missing.append("AIWIKI_LLM_API_KEY or OPENAI_API_KEY")
    elif requested == BACKEND_ANTHROPIC_API:
        if not values["anthropic_api_key"]:
            missing.append("AIWIKI_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY")
    elif requested == BACKEND_CODEX_CLI and not values["codex_path"]:
        missing.append(f"CLI command `{values['codex_command']}`")
    elif requested == BACKEND_CLAUDE_CLI and not values["claude_path"]:
        missing.append(f"CLI command `{values['claude_command']}`")
    return missing


def _missing_backend_message(values: dict[str, Any]) -> str:
    available = _available_backends(values)
    if available:
        return (
            "LLM backend resolution failed. "
            f"Requested `{values['requested_backend']}` but available backends are: {', '.join(available)}."
        )
    return (
        "No usable LLM backend found. "
        "Provide `AIWIKI_LLM_BACKEND=openai-api` with `AIWIKI_LLM_MODEL` + `AIWIKI_LLM_API_KEY`, "
        "or install/login `codex` or `claude` CLI and optionally set `AIWIKI_LLM_BACKEND=codex-cli|claude-cli`."
    )


def _auth_mode_for_backend(backend: str) -> str:
    if backend in {BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API}:
        return "api-key"
    if backend in {BACKEND_CODEX_CLI, BACKEND_CLAUDE_CLI}:
        return "cli-session"
    return ""


def _usage_visibility_for_backend(backend: str) -> str:
    if backend in {BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API}:
        return "response-usage"
    if backend in {BACKEND_CODEX_CLI, BACKEND_CLAUDE_CLI}:
        return "opaque-cli"
    return ""


def _usage_accounting_for_backend(backend: str) -> str:
    if backend in {BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API}:
        return "provider-api"
    if backend == BACKEND_CODEX_CLI:
        return "copilot-cli-session"
    if backend == BACKEND_CLAUDE_CLI:
        return "claude-cli-session"
    return ""


def _backend_supports_image_analysis(backend: str) -> bool:
    return backend in {BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API, BACKEND_CODEX_CLI}
