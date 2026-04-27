"""LLM backends for aiwiki."""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib import error, request

from .config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_CLAUDE_CLI,
    BACKEND_CODEX_CLI,
    BACKEND_COPILOT_CLI,
    BACKEND_NVIDIA_NIM_API,
    BACKEND_OPENAI_API,
    DEFAULT_CODEX_MODEL,
    DEFAULT_NVIDIA_NIM_MODEL,
    LLMConfig,
)


class LLMError(RuntimeError):
    """Raised when the configured LLM backend fails or returns invalid output."""


class AutonomyDisabled(LLMError):
    """Raised when an autonomy-policy kill switch blocks an external LLM call.

    Subclass of LLMError so that all existing callers (which already handle
    LLMError) get clean structured failure without bespoke wiring. Distinguish
    via ``isinstance(exc, AutonomyDisabled)`` when reason matters.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"external LLM disabled by autonomy policy: {reason}")
        self.reason = reason


@dataclass
class CompletionResult:
    text: str
    response_id: str
    usage: dict[str, Any]


PROBE_SYSTEM_PROMPT = "You are a backend health probe. Reply with exactly OK."
PROBE_USER_PROMPT = "Reply with exactly OK."


class OpenAICompatClient:
    """Call an OpenAI-compatible `/chat/completions` endpoint without extra dependencies."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        endpoint = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - exercised via CLI/network usage
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code} from LLM endpoint: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Unable to reach LLM endpoint: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM endpoint returned invalid JSON.") from exc

        text = _extract_content(parsed)
        if not text.strip():
            raise LLMError("LLM endpoint returned empty content.")
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
        )

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        mime_type = _guess_image_mime_type(image_path)
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}",
                            },
                        },
                    ],
                },
            ],
        }
        endpoint = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - exercised via CLI/network usage
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code} from LLM endpoint: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Unable to reach LLM endpoint: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM endpoint returned invalid JSON.") from exc

        text = _extract_content(parsed)
        if not text.strip():
            raise LLMError("LLM endpoint returned empty content.")
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
        )


class CodexCLIClient:
    """Use the local Codex CLI as the generation backend."""

    def __init__(self, config: LLMConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        full_prompt = "\n\n".join(
            [
                "# System Instructions",
                system_prompt,
                "",
                "# Task",
                user_prompt,
            ]
        )
        with tempfile.NamedTemporaryFile(prefix="aiwiki-codex-", suffix=".md", delete=False) as handle:
            output_path = Path(handle.name)
        command = [
            self.config.codex_path or self.config.codex_command,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(self.workdir),
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        if self.config.codex_reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{self.config.codex_reasoning_effort}"'])
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.append("-")
        try:
            completed = subprocess.run(
                command,
                input=full_prompt,
                text=True,
                capture_output=True,
                cwd=self.workdir,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Codex CLI timed out after {self.config.timeout_seconds} seconds.") from exc
        except OSError as exc:  # pragma: no cover - exercised by environment failures
            raise LLMError(f"Failed to launch Codex CLI: {exc}") from exc
        finally:
            text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
            output_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip() or text.strip()
            raise LLMError(f"Codex CLI failed with exit code {completed.returncode}: {details}")
        final_text = text.strip() or completed.stdout.strip()
        if not final_text:
            raise LLMError("Codex CLI returned no final content.")
        return CompletionResult(text=final_text, response_id="codex-cli", usage={})

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        full_prompt = "\n\n".join(
            [
                "# System Instructions",
                system_prompt,
                "",
                "# Task",
                user_prompt,
            ]
        )
        with tempfile.NamedTemporaryFile(prefix="aiwiki-codex-", suffix=".md", delete=False) as handle:
            output_path = Path(handle.name)
        command = [
            self.config.codex_path or self.config.codex_command,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            str(self.workdir),
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
            "--image",
            str(image_path),
        ]
        if self.config.codex_reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{self.config.codex_reasoning_effort}"'])
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.append("-")
        try:
            completed = subprocess.run(
                command,
                input=full_prompt,
                text=True,
                capture_output=True,
                cwd=self.workdir,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Codex CLI timed out after {self.config.timeout_seconds} seconds.") from exc
        except OSError as exc:  # pragma: no cover - exercised by environment failures
            raise LLMError(f"Failed to launch Codex CLI: {exc}") from exc
        finally:
            text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
            output_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip() or text.strip()
            raise LLMError(f"Codex CLI failed with exit code {completed.returncode}: {details}")
        final_text = text.strip() or completed.stdout.strip()
        if not final_text:
            raise LLMError("Codex CLI returned no final content.")
        return CompletionResult(text=final_text, response_id="codex-cli", usage={})


class ClaudeCLIClient:
    """Use the local Claude CLI as the generation backend."""

    def __init__(self, config: LLMConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        command = [
            self.config.claude_path or self.config.claude_command,
            "--print",
            "--output-format",
            "text",
            "--permission-mode",
            "bypassPermissions",
            "--tools",
            "",
            "--add-dir",
            str(self.workdir),
            "--system-prompt",
            system_prompt,
        ]
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.append(user_prompt)
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                cwd=self.workdir,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Claude CLI timed out after {self.config.timeout_seconds} seconds.") from exc
        except OSError as exc:  # pragma: no cover - exercised by environment failures
            raise LLMError(f"Failed to launch Claude CLI: {exc}") from exc

        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise LLMError(f"Claude CLI failed with exit code {completed.returncode}: {details}")
        final_text = completed.stdout.strip()
        if not final_text:
            raise LLMError("Claude CLI returned no final content.")
        return CompletionResult(text=final_text, response_id="claude-cli", usage={})

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        raise LLMError("Claude CLI image analysis is not supported by aiwiki yet.")


class CopilotCLIClient:
    """Use the local GitHub Copilot CLI in non-interactive prompt mode."""

    def __init__(self, config: LLMConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        full_prompt = "\n\n".join(
            [
                "# System Instructions",
                system_prompt,
                "",
                "# Task",
                user_prompt,
            ]
        )
        command = [
            self.config.copilot_path or self.config.copilot_command,
            "--prompt",
            full_prompt,
            "--silent",
            "--output-format",
            "text",
            "--stream",
            "off",
            "--no-ask-user",
            "--no-color",
            "--allow-tool=read",
            "--add-dir",
            str(self.workdir),
        ]
        if self.config.model:
            command.extend(["--model", self.config.model])
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                cwd=self.workdir,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Copilot CLI timed out after {self.config.timeout_seconds} seconds.") from exc
        except OSError as exc:  # pragma: no cover - exercised by environment failures
            raise LLMError(f"Failed to launch Copilot CLI: {exc}") from exc

        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise LLMError(f"Copilot CLI failed with exit code {completed.returncode}: {details}")
        final_text = completed.stdout.strip()
        if not final_text:
            raise LLMError("Copilot CLI returned no final content.")
        return CompletionResult(text=final_text, response_id="copilot-cli", usage={})

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        del system_prompt
        del user_prompt
        del image_path
        raise LLMError("Copilot CLI image analysis is not supported by aiwiki yet.")


class AnthropicClient:
    """Call the Anthropic Messages API directly."""

    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def _call_messages(self, system_prompt: str, content: list[dict[str, Any]] | str) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": 4096,
            "temperature": self.config.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
        }
        endpoint = f"{self.config.anthropic_base_url}/v1/messages"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            headers={
                "x-api-key": self.config.anthropic_api_key,
                "anthropic-version": self.ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - exercised via CLI/network usage
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code} from Anthropic endpoint: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Unable to reach Anthropic endpoint: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("Anthropic endpoint returned invalid JSON.") from exc

        text = _extract_anthropic_content(parsed)
        if not text.strip():
            raise LLMError("Anthropic endpoint returned empty content.")
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
        )

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        return self._call_messages(system_prompt, user_prompt)

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        mime_type = _guess_image_mime_type(image_path)
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": encoded,
                },
            },
            {"type": "text", "text": user_prompt},
        ]
        return self._call_messages(system_prompt, content)


class ModelFallbackClient:
    """Retry the same backend with alternate default models when the primary model is unavailable or invalid."""

    def __init__(self, config: LLMConfig, workdir: Path, configs: list[LLMConfig]) -> None:
        self.primary_config = config
        self.config = configs[0] if configs else config
        self.workdir = workdir
        self.client_configs = configs or [config]
        self.clients = [_instantiate_cli_client(candidate, workdir) for candidate in self.client_configs]
        self.index = 0

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        return self._run_with_fallback("complete", system_prompt, user_prompt)

    def analyze_image(self, system_prompt: str, user_prompt: str, image_path: Path) -> CompletionResult:
        return self._run_with_fallback("analyze_image", system_prompt, user_prompt, image_path)

    def advance_model(self) -> bool:
        if self.index >= len(self.clients) - 1:
            return False
        self.index += 1
        self.config = getattr(self.clients[self.index], "config", self.client_configs[self.index])
        return True

    def _run_with_fallback(self, method_name: str, *args: Any) -> CompletionResult:
        last_error: LLMError | None = None
        while self.index < len(self.clients):
            client = self.clients[self.index]
            method = getattr(client, method_name)
            try:
                result = method(*args)
            except LLMError as exc:
                last_error = exc
                if self.index == len(self.clients) - 1 or not _is_model_fallback_error(str(exc)):
                    raise
                self.advance_model()
                continue
            self.config = getattr(client, "config", self.client_configs[self.index])
            return result
        if last_error is not None:
            raise last_error
        raise LLMError("No usable model fallback candidate was configured.")


def create_backend_client(config: LLMConfig, workdir: Path) -> Any:
    # M7.4a Kill Switch: external LLM hook. Defer import to avoid cycles.
    from aiwiki import autonomy_policy

    reason = autonomy_policy.disabled_reason(workdir, "disable_external_llm")
    if reason is not None:
        raise AutonomyDisabled(reason)

    model_fallback_configs = _model_fallback_configs(config)
    if len(model_fallback_configs) > 1:
        return ModelFallbackClient(config, workdir, model_fallback_configs)
    if config.backend == BACKEND_OPENAI_API:
        return OpenAICompatClient(config)
    if config.backend == BACKEND_ANTHROPIC_API:
        return AnthropicClient(config)
    if config.backend == BACKEND_NVIDIA_NIM_API:
        return OpenAICompatClient(config)
    if config.backend == BACKEND_CODEX_CLI:
        return CodexCLIClient(config, workdir)
    if config.backend == BACKEND_COPILOT_CLI:
        return CopilotCLIClient(config, workdir)
    if config.backend == BACKEND_CLAUDE_CLI:
        return ClaudeCLIClient(config, workdir)
    raise LLMError(f"Unsupported backend `{config.backend}`.")


def probe_backend(config: LLMConfig, workdir: Path, timeout_seconds: int | None = None) -> dict[str, Any]:
    probe_config = config
    if timeout_seconds is not None:
        probe_config = replace(config, timeout_seconds=timeout_seconds)
    client = create_backend_client(probe_config, workdir)
    started = time.monotonic()
    try:
        result = client.complete(PROBE_SYSTEM_PROMPT, PROBE_USER_PROMPT)
    except LLMError as exc:
        effective_config = getattr(client, "config", probe_config)
        return {
            "ok": False,
            "status": _classify_backend_error(str(exc)),
            "backend_requested": probe_config.backend_requested or probe_config.backend,
            "backend": effective_config.backend,
            "model_requested": probe_config.model_requested,
            "model": effective_config.model,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "response_preview": "",
            "matched_expected_output": False,
            "error": str(exc),
        }

    effective_config = getattr(client, "config", probe_config)
    response_text = result.text.strip()
    return {
        "ok": True,
        "status": "ok",
        "backend_requested": probe_config.backend_requested or probe_config.backend,
        "backend": effective_config.backend,
        "model_requested": probe_config.model_requested,
        "model": effective_config.model,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "response_preview": _response_preview(response_text),
        "matched_expected_output": response_text == "OK",
        "error": "",
    }


def probe_available_backends(config: LLMConfig, workdir: Path, timeout_seconds: int | None = None) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for backend in _available_probe_backends(config):
        probe_config = replace(
            _config_for_backend(config, backend),
            backend_requested=backend,
        )
        probes.append(probe_backend(probe_config, workdir, timeout_seconds=timeout_seconds))
    return probes


def _available_probe_backends(config: LLMConfig) -> list[str]:
    ordered: list[str] = []
    for backend in (
        config.backend,
        BACKEND_CODEX_CLI,
        BACKEND_COPILOT_CLI,
        BACKEND_CLAUDE_CLI,
        BACKEND_NVIDIA_NIM_API,
    ):
        if backend in ordered:
            continue
        if backend == BACKEND_CODEX_CLI and config.codex_path:
            ordered.append(backend)
        elif backend == BACKEND_COPILOT_CLI and config.copilot_path:
            ordered.append(backend)
        elif backend == BACKEND_CLAUDE_CLI and config.claude_path:
            ordered.append(backend)
        elif backend == BACKEND_NVIDIA_NIM_API and config.nvidia_nim_api_key:
            ordered.append(backend)
    return ordered


def _config_for_backend(config: LLMConfig, backend: str) -> LLMConfig:
    model_requested = config.model_requested.strip()
    if model_requested:
        model = model_requested
    elif backend == BACKEND_CODEX_CLI:
        model = DEFAULT_CODEX_MODEL
    elif backend == BACKEND_NVIDIA_NIM_API:
        model = DEFAULT_NVIDIA_NIM_MODEL
    else:
        model = ""
    if backend == BACKEND_NVIDIA_NIM_API:
        return replace(
            config,
            backend=backend,
            model=model,
            api_key=config.nvidia_nim_api_key,
            base_url=config.nvidia_nim_base_url,
        )
    return replace(config, backend=backend, model=model)


def _instantiate_cli_client(config: LLMConfig, workdir: Path) -> Any:
    if config.backend == BACKEND_CODEX_CLI:
        return CodexCLIClient(config, workdir)
    if config.backend == BACKEND_NVIDIA_NIM_API:
        return OpenAICompatClient(config)
    if config.backend == BACKEND_COPILOT_CLI:
        return CopilotCLIClient(config, workdir)
    if config.backend == BACKEND_CLAUDE_CLI:
        return ClaudeCLIClient(config, workdir)
    raise LLMError(f"Unsupported backend `{config.backend}`.")


def _model_fallback_configs(config: LLMConfig) -> list[LLMConfig]:
    candidate_models = list(config.model_fallback_chain)
    if len(candidate_models) <= 1:
        return [_config_for_backend(config, config.backend)]
    base_config = _config_for_backend(config, config.backend)
    return [replace(base_config, model=model) for model in candidate_models]


def _is_model_fallback_error(message: str) -> bool:
    text = str(message or "").lower()
    if _classify_backend_error(text) in {"quota", "timeout", "unavailable"}:
        return True
    return any(pattern in text for pattern in ("unknown model", "unsupported model", "model_not_found"))


def advance_client_model(client: Any) -> bool:
    clients = getattr(client, "clients", None)
    client_configs = getattr(client, "client_configs", None)
    if isinstance(clients, list) and len(clients) <= 1:
        return False
    if isinstance(client_configs, list) and len(client_configs) <= 1:
        return False
    advance = getattr(client, "advance_model", None)
    if callable(advance):
        return bool(advance())
    return False


def _classify_backend_error(message: str) -> str:
    text = str(message or "").lower()
    if any(pattern in text for pattern in ("usage limit", "rate limit", "upgrade to pro", "purchase more credits", "quota", "402")):
        return "quota"
    if any(pattern in text for pattern in ("timed out", "timeout")):
        return "timeout"
    if any(
        pattern in text
        for pattern in (
            "not logged",
            "authentication",
            "auth",
            "forbidden",
            "unauthorized",
            "permission",
            "access",
            "login required",
        )
    ):
        return "auth"
    if any(pattern in text for pattern in ("temporarily unavailable", "unavailable", "unable to reach", "connection")):
        return "unavailable"
    return "error"


def classify_backend_error(message: str) -> str:
    """Expose stable backend error classification for shell-facing summaries."""

    return _classify_backend_error(message)


def _response_preview(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(0, limit - 3)]}..."


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("LLM response is missing `choices`.")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LLMError("LLM response is missing `message`.")
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    raise LLMError("Unsupported message content format from LLM endpoint.")


def _extract_anthropic_content(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise LLMError("Anthropic response is missing `content`.")
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _guess_image_mime_type(image_path: Path) -> str:
    guessed, _ = mimetypes.guess_type(image_path.name)
    return guessed or "image/png"
