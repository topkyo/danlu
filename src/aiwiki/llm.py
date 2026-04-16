"""LLM backends for aiwiki."""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from .config import BACKEND_ANTHROPIC_API, BACKEND_CLAUDE_CLI, BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig


class LLMError(RuntimeError):
    """Raised when the configured LLM backend fails or returns invalid output."""


@dataclass
class CompletionResult:
    text: str
    response_id: str
    usage: dict[str, Any]


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
                cwd=self.workdir,
                timeout=self.config.timeout_seconds,
                check=False,
            )
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


def create_backend_client(config: LLMConfig, workdir: Path) -> Any:
    if config.backend == BACKEND_OPENAI_API:
        return OpenAICompatClient(config)
    if config.backend == BACKEND_ANTHROPIC_API:
        return AnthropicClient(config)
    if config.backend == BACKEND_CODEX_CLI:
        return CodexCLIClient(config, workdir)
    if config.backend == BACKEND_CLAUDE_CLI:
        return ClaudeCLIClient(config, workdir)
    raise LLMError(f"Unsupported backend `{config.backend}`.")


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
