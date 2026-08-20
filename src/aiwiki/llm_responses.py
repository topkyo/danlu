"""DeepSeek Responses API client with server-side web_search."""

from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path
from typing import Any
from urllib import error

from aiwiki.utils.security import FetchPolicyError, safe_fetch

from .config import BACKEND_DEEPSEEK_API, WEB_SEARCH_SUPPORTED_MODELS, LLMConfig
from .llm import (
    _LLM_MAX_BYTES,
    _RETRYABLE_HTTP_STATUS_CODES,
    CompletionResult,
    LLMError,
    _http_retry_delay_seconds,
    _llm_retry_attempts,
    _write_raw_response,
)

_URL_PATTERN = re.compile(r"https?://[^\s\])<>\"']+")


def supports_web_search(backend: str, model: str) -> bool:
    """Return True when the backend/model pair may use DeepSeek Responses web_search."""

    return backend == BACKEND_DEEPSEEK_API and model in WEB_SEARCH_SUPPORTED_MODELS


class DeepSeekResponsesClient:
    """Call DeepSeek ``/responses`` with server-side ``web_search``."""

    def __init__(self, config: LLMConfig, workdir: Path | None = None) -> None:
        self.config = config
        self.workdir = workdir or Path.cwd()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        payload = {
            "model": self.config.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "temperature": self.config.temperature,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
        }
        raw = self._post_responses(payload)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raw_response_path = _write_raw_response(self.workdir, raw)
            raise LLMError("LLM endpoint returned invalid JSON.", raw_response_path=raw_response_path) from exc

        try:
            text, web_search_used, used_web_refs, web_search_calls = _parse_responses_payload(parsed)
        except LLMError as exc:
            exc.raw_response_path = exc.raw_response_path or _write_raw_response(self.workdir, raw)
            raise
        if not text.strip():
            raw_response_path = _write_raw_response(self.workdir, raw)
            raise LLMError("LLM endpoint returned empty content.", raw_response_path=raw_response_path)
        raw_response_path = _write_raw_response(self.workdir, raw)
        return CompletionResult(
            text=text,
            response_id=str(parsed.get("id", "")),
            usage=parsed.get("usage") or {},
            raw_response_path=raw_response_path,
            web_search_used=web_search_used,
            used_web_refs=used_web_refs,
            web_search_calls=web_search_calls,
        )

    def _post_responses(self, payload: dict[str, Any]) -> str:
        endpoint = f"{self.config.base_url.rstrip('/')}/responses"
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


def _parse_responses_payload(
    payload: dict[str, Any],
) -> tuple[str, bool, tuple[str, ...], tuple[dict[str, Any], ...]]:
    output = payload.get("output")
    if not isinstance(output, list):
        raise LLMError("LLM response is missing `output`.")

    text_parts: list[str] = []
    web_search_calls: list[dict[str, Any]] = []
    citation_urls: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "message":
            citation_urls.extend(_citation_urls_from_annotations(item.get("annotations")))
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    citation_urls.extend(_citation_urls_from_annotations(part.get("annotations")))
                    if part.get("type") == "output_text":
                        text = part.get("text")
                        if isinstance(text, str):
                            text_parts.append(text)
        elif item_type == "web_search_call":
            web_search_calls.append(_summarize_web_search_call(item))

    text = "".join(text_parts)
    used_web_refs = _dedupe_urls(list(_extract_urls_from_obj(web_search_calls)) + citation_urls)
    web_search_used = bool(web_search_calls) or bool(used_web_refs)
    return text, web_search_used, used_web_refs, tuple(web_search_calls)


def _citation_urls_from_annotations(annotations: Any) -> list[str]:
    if not isinstance(annotations, list):
        return []
    urls: list[str] = []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        if str(annotation.get("type") or "") != "url_citation":
            continue
        for key in ("url", "uri"):
            value = annotation.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(_normalize_url(value))
                break
    return urls


def _web_search_query_text(action_obj: dict[str, Any]) -> str:
    raw_queries = action_obj.get("queries")
    if isinstance(raw_queries, list):
        items = [item.strip() for item in raw_queries if isinstance(item, str)]
    else:
        query = action_obj.get("query")
        items = [query.strip()] if isinstance(query, str) else []
    kept = [item for item in items if item and not item.startswith("ws_call_id=")]
    return " | ".join(kept)


def _summarize_web_search_call(item: dict[str, Any]) -> dict[str, Any]:
    action = item.get("action")
    action_obj = action if isinstance(action, dict) else {}
    urls = _dedupe_urls(_extract_urls_from_obj(action_obj))
    return {
        "id": str(item.get("id") or ""),
        "status": str(item.get("status") or ""),
        "query": _web_search_query_text(action_obj),
        "urls": list(urls),
    }


def _extract_urls_from_text(text: str) -> list[str]:
    return [_normalize_url(match) for match in _URL_PATTERN.findall(str(text or ""))]


def _extract_urls_from_obj(obj: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(obj, str):
        if obj.startswith(("http://", "https://")):
            urls.append(_normalize_url(obj))
        else:
            urls.extend(_extract_urls_from_text(obj))
    elif isinstance(obj, dict):
        for key in ("url", "uri", "link"):
            value = obj.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(_normalize_url(value))
        for value in obj.values():
            urls.extend(_extract_urls_from_obj(value))
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_extract_urls_from_obj(item))
    return urls


def _normalize_url(url: str) -> str:
    value = str(url or "").rstrip(".,);]")
    fragment_at = value.find("#")
    if fragment_at != -1:
        value = value[:fragment_at]
    return value


def _dedupe_urls(urls: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)
