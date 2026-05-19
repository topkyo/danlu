"""Environment-backed configuration for aiwiki LLM backends."""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_BACKEND = "opencode-api"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_OPENCODE_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAX_CONTEXT_CHARS = 24000
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_OPENCODE_MODEL = "deepseek-v4-pro"
DEFAULT_NVIDIA_NIM_MODEL = "openai/gpt-oss-120b"
DEFAULT_CODEX_REASONING_EFFORT = "medium"
DEFAULT_OPENAI_API_MODEL = "gpt-4.1-mini"
DEFAULT_ANTHROPIC_API_MODEL = "claude-sonnet-4-20250514"
DEFAULT_L3_AUTO_ADOPT_MIN_EVIDENCE = 5
BACKEND_OPENCODE_API = "opencode-api"
BACKEND_OPENROUTER_API = "openrouter-api"
BACKEND_OPENAI_API = "openai-api"
BACKEND_ANTHROPIC_API = "anthropic-api"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_NVIDIA_NIM_API = "nvidia-nim-api"
BACKEND_COPILOT_CLI = "copilot-cli"
BACKEND_CLAUDE_CLI = "claude-cli"
DEFAULT_BACKEND_FALLBACK = BACKEND_CODEX_CLI
DEFAULT_BACKEND_FALLBACK_MODEL = DEFAULT_CODEX_MODEL
SUPPORTED_BACKENDS = {
    BACKEND_OPENCODE_API,
    BACKEND_OPENROUTER_API,
    BACKEND_OPENAI_API,
    BACKEND_ANTHROPIC_API,
    BACKEND_CODEX_CLI,
    BACKEND_NVIDIA_NIM_API,
    BACKEND_COPILOT_CLI,
    BACKEND_CLAUDE_CLI,
}

_logger = logging.getLogger(__name__)


def l3_auto_adopt_min_evidence_from_env() -> int:
    raw = os.environ.get("AIWIKI_L3_AUTO_ADOPT_MIN_EVIDENCE", str(DEFAULT_L3_AUTO_ADOPT_MIN_EVIDENCE))
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        _logger.warning(
            "Invalid AIWIKI_L3_AUTO_ADOPT_MIN_EVIDENCE=%r; using default %s",
            raw,
            DEFAULT_L3_AUTO_ADOPT_MIN_EVIDENCE,
        )
        return DEFAULT_L3_AUTO_ADOPT_MIN_EVIDENCE

@dataclass
class LLMConfig:
    backend: str
    backend_requested: str = DEFAULT_BACKEND
    model: str = ""
    model_requested: str = ""
    model_fallback_chain: tuple[str, ...] = ()
    backend_fallback_chain: tuple[str, ...] = ()
    backend_fallback_model: str = ""
    api_key: str = ""
    anthropic_api_key: str = ""
    opencode_api_key: str = ""
    opencode_api_key_source: str = ""
    openrouter_api_key: str = ""
    openrouter_api_key_source: str = ""
    nvidia_nim_api_key: str = ""
    nvidia_nim_api_key_source: str = ""
    base_url: str = DEFAULT_BASE_URL
    anthropic_base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    opencode_base_url: str = DEFAULT_OPENCODE_BASE_URL
    openrouter_base_url: str = DEFAULT_OPENROUTER_BASE_URL
    nvidia_nim_base_url: str = DEFAULT_NVIDIA_NIM_BASE_URL
    timeout_seconds: int = 120
    temperature: float = 0.2
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    codex_reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT
    codex_command: str = "codex"
    copilot_command: str = "copilot"
    claude_command: str = "claude"
    codex_path: str = ""
    copilot_path: str = ""
    claude_path: str = ""

    @classmethod
    def from_env(cls, *, model_fallback: Any | None = None) -> "LLMConfig":
        values = _read_env()
        if model_fallback is not None:
            values["model_fallback"] = model_fallback
        requested = values["requested_backend"]
        backend = _resolve_backend(values)
        # M7.4d Model Policy: strict mode rejects implicit backend default fallback.
        if values.get("require_explicit_model") and not values["model"]:
            backend_default = _effective_model("", backend)
            raise RuntimeError(
                "AIWIKI_REQUIRE_EXPLICIT_MODEL=1 but no AIWIKI_LLM_MODEL set; "
                f"backend `{backend}` would fall back to `{backend_default or '(none)'}`. "
                "Set AIWIKI_LLM_MODEL=<model> or unset AIWIKI_REQUIRE_EXPLICIT_MODEL."
            )
        effective_model = _effective_model(values["model"], backend)
        effective_model_fallback_chain = _effective_model_fallback_chain(
            effective_model,
            _resolve_model_fallback_chain(values),
        )
        effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"])
        if backend == BACKEND_CODEX_CLI:
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
        elif backend == BACKEND_NVIDIA_NIM_API:
            if not values["nvidia_nim_api_key"]:
                raise RuntimeError(
                    "Requested backend `nvidia-nim-api` but no NVIDIA NIM key was found via "
                    "AIWIKI_NVIDIA_NIM_API_KEY or NVIDIA_NIM_API_KEY."
                )
        elif backend == BACKEND_OPENCODE_API:
            if not values["opencode_api_key"]:
                raise RuntimeError(
                    "Requested backend `opencode-api` but no OpenCode API key was found via "
                    "AIWIKI_OPENCODE_API_KEY or AIWIKI_LLM_API_KEY."
                )
        elif backend == BACKEND_OPENROUTER_API:
            if not values["openrouter_api_key"]:
                raise RuntimeError(
                    "Requested backend `openrouter-api` but no OpenRouter API key was found via "
                    "AIWIKI_OPENROUTER_API_KEY."
                )
        elif backend == BACKEND_OPENAI_API:
            if not values["api_key"]:
                raise RuntimeError(
                    "Requested backend `openai-api` but no OpenAI-compatible key was found via "
                    "AIWIKI_LLM_API_KEY or OPENAI_API_KEY."
                )
        elif backend == BACKEND_ANTHROPIC_API:
            if not values["anthropic_api_key"]:
                raise RuntimeError(
                    "Requested backend `anthropic-api` but no Anthropic API key was found via "
                    "AIWIKI_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY."
                )
        else:
            raise RuntimeError(_missing_backend_message(values))

        effective_api_key = values["api_key"]
        effective_base_url = values["base_url"]
        if backend == BACKEND_OPENCODE_API:
            effective_api_key = values["opencode_api_key"]
            effective_base_url = values["opencode_base_url"]
        elif backend == BACKEND_OPENROUTER_API:
            effective_api_key = values["openrouter_api_key"]
            effective_base_url = values["openrouter_base_url"]
        elif backend == BACKEND_NVIDIA_NIM_API:
            effective_api_key = values["nvidia_nim_api_key"]
            effective_base_url = values["nvidia_nim_base_url"]

        return cls(
            backend=backend,
            backend_requested=requested,
            model=effective_model,
            model_requested=values["model"],
            model_fallback_chain=effective_model_fallback_chain,
            backend_fallback_chain=_resolve_backend_fallback_chain(values),
            backend_fallback_model=values["env_backend_fallback_model"],
            api_key=effective_api_key,
            anthropic_api_key=values["anthropic_api_key"],
            opencode_api_key=values["opencode_api_key"],
            opencode_api_key_source=values["opencode_api_key_source"],
            openrouter_api_key=values["openrouter_api_key"],
            openrouter_api_key_source=values["openrouter_api_key_source"],
            nvidia_nim_api_key=values["nvidia_nim_api_key"],
            nvidia_nim_api_key_source=values["nvidia_nim_api_key_source"],
            base_url=effective_base_url,
            anthropic_base_url=values["anthropic_base_url"],
            opencode_base_url=values["opencode_base_url"],
            openrouter_base_url=values["openrouter_base_url"],
            nvidia_nim_base_url=values["nvidia_nim_base_url"],
            timeout_seconds=values["timeout_seconds"],
            temperature=values["temperature"],
            max_context_chars=effective_max_context_chars,
            codex_reasoning_effort=values["codex_reasoning_effort"],
            codex_command=values["codex_command"],
            copilot_command=values["copilot_command"],
            claude_command=values["claude_command"],
            codex_path=values["codex_path"],
            copilot_path=values["copilot_path"],
            claude_path=values["claude_path"],
        )

    @classmethod
    def status_from_env(cls) -> dict[str, Any]:
        values = _read_env()
        requested = values["requested_backend"]
        effective_api_key_present = bool(values["api_key"])
        effective_base_url = values["base_url"]
        try:
            backend = _resolve_backend(values)
            configured = True
            missing = []
            message = ""
            effective_model = _effective_model(values["model"], backend)
            effective_model_fallback_chain = _effective_model_fallback_chain(
                effective_model,
                _resolve_model_fallback_chain(values),
            )
            effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"])
            if backend == BACKEND_NVIDIA_NIM_API:
                effective_api_key_present = bool(values["nvidia_nim_api_key"])
                effective_base_url = values["nvidia_nim_base_url"]
            elif backend == BACKEND_OPENCODE_API:
                effective_api_key_present = bool(values["opencode_api_key"])
                effective_base_url = values["opencode_base_url"]
            elif backend == BACKEND_OPENROUTER_API:
                effective_api_key_present = bool(values["openrouter_api_key"])
                effective_base_url = values["openrouter_base_url"]
            elif backend == BACKEND_ANTHROPIC_API:
                effective_api_key_present = bool(values["anthropic_api_key"])
                effective_base_url = values["anthropic_base_url"]
        except RuntimeError as exc:
            backend = ""
            configured = False
            missing = _missing_items(values)
            message = str(exc)
            effective_model = ""
            effective_model_fallback_chain = _effective_model_fallback_chain(
                effective_model,
                _resolve_model_fallback_chain(values),
            )
            effective_max_context_chars = _effective_max_context_chars(values["max_context_chars_override"])
        return {
            "configured": configured,
            "backend_requested": requested,
            "backend": backend,
            "image_analysis_supported": _backend_supports_image_analysis(backend, effective_model),
            "available_backends": _available_backends(values),
            "model_requested": values["model"],
            "model": effective_model or values["model"],
            "effective_model": effective_model,
            "model_source": _compute_model_source(values["model"], backend),
            "model_fallback_chain": list(effective_model_fallback_chain),
            "backend_fallback_chain": list(_resolve_backend_fallback_chain(values)),
            "backend_fallback_model": values["env_backend_fallback_model"],
            "backend_fallbacks": _backend_fallback_statuses(values, primary_backend=backend),
            "api_key_present": effective_api_key_present,
            "anthropic_api_key_present": bool(values["anthropic_api_key"]),
            "opencode_api_key_present": bool(values["opencode_api_key"]),
            "opencode_api_key_source": values["opencode_api_key_source"],
            "openrouter_api_key_present": bool(values["openrouter_api_key"]),
            "openrouter_api_key_source": values["openrouter_api_key_source"],
            "nvidia_nim_api_key_present": bool(values["nvidia_nim_api_key"]),
            "nvidia_nim_api_key_source": values["nvidia_nim_api_key_source"],
            "base_url": effective_base_url,
            "anthropic_base_url": values["anthropic_base_url"],
            "opencode_base_url": values["opencode_base_url"],
            "openrouter_base_url": values["openrouter_base_url"],
            "nvidia_nim_base_url": values["nvidia_nim_base_url"],
            "timeout_seconds": values["timeout_seconds"],
            "temperature": values["temperature"],
            "max_context_chars": effective_max_context_chars,
            "codex_reasoning_effort": values["codex_reasoning_effort"],
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
        if data["opencode_api_key"]:
            data["opencode_api_key"] = "***"
        if data["openrouter_api_key"]:
            data["openrouter_api_key"] = "***"
        if data["nvidia_nim_api_key"]:
            data["nvidia_nim_api_key"] = "***"
        return data


def _read_env() -> dict[str, Any]:
    requested_backend = (os.environ.get("AIWIKI_LLM_BACKEND") or DEFAULT_BACKEND).strip().lower()
    model = (os.environ.get("AIWIKI_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    env_model_fallback = os.environ.get("AIWIKI_MODEL_FALLBACK")
    explicit_backend_fallback = "AIWIKI_BACKEND_FALLBACK" in os.environ
    raw_backend_fallback = os.environ.get("AIWIKI_BACKEND_FALLBACK")
    env_backend_fallback = (
        raw_backend_fallback
        if explicit_backend_fallback
        else _canonical_backend_fallback(requested_backend=requested_backend, requested_model=model)
    )
    env_backend_fallback_model = (os.environ.get("AIWIKI_BACKEND_FALLBACK_MODEL") or "").strip()
    if not env_backend_fallback_model and _parse_backend_fallback_chain(env_backend_fallback, primary=requested_backend):
        env_backend_fallback_model = DEFAULT_BACKEND_FALLBACK_MODEL
    api_key = (os.environ.get("AIWIKI_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
    opencode_api_key, opencode_api_key_source = _resolve_opencode_api_key()
    openrouter_api_key, openrouter_api_key_source = _resolve_openrouter_api_key()
    anthropic_api_key = (
        os.environ.get("AIWIKI_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""
    ).strip()
    nvidia_nim_api_key, nvidia_nim_api_key_source = _resolve_nvidia_nim_api_key()
    nvidia_nim_base_url = (
        os.environ.get("AIWIKI_NVIDIA_NIM_BASE_URL") or os.environ.get("NVIDIA_NIM_BASE_URL") or DEFAULT_NVIDIA_NIM_BASE_URL
    ).rstrip("/")
    opencode_base_url = (
        os.environ.get("AIWIKI_OPENCODE_BASE_URL") or DEFAULT_OPENCODE_BASE_URL
    ).rstrip("/")
    openrouter_base_url = (
        os.environ.get("AIWIKI_OPENROUTER_BASE_URL")
        or os.environ.get("OPENROUTER_BASE_URL")
        or DEFAULT_OPENROUTER_BASE_URL
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
    codex_command = (os.environ.get("AIWIKI_CODEX_COMMAND") or "codex").strip()
    copilot_command = (os.environ.get("AIWIKI_COPILOT_COMMAND") or "copilot").strip()
    claude_command = (os.environ.get("AIWIKI_CLAUDE_COMMAND") or "claude").strip()
    explicit_codex_path = (os.environ.get("AIWIKI_CODEX_PATH") or "").strip()
    explicit_copilot_path = (os.environ.get("AIWIKI_COPILOT_PATH") or "").strip()
    explicit_claude_path = (os.environ.get("AIWIKI_CLAUDE_PATH") or "").strip()
    codex_path = explicit_codex_path or shutil.which(codex_command) or ""
    copilot_path = explicit_copilot_path or shutil.which(copilot_command) or ""
    claude_path = explicit_claude_path or shutil.which(claude_command) or ""
    require_explicit_model = (os.environ.get("AIWIKI_REQUIRE_EXPLICIT_MODEL") or "").strip() == "1"
    return {
        "requested_backend": requested_backend,
        "model": model,
        "model_fallback": None,
        "env_model_fallback": env_model_fallback,
        "env_backend_fallback": env_backend_fallback,
        "env_backend_fallback_model": env_backend_fallback_model,
        "api_key": api_key,
        "opencode_api_key": opencode_api_key,
        "opencode_api_key_source": opencode_api_key_source,
        "openrouter_api_key": openrouter_api_key,
        "openrouter_api_key_source": openrouter_api_key_source,
        "anthropic_api_key": anthropic_api_key,
        "nvidia_nim_api_key": nvidia_nim_api_key,
        "nvidia_nim_api_key_source": nvidia_nim_api_key_source,
        "nvidia_nim_base_url": nvidia_nim_base_url,
        "opencode_base_url": opencode_base_url,
        "openrouter_base_url": openrouter_base_url,
        "base_url": base_url,
        "anthropic_base_url": anthropic_base_url,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "max_context_chars_override": max_context_chars_override,
        "codex_reasoning_effort": codex_reasoning_effort,
        "codex_command": codex_command,
        "copilot_command": copilot_command,
        "claude_command": claude_command,
        "codex_path": codex_path,
        "copilot_path": copilot_path,
        "claude_path": claude_path,
        "require_explicit_model": require_explicit_model,
    }


def _resolve_backend(values: dict[str, Any]) -> str:
    requested = values["requested_backend"]
    if not requested:
        raise RuntimeError(_missing_backend_message(values))
    if requested not in SUPPORTED_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise RuntimeError(f"Unsupported AIWIKI_LLM_BACKEND `{requested}`. Expected one of: {supported}.")
    return _validate_requested_backend(requested, values)


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
    if requested == BACKEND_NVIDIA_NIM_API:
        if not values["nvidia_nim_api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_OPENCODE_API:
        if not values["opencode_api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_OPENROUTER_API:
        if not values["openrouter_api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_OPENAI_API:
        if not values["api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    if requested == BACKEND_ANTHROPIC_API:
        if not values["anthropic_api_key"]:
            raise RuntimeError(_missing_backend_message(values))
        return requested
    raise RuntimeError(_missing_backend_message(values))


def _effective_model(requested_model: str, backend: str) -> str:
    model = requested_model.strip()
    if model:
        return model
    if backend == BACKEND_OPENCODE_API:
        return DEFAULT_OPENCODE_MODEL
    if backend == BACKEND_NVIDIA_NIM_API:
        return DEFAULT_NVIDIA_NIM_MODEL
    if backend == BACKEND_OPENAI_API:
        return DEFAULT_OPENAI_API_MODEL
    if backend == BACKEND_ANTHROPIC_API:
        return DEFAULT_ANTHROPIC_API_MODEL
    defaults = _default_model_chain(backend, requested_model)
    if defaults:
        return defaults[0]
    return ""


def _compute_model_source(requested_model: str, backend: str) -> str:
    """M7.4d: classify how the effective model was chosen.

    Returns:
        "explicit"          — user set AIWIKI_LLM_MODEL / OPENAI_MODEL
        "backend_default"   — empty request, backend has a known default
        "none"              — empty request, no backend default available
                              (also when backend resolution itself failed)
    """
    if requested_model.strip():
        return "explicit"
    if not backend:
        return "none"
    if _effective_model("", backend):
        return "backend_default"
    return "none"


def _default_model_chain(backend: str, requested_model: str = "") -> tuple[str, ...]:
    model = str(requested_model or "").strip()
    if model:
        return (model,)
    if backend == BACKEND_OPENCODE_API:
        return (DEFAULT_OPENCODE_MODEL,)
    if backend == BACKEND_CODEX_CLI:
        return (DEFAULT_CODEX_MODEL,)
    if backend == BACKEND_OPENAI_API:
        return (DEFAULT_OPENAI_API_MODEL,)
    if backend == BACKEND_ANTHROPIC_API:
        return (DEFAULT_ANTHROPIC_API_MODEL,)
    return ()


def _resolve_model_fallback_chain(values: dict[str, Any]) -> tuple[str, ...]:
    if values.get("model_fallback") is not None:
        return _parse_model_fallback_chain(values.get("model_fallback"))
    return _parse_model_fallback_chain(values.get("env_model_fallback"))


def _resolve_backend_fallback_chain(values: dict[str, Any]) -> tuple[str, ...]:
    return _parse_backend_fallback_chain(values.get("env_backend_fallback"), primary=values.get("requested_backend", ""))


def _canonical_backend_fallback(*, requested_backend: str, requested_model: str) -> str:
    backend = str(requested_backend or "").strip().lower()
    model = str(requested_model or "").strip()
    if backend == BACKEND_OPENCODE_API and (not model or model == DEFAULT_OPENCODE_MODEL):
        return DEFAULT_BACKEND_FALLBACK
    return ""


def _backend_fallback_statuses(values: dict[str, Any], *, primary_backend: str) -> list[dict[str, Any]]:
    fallback_model = str(values.get("env_backend_fallback_model") or "").strip()
    statuses: list[dict[str, Any]] = []
    for backend in _resolve_backend_fallback_chain(values):
        model = fallback_model if backend == BACKEND_CODEX_CLI and fallback_model else _default_model_for_backend(backend, values)
        available, reason = _static_backend_available(values, backend)
        statuses.append(
            {
                "backend": backend,
                "model": model,
                "configured": backend != primary_backend,
                "available": available,
                "reason": reason,
            }
        )
    return statuses


def _static_backend_available(values: dict[str, Any], backend: str) -> tuple[bool, str]:
    if backend == BACKEND_CODEX_CLI:
        return (bool(values.get("codex_path")), "codex command found" if values.get("codex_path") else "codex command not found")
    if backend == BACKEND_COPILOT_CLI:
        return (bool(values.get("copilot_path")), "copilot command found" if values.get("copilot_path") else "copilot command not found")
    if backend == BACKEND_CLAUDE_CLI:
        return (bool(values.get("claude_path")), "claude command found" if values.get("claude_path") else "claude command not found")
    if backend == BACKEND_OPENCODE_API:
        return (bool(values.get("opencode_api_key")), "opencode api key configured" if values.get("opencode_api_key") else "opencode api key missing")
    if backend == BACKEND_OPENROUTER_API:
        return (bool(values.get("openrouter_api_key")), "openrouter api key configured" if values.get("openrouter_api_key") else "openrouter api key missing")
    if backend == BACKEND_NVIDIA_NIM_API:
        return (bool(values.get("nvidia_nim_api_key")), "nvidia nim api key configured" if values.get("nvidia_nim_api_key") else "nvidia nim api key missing")
    if backend == BACKEND_OPENAI_API:
        return (bool(values.get("api_key")), "openai-compatible api key configured" if values.get("api_key") else "openai-compatible api key missing")
    if backend == BACKEND_ANTHROPIC_API:
        return (bool(values.get("anthropic_api_key")), "anthropic api key configured" if values.get("anthropic_api_key") else "anthropic api key missing")
    return False, "unsupported backend"


def _default_model_for_backend(backend: str, values: dict[str, Any]) -> str:
    if backend == BACKEND_OPENCODE_API:
        return DEFAULT_OPENCODE_MODEL
    if backend == BACKEND_CODEX_CLI:
        return DEFAULT_CODEX_MODEL
    if backend == BACKEND_NVIDIA_NIM_API:
        return DEFAULT_NVIDIA_NIM_MODEL
    if backend == BACKEND_OPENAI_API:
        return str(values.get("model") or DEFAULT_OPENAI_API_MODEL)
    if backend == BACKEND_ANTHROPIC_API:
        return str(values.get("model") or DEFAULT_ANTHROPIC_API_MODEL)
    return str(values.get("model") or "")


def _parse_model_fallback_chain(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    raw_items: list[Any]
    if isinstance(raw, (list, tuple)):
        raw_items = list(raw)
    else:
        raw_items = [raw]
    models: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        for candidate in str(item or "").split(","):
            model = candidate.strip()
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
    return tuple(models)


def _parse_backend_fallback_chain(raw: Any, *, primary: str = "") -> tuple[str, ...]:
    if raw is None:
        return ()
    raw_items: list[Any]
    if isinstance(raw, (list, tuple)):
        raw_items = list(raw)
    else:
        raw_items = [raw]
    primary_backend = str(primary or "").strip().lower()
    backends: list[str] = []
    seen: set[str] = {primary_backend} if primary_backend else set()
    for item in raw_items:
        for candidate in str(item or "").split(","):
            backend = candidate.strip().lower()
            if not backend or backend in seen or backend not in SUPPORTED_BACKENDS:
                continue
            seen.add(backend)
            backends.append(backend)
    return tuple(backends)


def _effective_model_fallback_chain(effective_model: str, fallback_chain: tuple[str, ...]) -> tuple[str, ...]:
    return _parse_model_fallback_chain((effective_model, *fallback_chain))


def _effective_max_context_chars(raw_override: str) -> int:
    if str(raw_override or "").strip():
        return int(str(raw_override).strip())
    return DEFAULT_MAX_CONTEXT_CHARS


def _available_backends(values: dict[str, Any]) -> list[str]:
    available: list[str] = []
    if values["opencode_api_key"]:
        available.append(BACKEND_OPENCODE_API)
    if values["nvidia_nim_api_key"]:
        available.append(BACKEND_NVIDIA_NIM_API)
    if values["openrouter_api_key"]:
        available.append(BACKEND_OPENROUTER_API)
    if values["anthropic_api_key"]:
        available.append(BACKEND_ANTHROPIC_API)
    if values["api_key"]:
        available.append(BACKEND_OPENAI_API)
    if values["codex_path"]:
        available.append(BACKEND_CODEX_CLI)
    if values["copilot_path"]:
        available.append(BACKEND_COPILOT_CLI)
    if values["claude_path"]:
        available.append(BACKEND_CLAUDE_CLI)
    return available


def _missing_items(values: dict[str, Any]) -> list[str]:
    requested = values["requested_backend"]
    missing: list[str] = []
    if not requested:
        missing.append("Explicit `AIWIKI_LLM_BACKEND` selection")
        return missing
    if requested == BACKEND_CODEX_CLI and not values["codex_path"]:
        missing.append(f"CLI command `{values['codex_command']}`")
    elif requested == BACKEND_NVIDIA_NIM_API and not values["nvidia_nim_api_key"]:
        missing.append("NVIDIA NIM key via AIWIKI_NVIDIA_NIM_API_KEY|NVIDIA_NIM_API_KEY")
    elif requested == BACKEND_OPENCODE_API and not values["opencode_api_key"]:
        missing.append("OpenCode API key via AIWIKI_OPENCODE_API_KEY|AIWIKI_LLM_API_KEY")
    elif requested == BACKEND_OPENROUTER_API and not values["openrouter_api_key"]:
        missing.append("OpenRouter API key via AIWIKI_OPENROUTER_API_KEY")
    elif requested == BACKEND_OPENAI_API and not values["api_key"]:
        missing.append("OpenAI-compatible key via AIWIKI_LLM_API_KEY|OPENAI_API_KEY")
    elif requested == BACKEND_ANTHROPIC_API and not values["anthropic_api_key"]:
        missing.append("Anthropic API key via AIWIKI_ANTHROPIC_API_KEY|ANTHROPIC_API_KEY")
    elif requested == BACKEND_COPILOT_CLI and not values["copilot_path"]:
        missing.append(f"CLI command `{values['copilot_command']}`")
    elif requested == BACKEND_CLAUDE_CLI and not values["claude_path"]:
        missing.append(f"CLI command `{values['claude_command']}`")
    return missing


def _missing_backend_message(values: dict[str, Any]) -> str:
    requested = values["requested_backend"]
    available = _available_backends(values)
    if not requested:
        if available:
            return (
                "No LLM backend selected. "
                f"Set `AIWIKI_LLM_BACKEND` explicitly to one of: {', '.join(available)}."
            )
        return (
            "No LLM backend selected. "
            "Configure one of `opencode-api|nvidia-nim-api|openrouter-api|anthropic-api|openai-api|"
            "codex-cli|copilot-cli|claude-cli`, "
            "then set `AIWIKI_LLM_BACKEND` explicitly."
        )
    if available:
        return (
            "LLM backend resolution failed. "
            f"Requested `{requested}` but available backends are: {', '.join(available)}."
        )
    return (
        "LLM backend resolution failed. "
        f"Requested `{requested}` but its required CLI/key is unavailable."
    )


def _auth_mode_for_backend(backend: str) -> str:
    if backend in {BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI}:
        return "cli-session"
    if backend in {BACKEND_OPENCODE_API, BACKEND_OPENROUTER_API, BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API, BACKEND_NVIDIA_NIM_API}:
        return "api-key"
    return ""


def _usage_visibility_for_backend(backend: str) -> str:
    if backend in {BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI}:
        return "opaque-cli"
    if backend in {BACKEND_OPENCODE_API, BACKEND_OPENROUTER_API, BACKEND_OPENAI_API, BACKEND_ANTHROPIC_API, BACKEND_NVIDIA_NIM_API}:
        return "response-usage"
    return ""


def _usage_accounting_for_backend(backend: str) -> str:
    if backend == BACKEND_CODEX_CLI:
        return "codex-cli-session"
    if backend == BACKEND_COPILOT_CLI:
        return "copilot-cli-session"
    if backend == BACKEND_CLAUDE_CLI:
        return "claude-cli-session"
    if backend == BACKEND_OPENCODE_API:
        return "opencode-api"
    if backend == BACKEND_OPENROUTER_API:
        return "openrouter-api"
    if backend == BACKEND_OPENAI_API:
        return "openai-compatible-api"
    if backend == BACKEND_ANTHROPIC_API:
        return "anthropic-api"
    if backend == BACKEND_NVIDIA_NIM_API:
        return "nvidia-nim-api"
    return ""


_IMAGE_MODEL_MARKERS = (
    "vision",
    "image",
    "multimodal",
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o3",
    "o4",
    "claude",
    "gemini",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "llava",
    "vila",
    "pixtral",
    "mistral-small-3.2",
)
_TEXT_ONLY_MODEL_MARKERS = (
    "gpt-oss",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
)


def _backend_supports_image_analysis(backend: str, model: str = "") -> bool:
    normalized_backend = str(backend or "").strip()
    normalized_model = str(model or "").strip().lower()
    if normalized_backend == BACKEND_CODEX_CLI:
        return True
    if normalized_backend == BACKEND_ANTHROPIC_API:
        return bool(normalized_model and "claude" in normalized_model)
    if normalized_backend in {BACKEND_OPENCODE_API, BACKEND_OPENROUTER_API, BACKEND_OPENAI_API, BACKEND_NVIDIA_NIM_API}:
        if not normalized_model:
            return False
        if any(marker in normalized_model for marker in _TEXT_ONLY_MODEL_MARKERS):
            return False
        return any(marker in normalized_model for marker in _IMAGE_MODEL_MARKERS)
    return False


def _resolve_nvidia_nim_api_key() -> tuple[str, str]:
    for env_name in ("AIWIKI_NVIDIA_NIM_API_KEY", "NVIDIA_NIM_API_KEY"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value, env_name
    return "", ""


def _resolve_opencode_api_key() -> tuple[str, str]:
    for env_name in ("AIWIKI_OPENCODE_API_KEY", "AIWIKI_LLM_API_KEY"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value, env_name
    return "", ""


def _resolve_openrouter_api_key() -> tuple[str, str]:
    for env_name in ("AIWIKI_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"):
        value = (os.environ.get(env_name) or "").strip()
        if value:
            return value, env_name
    return "", ""
