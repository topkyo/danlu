"""LLM backends for aiwiki."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import socket
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error

from aiwiki.utils.io import atomic_write_text, is_atomic_write_tmp_path
from aiwiki.utils.security import FetchPolicyError, safe_fetch

from .config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_DEEPSEEK_API,
    BACKEND_OPENAI_API,
    BACKEND_OPENCODE_API,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENCODE_MODEL,
    LLMConfig,
)

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the configured LLM backend fails or returns invalid output."""

    def __init__(self, message: str, *, raw_response_path: str | None = None) -> None:
        super().__init__(message)
        self.raw_response_path = raw_response_path


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
    raw_response_path: str | None = None
    web_search_used: bool = False
    used_web_refs: tuple[str, ...] = ()
    web_search_calls: tuple[dict[str, Any], ...] = ()


PROBE_SYSTEM_PROMPT = "You are a backend health probe. Reply with exactly OK."
PROBE_USER_PROMPT = "Reply with exactly OK."
FRONTMATTER_PROBE_SYSTEM_PROMPT = (
    "You are a backend compatibility probe. Respond with the exact markdown frontmatter block the user requests."
)
FRONTMATTER_PROBE_USER_PROMPT = """Respond with exactly the following text, nothing else, no decoration, no commentary:
---
title: probe
---
ok"""
_LLM_MAX_BYTES = 10 * 1024 * 1024
_LLM_RAW_RESPONSE_KEEP = 500
_RETRYABLE_HTTP_STATUS_CODES = {429, 500, 502, 503, 504}


def _llm_retry_attempts() -> int:
    raw = os.environ.get("AIWIKI_LLM_RETRY_ATTEMPTS", "2").strip()
    try:
        return max(0, min(5, int(raw)))
    except ValueError:
        return 2


def _http_retry_delay_seconds(exc: error.HTTPError, attempt_index: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return max(0.0, min(30.0, float(retry_after)))
        except ValueError:
            pass
    return min(12.0, 2.0 * (attempt_index + 1))


class OpenAICompatClient:
    """Call an OpenAI-compatible `/chat/completions` endpoint without extra dependencies."""

    def __init__(self, config: LLMConfig, workdir: Path | None = None) -> None:
        self.config = config
        self.workdir = workdir or Path.cwd()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        raw = self._post_chat_completions(payload)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raw_response_path = _write_raw_response(self.workdir, raw)
            raise LLMError("LLM endpoint returned invalid JSON.", raw_response_path=raw_response_path) from exc

        try:
            text = _extract_content(parsed)
        except LLMError as exc:
            exc.raw_response_path = exc.raw_response_path or _write_raw_response(self.workdir, raw)
            raise
        if not text.strip():
            raw_response_path = _write_raw_response(self.workdir, text)
            raise LLMError("LLM endpoint returned empty content.", raw_response_path=raw_response_path)
        raw_response_path = _write_raw_response(self.workdir, text)
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
            raw_response_path=raw_response_path,
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
        raw = self._post_chat_completions(payload)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raw_response_path = _write_raw_response(self.workdir, raw)
            raise LLMError("LLM endpoint returned invalid JSON.", raw_response_path=raw_response_path) from exc

        try:
            text = _extract_content(parsed)
        except LLMError as exc:
            exc.raw_response_path = exc.raw_response_path or _write_raw_response(self.workdir, raw)
            raise
        if not text.strip():
            raw_response_path = _write_raw_response(self.workdir, text)
            raise LLMError("LLM endpoint returned empty content.", raw_response_path=raw_response_path)
        raw_response_path = _write_raw_response(self.workdir, text)
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
            raw_response_path=raw_response_path,
        )

    def _post_chat_completions(self, payload: dict[str, Any]) -> str:
        endpoint = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        retry_attempts = _llm_retry_attempts()
        for attempt_index in range(retry_attempts + 1):
            try:
                response_body, _ = safe_fetch(
                    endpoint,
                    method="POST",
                    data=body,
                    headers=headers,
                    max_bytes=_LLM_MAX_BYTES,
                    timeout=self.config.timeout_seconds,
                )
                raw = response_body.decode("utf-8")
                break
            except FetchPolicyError as exc:
                raise LLMError(f"unsafe LLM endpoint: {exc}") from exc
            except (TimeoutError, socket.timeout) as exc:
                raise LLMError(f"LLM endpoint timed out after {self.config.timeout_seconds} seconds.") from exc
            except error.HTTPError as exc:  # pragma: no cover - exercised via CLI/network usage
                details = exc.read().decode("utf-8", errors="replace")
                if exc.code in _RETRYABLE_HTTP_STATUS_CODES and attempt_index < retry_attempts:
                    time.sleep(_http_retry_delay_seconds(exc, attempt_index))
                    continue
                raise LLMError(f"HTTP {exc.code} from LLM endpoint: {details}") from exc
            except error.URLError as exc:  # pragma: no cover - exercised via CLI/network usage
                raise LLMError(f"Unable to reach LLM endpoint: {exc.reason}") from exc
        else:  # pragma: no cover - loop either breaks or raises
            raise LLMError("LLM endpoint did not return a response.")
        return raw


class AnthropicClient:
    """Call the Anthropic Messages API directly."""

    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, config: LLMConfig, workdir: Path | None = None) -> None:
        self.config = config
        self.workdir = workdir or Path.cwd()

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
        headers = {
            "x-api-key": self.config.anthropic_api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

        try:
            response_body, _ = safe_fetch(
                endpoint,
                method="POST",
                data=body,
                headers=headers,
                max_bytes=_LLM_MAX_BYTES,
                timeout=self.config.timeout_seconds,
            )
            raw = response_body.decode("utf-8")
        except FetchPolicyError as exc:
            raise LLMError(f"unsafe LLM endpoint: {exc}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError(f"Anthropic endpoint timed out after {self.config.timeout_seconds} seconds.") from exc
        except error.HTTPError as exc:  # pragma: no cover - exercised via CLI/network usage
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"HTTP {exc.code} from Anthropic endpoint: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - exercised via CLI/network usage
            raise LLMError(f"Unable to reach Anthropic endpoint: {exc.reason}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raw_response_path = _write_raw_response(self.workdir, raw)
            raise LLMError("Anthropic endpoint returned invalid JSON.", raw_response_path=raw_response_path) from exc

        try:
            text = _extract_anthropic_content(parsed)
        except LLMError as exc:
            exc.raw_response_path = exc.raw_response_path or _write_raw_response(self.workdir, raw)
            raise
        if not text.strip():
            raw_response_path = _write_raw_response(self.workdir, text)
            raise LLMError("Anthropic endpoint returned empty content.", raw_response_path=raw_response_path)
        raw_response_path = _write_raw_response(self.workdir, text)
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
            raw_response_path=raw_response_path,
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
    # M7.4a Kill Switch: external LLM hook. Defer import to avoid cycles.
    from aiwiki import autonomy_policy

    reason = autonomy_policy.disabled_reason(workdir, "disable_external_llm")
    if reason is not None:
        raise AutonomyDisabled(reason)

    return _instantiate_cli_client(_config_for_backend(config, config.backend), workdir)


def probe_backend(config: LLMConfig, workdir: Path, timeout_seconds: int | None = None) -> dict[str, Any]:
    probe_config = config
    if timeout_seconds is not None:
        probe_config = replace(config, timeout_seconds=timeout_seconds)
    started = time.monotonic()
    client: Any | None = None
    try:
        client = create_backend_client(probe_config, workdir)
        assert client is not None
        result = client.complete(FRONTMATTER_PROBE_SYSTEM_PROMPT, FRONTMATTER_PROBE_USER_PROMPT)
    except LLMError as exc:
        effective_config = getattr(client, "config", probe_config) if client is not None else probe_config
        error_class = classify_backend_error(str(exc))
        compatibility = "requires_credential" if _is_auth_error(str(exc)) else "unavailable"
        return {
            "ok": False,
            "status": compatibility,
            "backend_requested": probe_config.backend_requested or probe_config.backend,
            "backend": effective_config.backend,
            "model_requested": probe_config.model_requested,
            "model": effective_config.model,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "response_preview": "",
            "matched_expected_output": False,
            "error": str(exc),
            "compatibility": compatibility,
            "error_class": error_class,
            "raw_response_path": exc.raw_response_path or "",
            "compatibility_hint": str(exc),
        }

    effective_config = getattr(client, "config", probe_config)
    response_text = result.text.strip()
    is_compatible, compatibility_hint = _validate_frontmatter_probe_response(result.text)
    compatibility = "compatible" if is_compatible else "degraded"
    return {
        "ok": compatibility == "compatible",
        "status": compatibility,
        "backend_requested": probe_config.backend_requested or probe_config.backend,
        "backend": effective_config.backend,
        "model_requested": probe_config.model_requested,
        "model": effective_config.model,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "response_preview": _response_preview(response_text),
        "matched_expected_output": compatibility == "compatible",
        "error": "",
        "compatibility": compatibility,
        "error_class": "",
        "raw_response_path": result.raw_response_path or "",
        "compatibility_hint": compatibility_hint,
    }


def probe_available_backends(
    config: LLMConfig, workdir: Path, timeout_seconds: int | None = None
) -> list[dict[str, Any]]:
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
        BACKEND_DEEPSEEK_API,
        BACKEND_OPENCODE_API,
        BACKEND_ANTHROPIC_API,
        BACKEND_OPENAI_API,
    ):
        if backend in ordered:
            continue
        if backend == BACKEND_DEEPSEEK_API and config.deepseek_api_key:
            ordered.append(backend)
        elif backend == BACKEND_OPENCODE_API and config.opencode_api_key:
            ordered.append(backend)
        elif backend == BACKEND_ANTHROPIC_API and config.anthropic_api_key:
            ordered.append(backend)
        elif backend == BACKEND_OPENAI_API and config.api_key:
            ordered.append(backend)
    return ordered


def _config_for_backend(config: LLMConfig, backend: str) -> LLMConfig:
    if backend == config.backend:
        model = config.model or _effective_backend_default_model(backend, config)
    elif backend == BACKEND_DEEPSEEK_API:
        model = DEFAULT_DEEPSEEK_MODEL
    elif backend == BACKEND_OPENCODE_API:
        model = DEFAULT_OPENCODE_MODEL
    elif backend == BACKEND_OPENAI_API:
        model = config.model or ""
    elif backend == BACKEND_ANTHROPIC_API:
        model = config.model or ""
    else:
        model = ""
    if backend == BACKEND_DEEPSEEK_API:
        return replace(
            config,
            backend=backend,
            model=model,
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )
    if backend == BACKEND_OPENCODE_API:
        return replace(
            config,
            backend=backend,
            model=model,
            api_key=config.opencode_api_key,
            base_url=config.opencode_base_url,
        )
    return replace(config, backend=backend, model=model)


def _effective_backend_default_model(backend: str, config: LLMConfig) -> str:
    if backend == BACKEND_DEEPSEEK_API:
        return DEFAULT_DEEPSEEK_MODEL
    if backend == BACKEND_OPENCODE_API:
        return DEFAULT_OPENCODE_MODEL
    return config.model or ""


def _instantiate_cli_client(config: LLMConfig, workdir: Path) -> Any:
    from aiwiki.llm_responses import DeepSeekResponsesClient, supports_web_search

    if supports_web_search(config.backend, config.model):
        return DeepSeekResponsesClient(config, workdir)
    if config.backend in {BACKEND_DEEPSEEK_API, BACKEND_OPENCODE_API, BACKEND_OPENAI_API}:
        return OpenAICompatClient(config, workdir)
    if config.backend == BACKEND_ANTHROPIC_API:
        return AnthropicClient(config, workdir)
    raise LLMError(f"Unsupported backend `{config.backend}`.")


def supports_web_search(backend: str, model: str) -> bool:
    """Return True when the backend/model pair may use DeepSeek Responses web_search."""

    from aiwiki.llm_responses import supports_web_search as _supports_web_search

    return _supports_web_search(backend, model)


def _is_auth_error(message: str) -> bool:
    text = str(message or "").lower()
    return any(
        pattern in text
        for pattern in (
            "unauthorized",
            "not signed in",
            "not logged in",
            "please login",
            "api key",
            "api_key",
            "authentication",
            "forbidden",
            "permission",
            "organization",
            "401",
            "403",
            "expired token",
            "invalid token",
        )
    )


def _validate_frontmatter_probe_response(text: str) -> tuple[bool, str]:
    raw_text = str(text or "")
    if not raw_text.strip():
        return False, "empty response"
    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("●"):
            return False, "decoration prefix detected: ●"
        if stripped.startswith("▶"):
            return False, "decoration prefix detected: ▶"
    lines = raw_text.splitlines()
    first_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_index is None:
        return False, "empty response"
    first_line = lines[first_index].strip()
    if first_line != "---":
        return False, f"missing opening frontmatter fence; first line: {repr(first_line[:80])}"
    closing_index: int | None = None
    for index in range(first_index + 1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index is None:
        return False, "missing closing frontmatter fence"
    frontmatter_lines = lines[first_index + 1 : closing_index]
    if not any(line.strip() == "title: probe" for line in frontmatter_lines):
        return False, "frontmatter missing 'title: probe'"
    body = "\n".join(lines[closing_index + 1 :]).strip()
    if "ok" not in body:
        return False, "body missing 'ok' marker"
    return True, ""


def _write_raw_response(root: Path, raw_text: str) -> str:
    """Best-effort persistence for one LLM raw response body."""

    text = str(raw_text or "")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(":", "")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    relative = Path(".aiwiki") / "llm-responses" / f"{timestamp}-{digest}.txt"
    path = root / relative
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)
    except OSError as exc:  # pragma: no cover - environment dependent best-effort path
        return f"write_failed:{exc}"
    # Best-effort rotation: filenames start with a fixed-width UTC timestamp, so
    # lexicographic order is chronological. Pruning must never break the write path.
    try:
        files = sorted(
            item for item in path.parent.iterdir() if item.is_file() and not is_atomic_write_tmp_path(item)
        )
        overflow = len(files) - _LLM_RAW_RESPONSE_KEEP
        for stale in files[: max(0, overflow)]:
            stale.unlink()
    except OSError as exc:
        logger.warning("failed to prune LLM raw responses in %s: %s", path.parent, exc)
    return relative.as_posix()


def _classify_backend_error(message: str) -> str:
    text = str(message or "").lower()
    if any(
        pattern in text
        for pattern in ("usage limit", "rate limit", "upgrade to pro", "purchase more credits", "quota", "402")
    ):
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
