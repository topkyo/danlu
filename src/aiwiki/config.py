"""Environment-backed configuration for aiwiki LLM backends."""

from __future__ import annotations

import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any


DEFAULT_BACKEND = "auto"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
BACKEND_OPENAI_API = "openai-api"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_CLAUDE_CLI = "claude-cli"
SUPPORTED_BACKENDS = {BACKEND_OPENAI_API, BACKEND_CODEX_CLI, BACKEND_CLAUDE_CLI}


@dataclass
class LLMConfig:
    backend: str
    model: str = ""
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
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
        if backend == BACKEND_OPENAI_API:
            missing: list[str] = []
            if not values["model"]:
                missing.append("AIWIKI_LLM_MODEL or OPENAI_MODEL")
            if not values["api_key"]:
                missing.append("AIWIKI_LLM_API_KEY or OPENAI_API_KEY")
            if missing:
                raise RuntimeError(f"Missing LLM configuration: {', '.join(missing)}")
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
            model=values["model"],
            api_key=values["api_key"],
            base_url=values["base_url"],
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
        except RuntimeError as exc:
            backend = ""
            configured = False
            missing = _missing_items(values)
            message = str(exc)
        return {
            "configured": configured,
            "backend_requested": requested,
            "backend": backend,
            "image_analysis_supported": _backend_supports_image_analysis(backend),
            "available_backends": _available_backends(values),
            "model": values["model"],
            "api_key_present": bool(values["api_key"]),
            "base_url": values["base_url"],
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
            "missing": missing,
            "message": message,
        }

    def redacted(self) -> dict[str, Any]:
        data = asdict(self)
        if data["api_key"]:
            data["api_key"] = "***"
        return data


def _read_env() -> dict[str, Any]:
    requested_backend = (os.environ.get("AIWIKI_LLM_BACKEND") or DEFAULT_BACKEND).strip().lower()
    model = (os.environ.get("AIWIKI_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    api_key = (os.environ.get("AIWIKI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    base_url = (
        os.environ.get("AIWIKI_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    timeout_seconds = int(os.environ.get("AIWIKI_LLM_TIMEOUT", "120"))
    temperature = float(os.environ.get("AIWIKI_LLM_TEMPERATURE", "0.2"))
    max_context_chars = int(os.environ.get("AIWIKI_LLM_MAX_CONTEXT_CHARS", "24000"))
    codex_command = (os.environ.get("AIWIKI_CODEX_COMMAND") or "codex").strip()
    claude_command = (os.environ.get("AIWIKI_CLAUDE_COMMAND") or "claude").strip()
    codex_path = shutil.which(codex_command) or ""
    claude_path = shutil.which(claude_command) or ""
    return {
        "requested_backend": requested_backend,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
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

    if values["api_key"] and values["model"]:
        return BACKEND_OPENAI_API
    if values["codex_path"]:
        return BACKEND_CODEX_CLI
    if values["claude_path"]:
        return BACKEND_CLAUDE_CLI
    raise RuntimeError(_missing_backend_message(values))


def _validate_requested_backend(requested: str, values: dict[str, Any]) -> str:
    if requested == BACKEND_OPENAI_API:
        if not values["model"] or not values["api_key"]:
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


def _available_backends(values: dict[str, Any]) -> list[str]:
    available: list[str] = []
    if values["api_key"] and values["model"]:
        available.append(BACKEND_OPENAI_API)
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
        if not values["model"]:
            missing.append("LLM model name")
        if not values["codex_path"]:
            missing.append(f"CLI command `{values['codex_command']}`")
        if not values["claude_path"]:
            missing.append(f"CLI command `{values['claude_command']}`")
        return missing
    if requested == BACKEND_OPENAI_API:
        if not values["model"]:
            missing.append("AIWIKI_LLM_MODEL or OPENAI_MODEL")
        if not values["api_key"]:
            missing.append("AIWIKI_LLM_API_KEY or OPENAI_API_KEY")
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
    if backend == BACKEND_OPENAI_API:
        return "api-key"
    if backend in {BACKEND_CODEX_CLI, BACKEND_CLAUDE_CLI}:
        return "cli-session"
    return ""


def _backend_supports_image_analysis(backend: str) -> bool:
    return backend in {BACKEND_OPENAI_API, BACKEND_CODEX_CLI}
