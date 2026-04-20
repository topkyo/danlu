"""Environment-backed configuration for aiwiki LLM backends."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_BACKEND = "auto"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_GITHUB_MODELS_BASE_URL = "https://models.github.ai"
DEFAULT_MAX_CONTEXT_CHARS = 24000
DEFAULT_GITHUB_MODELS_MAX_CONTEXT_CHARS = 14000
DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_GITHUB_MODELS_MODEL = "openai/gpt-4.1"
DEFAULT_CODEX_REASONING_EFFORT = "medium"
DEFAULT_OPENAI_API_MODEL = "gpt-4.1-mini"
DEFAULT_ANTHROPIC_API_MODEL = "claude-sonnet-4-20250514"
BACKEND_OPENAI_API = "openai-api"
BACKEND_ANTHROPIC_API = "anthropic-api"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_GITHUB_MODELS_API = "github-models-api"
BACKEND_COPILOT_CLI = "copilot-cli"
BACKEND_CLAUDE_CLI = "claude-cli"
SUPPORTED_BACKENDS = {BACKEND_CODEX_CLI, BACKEND_GITHUB_MODELS_API, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI}


@dataclass
class LLMConfig:
    backend: str
    backend_requested: str = DEFAULT_BACKEND
    model: str = ""
    model_requested: str = ""
    api_key: str = ""
    anthropic_api_key: str = ""
    github_token: str = ""
    github_token_source: str = ""
    base_url: str = DEFAULT_BASE_URL
    anthropic_base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    github_models_base_url: str = DEFAULT_GITHUB_MODELS_BASE_URL
    timeout_seconds: int = 120
    temperature: float = 0.2
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    codex_reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT
    gh_command: str = "gh"
    codex_command: str = "codex"
    copilot_command: str = "copilot"
    claude_command: str = "claude"
    gh_path: str = ""
    codex_path: str = ""
    copilot_path: str = ""
    claude_path: str = ""

    @classmethod
    def from_env(cls) -> "LLMConfig":
        values = _read_env()
        requested = values["requested_backend"]
        backend = _resolve_backend(values)
        effective_model = _effective_model(values["model"], backend)
        effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"], backend)
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
        elif backend == BACKEND_COPILOT_CLI:
            if not values["copilot_path"]:
                raise RuntimeError(
                    f"Requested backend `{BACKEND_COPILOT_CLI}` but `{values['copilot_command']}` is not available."
                )
        elif backend == BACKEND_CLAUDE_CLI:
            if not values["claude_path"]:
                raise RuntimeError(
                    f"Requested backend `{BACKEND_CLAUDE_CLI}` but `{values['claude_command']}` is not available."
                )
        elif backend == BACKEND_GITHUB_MODELS_API:
            if not values["github_token"]:
                raise RuntimeError(
                    "Requested backend `github-models-api` but no GitHub token was found via "
                    "AIWIKI_GITHUB_TOKEN, COPILOT_GITHUB_TOKEN, GH_TOKEN, GITHUB_TOKEN, or `gh auth token`."
                )
        else:
            raise RuntimeError(_missing_backend_message(values))

        return cls(
            backend=backend,
            backend_requested=requested,
            model=effective_model,
            model_requested=values["model"],
            api_key=values["api_key"],
            anthropic_api_key=values["anthropic_api_key"],
            github_token=values["github_token"],
            github_token_source=values["github_token_source"],
            base_url=values["base_url"],
            anthropic_base_url=values["anthropic_base_url"],
            github_models_base_url=values["github_models_base_url"],
            timeout_seconds=values["timeout_seconds"],
            temperature=values["temperature"],
            max_context_chars=effective_max_context_chars,
            codex_reasoning_effort=values["codex_reasoning_effort"],
            gh_command=values["gh_command"],
            codex_command=values["codex_command"],
            copilot_command=values["copilot_command"],
            claude_command=values["claude_command"],
            gh_path=values["gh_path"],
            codex_path=values["codex_path"],
            copilot_path=values["copilot_path"],
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
            effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"], backend)
        except RuntimeError as exc:
            backend = ""
            configured = False
            missing = _missing_items(values)
            message = str(exc)
            effective_model = ""
            effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"], backend)
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
            "github_token_present": bool(values["github_token"]),
            "github_token_source": values["github_token_source"],
            "base_url": values["base_url"],
            "anthropic_base_url": values["anthropic_base_url"],
            "github_models_base_url": values["github_models_base_url"],
            "timeout_seconds": values["timeout_seconds"],
            "temperature": values["temperature"],
            "max_context_chars": effective_max_context_chars,
            "codex_reasoning_effort": values["codex_reasoning_effort"],
            "gh_command": values["gh_command"],
            "gh_available": bool(values["gh_path"]),
            "gh_path": values["gh_path"],
            "codex_command": values["codex_command"],
            "codex_available": bool(values["codex_path"]),
            "codex_path": values["codex_path"],
            "copilot_command": values["copilot_command"],
            "copilot_available": bool(values["copilot_path"]),
            "copilot_path": values["copilot_path"],
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
        if data["github_token"]:
            data["github_token"] = "***"
        return data


def _read_env() -> dict[str, Any]:
    requested_backend = (os.environ.get("AIWIKI_LLM_BACKEND") or DEFAULT_BACKEND).strip().lower()
    model = (os.environ.get("AIWIKI_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    api_key = (os.environ.get("AIWIKI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    anthropic_api_key = (
        os.environ.get("AIWIKI_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    ).strip()
    github_models_base_url = (
        os.environ.get("AIWIKI_GITHUB_MODELS_BASE_URL") or DEFAULT_GITHUB_MODELS_BASE_URL
    ).rstrip("/")
    base_url = (
        os.environ.get("AIWIKI_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
    ).rstrip("/")
    anthropic_base_url = (
        os.environ.get("AIWIKI_ANTHROPIC_BASE_URL") or DEFAULT_ANTHROPIC_BASE_URL
    ).rstrip("/")
    timeout_seconds = int(os.environ.get("AIWIKI_LLM_TIMEOUT", "120"))
    temperature = float(os.environ.get("AIWIKI_LLM_TEMPERATURE", "0.2"))
    max_context_chars_override = (os.environ.get("AIWIKI_LLM_MAX_CONTEXT_CHARS") or "").strip()
    codex_reasoning_effort = (os.environ.get("AIWIKI_CODEX_REASONING_EFFORT") or DEFAULT_CODEX_REASONING_EFFORT).strip().lower()
    gh_command = (os.environ.get("AIWIKI_GH_COMMAND") or "gh").strip()
    codex_command = (os.environ.get("AIWIKI_CODEX_COMMAND") or "codex").strip()
    copilot_command = (os.environ.get("AIWIKI_COPILOT_COMMAND") or "copilot").strip()
    claude_command = (os.environ.get("AIWIKI_CLAUDE_COMMAND") or "claude").strip()
    explicit_gh_path = (os.environ.get("AIWIKI_GH_PATH") or "").strip()
    explicit_codex_path = (os.environ.get("AIWIKI_CODEX_PATH") or "").strip()
    explicit_copilot_path = (os.environ.get("AIWIKI_COPILOT_PATH") or "").strip()
    explicit_claude_path = (os.environ.get("AIWIKI_CLAUDE_PATH") or "").strip()
    gh_path = explicit_gh_path or shutil.which(gh_command) or ""
    codex_path = explicit_codex_path or shutil.which(codex_command) or ""
    copilot_path = explicit_copilot_path or shutil.which(copilot_command) or ""
    claude_path = explicit_claude_path or shutil.which(claude_command) or ""
    github_token, github_token_source = _resolve_github_token(gh_path, gh_command)
    return {
        "requested_backend": requested_backend,
        "model": model,
        "api_key": api_key,
        "anthropic_api_key": anthropic_api_key,
        "github_token": github_token,
        "github_token_source": github_token_source,
        "github_models_base_url": github_models_base_url,
        "base_url": base_url,
        "anthropic_base_url": anthropic_base_url,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "max_context_chars_override": max_context_chars_override,
        "codex_reasoning_effort": codex_reasoning_effort,
        "gh_command": gh_command,
        "codex_command": codex_command,
        "copilot_command": copilot_command,
        "claude_command": claude_command,
        "gh_path": gh_path,
        "codex_path": codex_path,
        "copilot_path": copilot_path,
        "claude_path": claude_path,
    }


def _resolve_backend(values: dict[str, Any]) -> str:
    requested = values["requested_backend"]
    if requested and requested != DEFAULT_BACKEND:
        if requested not in SUPPORTED_BACKENDS:
            supported = ", ".join(sorted(SUPPORTED_BACKENDS))
            raise RuntimeError(f"Unsupported AIWIKI_LLM_BACKEND `{requested}`. Expected one of: {supported}, auto.")
        return _validate_requested_backend(requested, values)

    if values["codex_path"]:
        return BACKEND_CODEX_CLI
    if values["copilot_path"]:
        return BACKEND_COPILOT_CLI
    if values["claude_path"]:
        return BACKEND_CLAUDE_CLI
    raise RuntimeError(_missing_backend_message(values))


def _validate_requested_backend(requested: str, values: dict[str, Any]) -> str:
    if requested == BACKEND_CODEX_CLI:
        if not values["codex_path"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_COPILOT_CLI:
        if not values["copilot_path"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_CLAUDE_CLI:
        if not values["claude_path"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_GITHUB_MODELS_API:
        if not values["github_token"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    raise RuntimeError(_missing_backend_message(values))


def _effective_model(requested_model: str, backend: str) -> str:
    model = requested_model.strip()
    if model:
        return model
    if backend == BACKEND_CODEX_CLI:
        return DEFAULT_CODEX_MODEL
    if backend == BACKEND_GITHUB_MODELS_API:
        return DEFAULT_GITHUB_MODELS_MODEL
    return ""


def _effective_max_context_chars(raw_override: str, backend: str) -> int:
    if str(raw_override or "").strip():
        return int(str(raw_override).strip())
    if backend == BACKEND_GITHUB_MODELS_API:
        return DEFAULT_GITHUB_MODELS_MAX_CONTEXT_CHARS
    return DEFAULT_MAX_CONTEXT_CHARS


def _available_backends(values: dict[str, Any]) -> list[str]:
    available: list[str] = []
    if values["codex_path"]:
        available.append(BACKEND_CODEX_CLI)
    if values["copilot_path"]:
        available.append(BACKEND_COPILOT_CLI)
    if values["claude_path"]:
        available.append(BACKEND_CLAUDE_CLI)
    if values["github_token"]:
        available.append(BACKEND_GITHUB_MODELS_API)
    return available


def _missing_items(values: dict[str, Any]) -> list[str]:
    requested = values["requested_backend"]
    missing: list[str] = []
    if requested in ("", DEFAULT_BACKEND):
        if not values["codex_path"]:
            missing.append(f"CLI command `{values['codex_command']}`")
        if not values["copilot_path"]:
            missing.append(f"CLI command `{values['copilot_command']}`")
        if not values["claude_path"]:
            missing.append(f"CLI command `{values['claude_command']}`")
        return missing
    if requested == BACKEND_CODEX_CLI and not values["codex_path"]:
        missing.append(f"CLI command `{values['codex_command']}`")
    elif requested == BACKEND_GITHUB_MODELS_API and not values["github_token"]:
        missing.append("GitHub token via AIWIKI_GITHUB_TOKEN|COPILOT_GITHUB_TOKEN|GH_TOKEN|GITHUB_TOKEN or `gh auth token`")
    elif requested == BACKEND_COPILOT_CLI and not values["copilot_path"]:
        missing.append(f"CLI command `{values['copilot_command']}`")
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
        "Install/login `codex`, `copilot`, or `claude` CLI for `auto`, or explicitly set "
        "`AIWIKI_LLM_BACKEND=codex-cli|github-models-api|copilot-cli|claude-cli`."
    )


def _auth_mode_for_backend(backend: str) -> str:
    if backend in {BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI}:
        return "cli-session"
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-token-or-gh-cli"
    return ""


def _usage_visibility_for_backend(backend: str) -> str:
    if backend in {BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI}:
        return "opaque-cli"
    if backend == BACKEND_GITHUB_MODELS_API:
        return "response-usage"
    return ""


def _usage_accounting_for_backend(backend: str) -> str:
    if backend == BACKEND_CODEX_CLI:
        return "codex-cli-session"
    if backend == BACKEND_COPILOT_CLI:
        return "copilot-cli-session"
    if backend == BACKEND_CLAUDE_CLI:
        return "claude-cli-session"
    if backend == BACKEND_GITHUB_MODELS_API:
        return "github-models-api"
    return ""


def _backend_supports_image_analysis(backend: str) -> bool:
    return backend == BACKEND_CODEX_CLI


def _resolve_github_token(gh_path: str, gh_command: str) -> tuple[str, str]:
    for env_name in ("AIWIKI_GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value, env_name
    if not gh_path:
        return "", ""
    try:
        completed = subprocess.run(
            [gh_path or gh_command, "auth", "token"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    if completed.returncode != 0:
        return "", ""
    token = completed.stdout.strip()
    if not token:
        return "", ""
    return token, "gh auth token"
