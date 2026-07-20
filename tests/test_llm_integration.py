"""Smoke-level integration tests for the LLM execution layer.

These tests exercise the real ``LLMConfig.from_env()`` + backend client +
``workflows_ask`` state machine paths with mock backends (no real network
calls). They cover the high-risk blind spots that acceptance tests (which use
``ReplayBackend`` stubs for deterministic replay) do not reach:

- ``LLMConfig.from_env()`` env var resolution (backend / model / key / base url / timeout / temperature)
- backend resolution (unknown backend raises, known backend resolves, missing credentials raise)
- ``OpenAICompatClient`` retry loop (retryable HTTP status -> retry -> success)
- timeout / HTTP / network / parse error classification via ``classify_backend_error``
- ``ModelFallbackClient`` model-chain advancement on model-not-found errors
- ``_retry_ask_prompt_profile`` state machine decision (timeout -> lean retry profile)
- ``_mark_run_ask_artifact_degraded`` writes an explicit failure notice (not a fake success)
- ``_complete_run_ask_artifact`` end-to-end state machine: timeout-retry-success and failure-degrade

All tests use ``monkeypatch`` + stdlib only; no third-party mocking libraries.
"""

from __future__ import annotations

import json
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib import error

import pytest

from aiwiki.config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_DEEPSEEK_API,
    BACKEND_OPENAI_API,
    BACKEND_OPENCODE_API,
    DEFAULT_ANTHROPIC_API_MODEL,
    DEFAULT_ANTHROPIC_BASE_URL,
    DEFAULT_BASE_URL,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_API_MODEL,
    DEFAULT_OPENCODE_BASE_URL,
    DEFAULT_OPENCODE_MODEL,
    LLMConfig,
)
from aiwiki.execution.ask import ask_question
from aiwiki.llm import (
    CompletionResult,
    LLMError,
    ModelFallbackClient,
    OpenAICompatClient,
    classify_backend_error,
)
from aiwiki.runner.prompts import _retry_ask_prompt_profile
from aiwiki.runner.workflows_ask import (
    _complete_run_ask_artifact,
    _mark_run_ask_artifact_degraded,
)
from aiwiki.utils.markdown import parse_frontmatter

_LLM_ENV_VARS = (
    "AIWIKI_LLM_BACKEND",
    "AIWIKI_LLM_MODEL",
    "OPENAI_MODEL",
    "AIWIKI_LLM_API_KEY",
    "OPENAI_API_KEY",
    "AIWIKI_DEEPSEEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "AIWIKI_OPENCODE_API_KEY",
    "AIWIKI_ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY",
    "AIWIKI_LLM_BASE_URL",
    "OPENAI_BASE_URL",
    "AIWIKI_DEEPSEEK_BASE_URL",
    "DEEPSEEK_BASE_URL",
    "AIWIKI_OPENCODE_BASE_URL",
    "AIWIKI_ANTHROPIC_BASE_URL",
    "AIWIKI_LLM_TIMEOUT",
    "AIWIKI_LLM_TEMPERATURE",
    "AIWIKI_LLM_MAX_CONTEXT_CHARS",
    "AIWIKI_MODEL_FALLBACK",
    "AIWIKI_REQUIRE_EXPLICIT_MODEL",
    "AIWIKI_LLM_RETRY_ATTEMPTS",
)

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "acceptance" / "M6.1b" / "case_happy_run_ask" / "root"


@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every LLM-related env var before each test so from_env() is deterministic."""

    for name in _LLM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# 1. LLMConfig.from_env() env var resolution
# ---------------------------------------------------------------------------


def test_from_env_resolves_opencode_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "opencode-api")
    monkeypatch.setenv("AIWIKI_OPENCODE_API_KEY", "oc-key-123")
    monkeypatch.setenv("AIWIKI_LLM_MODEL", "deepseek-v4-pro")

    config = LLMConfig.from_env()

    assert config.backend == BACKEND_OPENCODE_API
    assert config.backend_requested == "opencode-api"
    assert config.model == "deepseek-v4-pro"
    assert config.model_requested == "deepseek-v4-pro"
    assert config.api_key == "oc-key-123"
    assert config.opencode_api_key == "oc-key-123"
    assert config.base_url == DEFAULT_OPENCODE_BASE_URL
    assert config.timeout_seconds == 120
    assert config.temperature == 0.2


def test_from_env_resolves_deepseek_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "deepseek-api")
    monkeypatch.setenv("AIWIKI_DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("AIWIKI_DEEPSEEK_BASE_URL", "https://ds.example.com/v1")

    config = LLMConfig.from_env()

    assert config.backend == BACKEND_DEEPSEEK_API
    assert config.model == DEFAULT_DEEPSEEK_MODEL
    assert config.api_key == "ds-key"
    assert config.deepseek_api_key == "ds-key"
    assert config.base_url == "https://ds.example.com/v1"


def test_from_env_resolves_anthropic_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "anthropic-api")
    monkeypatch.setenv("AIWIKI_ANTHROPIC_API_KEY", "ant-key")

    config = LLMConfig.from_env()

    assert config.backend == BACKEND_ANTHROPIC_API
    assert config.model == DEFAULT_ANTHROPIC_API_MODEL
    assert config.anthropic_api_key == "ant-key"
    assert config.anthropic_base_url == DEFAULT_ANTHROPIC_BASE_URL


def test_from_env_resolves_openai_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "openai-api")
    monkeypatch.setenv("AIWIKI_LLM_API_KEY", "oai-key")
    monkeypatch.setenv("AIWIKI_LLM_BASE_URL", "https://oai.example.com/v1")

    config = LLMConfig.from_env()

    assert config.backend == BACKEND_OPENAI_API
    assert config.model == DEFAULT_OPENAI_API_MODEL
    assert config.api_key == "oai-key"
    assert config.base_url == "https://oai.example.com/v1"


def test_from_env_timeout_and_temperature_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "opencode-api")
    monkeypatch.setenv("AIWIKI_OPENCODE_API_KEY", "k")
    monkeypatch.setenv("AIWIKI_LLM_TIMEOUT", "30")
    monkeypatch.setenv("AIWIKI_LLM_TEMPERATURE", "0.7")

    config = LLMConfig.from_env()

    assert config.timeout_seconds == 30
    assert config.temperature == 0.7


def test_from_env_model_fallback_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "opencode-api")
    monkeypatch.setenv("AIWIKI_OPENCODE_API_KEY", "k")
    monkeypatch.setenv("AIWIKI_LLM_MODEL", "primary-model")
    monkeypatch.setenv("AIWIKI_MODEL_FALLBACK", "primary-model,secondary-model,tertiary-model")

    config = LLMConfig.from_env()

    assert config.model_retry_chain == ("primary-model", "secondary-model", "tertiary-model")


# ---------------------------------------------------------------------------
# 2. Backend resolution: unknown backend / missing credentials
# ---------------------------------------------------------------------------


def test_from_env_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "unknown-backend")
    monkeypatch.setenv("AIWIKI_LLM_API_KEY", "k")

    with pytest.raises(RuntimeError, match="Unsupported AIWIKI_LLM_BACKEND"):
        LLMConfig.from_env()


def test_from_env_opencode_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "opencode-api")

    with pytest.raises(RuntimeError, match="opencode-api"):
        LLMConfig.from_env()


def test_from_env_deepseek_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "deepseek-api")

    with pytest.raises(RuntimeError, match="deepseek-api"):
        LLMConfig.from_env()


def test_from_env_anthropic_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "anthropic-api")

    with pytest.raises(RuntimeError, match="anthropic-api"):
        LLMConfig.from_env()


def test_from_env_openai_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "openai-api")

    with pytest.raises(RuntimeError, match="openai-api"):
        LLMConfig.from_env()


def test_from_env_require_explicit_model_rejects_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIWIKI_LLM_BACKEND", "opencode-api")
    monkeypatch.setenv("AIWIKI_OPENCODE_API_KEY", "k")
    monkeypatch.setenv("AIWIKI_REQUIRE_EXPLICIT_MODEL", "1")

    with pytest.raises(RuntimeError, match="AIWIKI_REQUIRE_EXPLICIT_MODEL"):
        LLMConfig.from_env()


# ---------------------------------------------------------------------------
# 3 + 4 + 5. OpenAICompatClient retry / timeout / error classification
# ---------------------------------------------------------------------------


def _ok_response_bytes(content: str = "# answer\n\nbody text") -> bytes:
    return json.dumps(
        {
            "id": "resp-1",
            "choices": [{"message": {"content": content}}],
            "usage": {"input_tokens": 5, "output_tokens": 7},
        }
    ).encode("utf-8")


def _make_http_error(code: int, body: bytes = b"error details") -> error.HTTPError:
    return error.HTTPError(
        url="https://example.com/v1/chat/completions",
        code=code,
        msg=f"HTTP {code}",
        hdrs={"Content-Type": "application/json"},
        fp=BytesIO(body),
    )


def _openai_compat_config(**overrides: Any) -> LLMConfig:
    base = dict(
        backend=BACKEND_OPENAI_API,
        backend_requested="openai-api",
        model="gpt-4.1-mini",
        model_requested="gpt-4.1-mini",
        api_key="key",
        base_url="https://api.openai.com/v1",
        timeout_seconds=60,
        temperature=0.2,
    )
    base.update(overrides)
    return LLMConfig(**base)


def test_openai_compat_client_retry_then_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Retryable HTTP 503 on first attempt -> retry -> success on second attempt."""

    monkeypatch.setenv("AIWIKI_LLM_RETRY_ATTEMPTS", "2")
    calls: list[str] = []

    def _fake_safe_fetch(url: str, **_kwargs: Any) -> tuple[bytes, str]:
        calls.append(url)
        if len(calls) == 1:
            raise _make_http_error(503, b"service unavailable")
        return _ok_response_bytes(), "application/json"

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)
    monkeypatch.setattr("aiwiki.llm.time.sleep", lambda _seconds: None)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    result = client.complete("system", "user")

    assert len(calls) == 2
    assert result.text == "# answer\n\nbody text"
    assert result.response_id == "resp-1"
    assert result.usage == {"input_tokens": 5, "output_tokens": 7}


def test_openai_compat_client_non_retryable_http_raises_immediately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """HTTP 401 is not in the retryable set; client raises after the first attempt."""

    monkeypatch.setenv("AIWIKI_LLM_RETRY_ATTEMPTS", "2")
    calls: list[str] = []

    def _fake_safe_fetch(url: str, **_kwargs: Any) -> tuple[bytes, str]:
        calls.append(url)
        raise _make_http_error(401, b"unauthorized")

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)
    monkeypatch.setattr("aiwiki.llm.time.sleep", lambda _seconds: None)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    with pytest.raises(LLMError, match="HTTP 401"):
        client.complete("system", "user")

    assert len(calls) == 1


def test_openai_compat_client_timeout_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """TimeoutError from safe_fetch surfaces as LLMError classified as 'timeout'."""

    def _fake_safe_fetch(_url: str, **_kwargs: Any) -> tuple[bytes, str]:
        raise TimeoutError("timed out")

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)

    config = _openai_compat_config(timeout_seconds=15)
    client = OpenAICompatClient(config, workdir=tmp_path)
    with pytest.raises(LLMError, match="timed out after 15 seconds") as exc_info:
        client.complete("system", "user")

    assert classify_backend_error(str(exc_info.value)) == "timeout"


def test_openai_compat_client_network_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """URLError (network) surfaces as LLMError classified as 'unavailable'."""

    def _fake_safe_fetch(_url: str, **_kwargs: Any) -> tuple[bytes, str]:
        raise error.URLError("connection refused")

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    with pytest.raises(LLMError, match="Unable to reach LLM endpoint") as exc_info:
        client.complete("system", "user")

    assert classify_backend_error(str(exc_info.value)) == "unavailable"


def test_openai_compat_client_invalid_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-JSON response body surfaces as LLMError with a persisted raw response path."""

    def _fake_safe_fetch(_url: str, **_kwargs: Any) -> tuple[bytes, str]:
        return b"not valid json at all", "text/plain"

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    with pytest.raises(LLMError, match="invalid JSON") as exc_info:
        client.complete("system", "user")

    assert exc_info.value.raw_response_path is not None
    assert exc_info.value.raw_response_path.startswith(".aiwiki/llm-responses/")


def test_openai_compat_client_empty_content(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Valid JSON with empty content surfaces as LLMError."""

    def _fake_safe_fetch(_url: str, **_kwargs: Any) -> tuple[bytes, str]:
        return (
            json.dumps({"id": "r", "choices": [{"message": {"content": "   "}}]}).encode("utf-8"),
            "application/json",
        )

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    with pytest.raises(LLMError, match="empty content"):
        client.complete("system", "user")


def test_openai_compat_client_missing_choices(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Malformed response (no choices) surfaces as LLMError."""

    def _fake_safe_fetch(_url: str, **_kwargs: Any) -> tuple[bytes, str]:
        return b'{"id": "r"}', "application/json"

    monkeypatch.setattr("aiwiki.llm.safe_fetch", _fake_safe_fetch)

    client = OpenAICompatClient(_openai_compat_config(), workdir=tmp_path)
    with pytest.raises(LLMError, match="missing `choices`"):
        client.complete("system", "user")


# ---------------------------------------------------------------------------
# 5. classify_backend_error categories
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("LLM endpoint timed out after 60 seconds.", "timeout"),
        ("HTTP 429 from LLM endpoint: rate limit exceeded", "quota"),
        ("usage limit reached, upgrade to pro", "quota"),
        ("HTTP 401 from LLM endpoint: unauthorized", "auth"),
        ("forbidden: permission denied", "auth"),
        ("Unable to reach LLM endpoint: connection refused", "unavailable"),
        ("temporarily unavailable, please retry", "unavailable"),
        ("HTTP 500 from LLM endpoint: internal error", "error"),
        ("some other unexpected failure", "error"),
    ],
)
def test_classify_backend_error_categories(message: str, expected: str) -> None:
    assert classify_backend_error(message) == expected


# ---------------------------------------------------------------------------
# 6. ModelFallbackClient model-chain advancement
# ---------------------------------------------------------------------------


class _StubClient:
    """Minimal SupportsComplete stub with a configurable .config and .complete."""

    def __init__(self, config: LLMConfig, responses: list[Any]) -> None:
        self.config = config
        self.primary_config = config
        self.client_configs = [config]
        self._responses = list(responses)
        self._index = 0

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt, user_prompt
        if self._index >= len(self._responses):
            raise LLMError("stub exhausted")
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, BaseException):
            raise response
        return response


def test_model_fallback_client_advances_on_model_not_found(tmp_path: Path) -> None:
    """Primary model fails with model_not_found -> advance to next candidate -> success."""

    primary_cfg = _openai_compat_config(model="primary-model", model_requested="primary-model")
    secondary_cfg = _openai_compat_config(model="secondary-model", model_requested="secondary-model")
    primary = _StubClient(primary_cfg, [LLMError("unknown model: primary-model")])
    secondary = _StubClient(secondary_cfg, [CompletionResult(text="ok", response_id="r", usage={})])

    client = ModelFallbackClient(primary_cfg, tmp_path, [primary_cfg, secondary_cfg])
    # Replace the internally-instantiated clients with our stubs so we control
    # the per-candidate behavior without real network calls.
    client.clients = [primary, secondary]

    result = client.complete("system", "user")

    assert result.text == "ok"
    assert client.index == 1
    assert client.config.model == "secondary-model"


def test_model_fallback_client_no_advance_on_non_model_error(tmp_path: Path) -> None:
    """Non-model error (e.g. auth) does not trigger model-chain advancement."""

    primary_cfg = _openai_compat_config(model="primary-model")
    secondary_cfg = _openai_compat_config(model="secondary-model")
    primary = _StubClient(primary_cfg, [LLMError("HTTP 401: unauthorized")])
    secondary = _StubClient(secondary_cfg, [CompletionResult(text="ok", response_id="r", usage={})])

    client = ModelFallbackClient(primary_cfg, tmp_path, [primary_cfg, secondary_cfg])
    client.clients = [primary, secondary]

    with pytest.raises(LLMError, match="HTTP 401"):
        client.complete("system", "user")

    assert client.index == 0


# ---------------------------------------------------------------------------
# 7. _retry_ask_prompt_profile state machine decision
# ---------------------------------------------------------------------------


def test_retry_ask_prompt_profile_returns_lean_on_timeout() -> None:
    """Timeout error with 'balanced' profile triggers a 'lean' retry."""

    exc = LLMError("LLM endpoint timed out after 120 seconds.")
    client = _StubClient(_openai_compat_config(), [])

    assert _retry_ask_prompt_profile(exc, "balanced", client) == "lean"


def test_retry_ask_prompt_profile_returns_empty_on_non_timeout() -> None:
    """Non-timeout error does not trigger a prompt-profile retry."""

    exc = LLMError("HTTP 401: unauthorized")
    client = _StubClient(_openai_compat_config(), [])

    assert _retry_ask_prompt_profile(exc, "balanced", client) == ""


def test_retry_ask_prompt_profile_returns_empty_when_already_lean() -> None:
    """Even a timeout error does not retry once we are already on the 'lean' profile."""

    exc = LLMError("LLM endpoint timed out after 120 seconds.")
    client = _StubClient(_openai_compat_config(), [])

    assert _retry_ask_prompt_profile(exc, "lean", client) == ""


# ---------------------------------------------------------------------------
# 8. _mark_run_ask_artifact_degraded writes failure notice (not fake success)
# ---------------------------------------------------------------------------


def test_mark_run_ask_artifact_degraded_writes_failure_notice(tmp_path: Path) -> None:
    target = tmp_path / "output" / "reports" / "ask-failed.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\n"
        "title: pending question\n"
        "query: what is source-a\n"
        "format: report\n"
        "delivery_mode: background-pending\n"
        "---\n\n"
        "# Pending\n\nWaiting for LLM.\n",
        encoding="utf-8",
    )

    _mark_run_ask_artifact_degraded(
        target,
        reason="HTTP 401 from LLM endpoint: unauthorized",
        backend="opencode-api",
        model="deepseek-v4-pro",
        llm_status="failed",
    )

    content = target.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)
    assert frontmatter.get("delivery_mode") == "llm-failed"
    assert frontmatter.get("llm_status") == "failed"
    assert frontmatter.get("background_status") == "failed"
    assert frontmatter.get("llm_failure_reason") == "HTTP 401 from LLM endpoint: unauthorized"
    assert frontmatter.get("llm_backend") == "opencode-api"
    assert frontmatter.get("llm_model") == "deepseek-v4-pro"
    # Must explicitly state it is NOT a final report / fallback answer.
    assert "不是最终报告" in content
    assert "不是 fallback 占位答案" in content


def test_mark_run_ask_artifact_degraded_timeout_status(tmp_path: Path) -> None:
    target = tmp_path / "output" / "reports" / "ask-timeout.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\nquery: q\n---\n\nbody\n", encoding="utf-8")

    _mark_run_ask_artifact_degraded(
        target,
        reason="LLM endpoint timed out after 120 seconds.",
        backend="opencode-api",
        model="m",
        llm_status="timeout_or_unavailable",
    )

    content = target.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)
    assert frontmatter.get("llm_status") == "timeout_or_unavailable"
    assert frontmatter.get("delivery_mode") == "llm-failed"


# ---------------------------------------------------------------------------
# 9. _complete_run_ask_artifact end-to-end state machine (fixture vault)
# ---------------------------------------------------------------------------


def _copy_fixture_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    shutil.copytree(_FIXTURE_ROOT, vault)
    return vault


class _StatefulMockClient:
    """Mock client that plays back a scripted sequence of results or exceptions.

    Mimics the interface that ``_complete_run_ask_artifact`` reads from a real
    client (``.config``, ``.primary_config``, ``.client_configs``) so the
    state machine's backend/model audit fields populate without a real backend.
    """

    def __init__(self, config: LLMConfig, responses: list[Any]) -> None:
        self.config = config
        self.primary_config = config
        self.client_configs = [config]
        self._responses = list(responses)
        self._index = 0

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt, user_prompt
        if self._index >= len(self._responses):
            raise LLMError("mock client exhausted")
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, BaseException):
            raise response
        return response


def _mock_config() -> LLMConfig:
    return LLMConfig(
        backend=BACKEND_OPENCODE_API,
        backend_requested="opencode-api",
        model="stub-model",
        model_requested="stub-model",
        api_key="stub-key",
        base_url=DEFAULT_OPENCODE_BASE_URL,
        timeout_seconds=60,
    )


def _valid_report_markdown() -> str:
    return "---\ntitle: stub report\n---\n\n# Stub Answer\n\nDeterministic stub body for source-a.\n"


def test_complete_run_ask_artifact_timeout_retry_success(tmp_path: Path) -> None:
    """First attempt times out -> state machine retries with 'lean' profile -> success.

    Covers the ``workflows_ask`` state machine path: ``_retry_ask_prompt_profile``
    returns 'lean' on timeout, ``_complete_run_ask_artifact`` records the
    prompt-profile fallback stage and completes successfully on the retry.
    """

    vault = _copy_fixture_vault(tmp_path)
    artifact = ask_question(vault, "deterministic source-a", "report")
    target = vault / artifact["path"]
    assert target.exists()

    client = _StatefulMockClient(
        _mock_config(),
        [
            LLMError("LLM endpoint timed out after 60 seconds."),
            CompletionResult(text=_valid_report_markdown(), response_id="stub-1", usage={}),
        ],
    )

    payload = _complete_run_ask_artifact(
        vault,
        artifact=artifact,
        question="deterministic source-a",
        output_format="report",
        client=client,
    )

    assert payload["contract_validated"] is True
    assert "prompt-profile" in str(payload.get("fallback_stage") or "")
    assert payload.get("retry_prompt_profile") == "lean"
    assert payload.get("prompt_profile") == "lean"
    assert payload["backend_effective"] == "opencode-api"
    assert payload["model_final"] == "stub-model"

    # The artifact on disk should now carry the LLM-completed body, not a failure notice.
    final_text = target.read_text(encoding="utf-8")
    assert "Stub Answer" in final_text
    assert "llm-failed" not in final_text


def test_complete_run_ask_artifact_failure_degrades_artifact(tmp_path: Path) -> None:
    """Persistent non-retryable failure -> artifact is marked degraded with a failure notice.

    Covers ``_mark_run_ask_artifact_degraded`` being invoked from the state
    machine's failure branch: the target artifact receives
    ``delivery_mode: llm-failed`` and an explicit failure reason, not a fake
    success body.
    """

    vault = _copy_fixture_vault(tmp_path)
    artifact = ask_question(vault, "deterministic source-a", "report")
    target = vault / artifact["path"]
    assert target.exists()

    client = _StatefulMockClient(
        _mock_config(),
        [LLMError("HTTP 401 from LLM endpoint: unauthorized")],
    )

    with pytest.raises(LLMError, match="HTTP 401"):
        _complete_run_ask_artifact(
            vault,
            artifact=artifact,
            question="deterministic source-a",
            output_format="report",
            client=client,
        )

    final_text = target.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(final_text)
    assert frontmatter.get("delivery_mode") == "llm-failed"
    assert frontmatter.get("llm_status") == "failed"
    assert frontmatter.get("llm_failure_reason") == "HTTP 401 from LLM endpoint: unauthorized"
    assert "不是最终报告" in final_text
    # The failure receipt should be recorded.
    receipt_path = vault / ".aiwiki" / "logs" / "llm-receipts.jsonl"
    assert receipt_path.exists()
    receipts = [json.loads(line) for line in receipt_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(receipts) == 1
    assert receipts[0]["status"] == "failed"
    assert receipts[0]["event"] == "run-ask"
    assert receipts[0]["delivery_mode"] == "llm-failed"


def test_complete_run_ask_artifact_persistent_timeout_degrades_artifact(tmp_path: Path) -> None:
    """Timeout on both 'balanced' and 'lean' profiles -> degrade with timeout_or_unavailable status."""

    vault = _copy_fixture_vault(tmp_path)
    artifact = ask_question(vault, "deterministic source-a", "report")
    target = vault / artifact["path"]

    client = _StatefulMockClient(
        _mock_config(),
        [
            LLMError("LLM endpoint timed out after 60 seconds."),
            LLMError("LLM endpoint timed out after 60 seconds."),
        ],
    )

    with pytest.raises(LLMError, match="timed out"):
        _complete_run_ask_artifact(
            vault,
            artifact=artifact,
            question="deterministic source-a",
            output_format="report",
            client=client,
        )

    final_text = target.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(final_text)
    assert frontmatter.get("delivery_mode") == "llm-failed"
    assert frontmatter.get("llm_status") == "timeout_or_unavailable"


def test_furnace_quick_commands_use_advanced_surface_without_protocol() -> None:
    from aiwiki.render.views import furnace_quick_commands

    cmds = furnace_quick_commands("general", [], [])
    assert cmds
    assert all("--protocol" not in cmd for cmd in cmds)
    assert all("advanced" in cmd for cmd in cmds)


def test_build_llm_rerun_command_uses_advanced_surface_without_protocol() -> None:
    from aiwiki.app_shell.helpers import _build_llm_rerun_command

    cmd = _build_llm_rerun_command(
        {"event": "run-ask", "question": "hi", "format": "report", "protocol": "general"}
    )
    assert cmd
    assert "--protocol" not in cmd
    assert "advanced" in cmd
    assert "advanced run-ask" in cmd


def test_render_url_in_browser_skips_unguarded_cli_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from aiwiki.drop import url as drop_url_module

    monkeypatch.delenv("AIWIKI_ALLOW_UNGUARDED_BROWSER_CLI", raising=False)
    monkeypatch.setattr(drop_url_module, "sync_playwright", None)

    with patch.object(drop_url_module, "_browser_command", return_value="/fake/chromium") as mock_browser_command:
        with patch.object(drop_url_module, "_render_url_with_browser_cli") as mock_cli:
            result = drop_url_module._render_url_in_browser("https://example.com")

    assert result == {"html": "", "backend": ""}
    mock_browser_command.assert_not_called()
    mock_cli.assert_not_called()


def test_render_url_in_browser_uses_cli_when_explicitly_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from aiwiki.drop import url as drop_url_module

    monkeypatch.setenv("AIWIKI_ALLOW_UNGUARDED_BROWSER_CLI", "1")
    monkeypatch.setattr(drop_url_module, "sync_playwright", None)

    with patch.object(drop_url_module, "_browser_command", return_value="/fake/chromium"):
        with patch.object(
            drop_url_module,
            "_render_url_with_browser_cli",
            return_value="<html>ok</html>",
        ) as mock_cli:
            result = drop_url_module._render_url_in_browser("https://example.com")

    assert result == {"html": "<html>ok</html>", "backend": "chromium"}
    mock_cli.assert_called_once_with("https://example.com", "/fake/chromium")


# ---------------------------------------------------------------------------
# LLM input planner (plan/execute split): JSON parse + Plan validation
# ---------------------------------------------------------------------------


def test_planner_parse_plan_valid_json() -> None:
    from aiwiki.input_planner import _parse_plan

    plan = _parse_plan('{"action": "fetch_raw", "targets": ["https://raw.githubusercontent.com/x/y/HEAD/README.md"], "title": "y", "reason": "github"}')
    assert plan.action == "fetch_raw"
    assert plan.targets == ["https://raw.githubusercontent.com/x/y/HEAD/README.md"]
    assert plan.title == "y"
    assert plan.reason == "github"


def test_planner_parse_plan_strips_code_fence() -> None:
    from aiwiki.input_planner import _parse_plan

    plan = _parse_plan('```json\n{"action": "ask", "targets": ["what is aiwiki?"]}\n```')
    assert plan.action == "ask"
    assert plan.targets == ["what is aiwiki?"]


def test_planner_parse_plan_handles_leading_prose() -> None:
    from aiwiki.input_planner import _parse_plan

    plan = _parse_plan('Here is the plan:\n{"action": "fetch_page", "targets": ["https://example.com"]}\nDone.')
    assert plan.action == "fetch_page"
    assert plan.targets == ["https://example.com"]


def test_planner_parse_plan_no_json_raises() -> None:
    from aiwiki.input_planner import PlannerError, _parse_plan

    with pytest.raises(PlannerError):
        _parse_plan("no json here")


def test_planner_validate_invalid_action() -> None:
    from aiwiki.input_planner import Plan, PlannerError

    with pytest.raises(PlannerError):
        Plan(action="bogus", targets=["x"]).validate()


def test_planner_validate_missing_targets() -> None:
    from aiwiki.input_planner import Plan, PlannerError

    with pytest.raises(PlannerError):
        Plan(action="fetch_raw", targets=[]).validate()


def test_planner_validate_ask_allows_empty_targets() -> None:
    from aiwiki.input_planner import Plan

    Plan(action="ask", targets=[]).validate()  # should not raise


def test_planner_validate_too_many_targets() -> None:
    from aiwiki.input_planner import MAX_TARGETS, Plan, PlannerError

    with pytest.raises(PlannerError):
        Plan(action="fetch_raw", targets=[f"https://example.com/{i}" for i in range(MAX_TARGETS + 1)]).validate()


def test_plan_input_success_with_mock_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki import input_planner
    from aiwiki.llm import CompletionResult

    class _StubClient:
        def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
            return CompletionResult(
                text='{"action": "fetch_raw", "targets": ["https://raw.githubusercontent.com/34306/vphone-aio/HEAD/README.md"], "title": "vphone-aio", "reason": "github repo"}',
                response_id="stub",
                usage={},
            )

    monkeypatch.setattr("aiwiki.runner.clients.create_client", lambda root, timeout_seconds=None: _StubClient())

    plan = input_planner.plan_input("https://github.com/34306/vphone-aio", tmp_path)
    assert plan.action == "fetch_raw"
    assert plan.targets == ["https://raw.githubusercontent.com/34306/vphone-aio/HEAD/README.md"]
    assert plan.title == "vphone-aio"


def test_plan_input_llm_error_raises_planner_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki import input_planner
    from aiwiki.llm import LLMError

    class _FailingClient:
        def complete(self, system_prompt: str, user_prompt: str) -> Any:
            raise LLMError("backend down")

    monkeypatch.setattr("aiwiki.runner.clients.create_client", lambda root, timeout_seconds=None: _FailingClient())

    with pytest.raises(input_planner.PlannerError):
        input_planner.plan_input("https://example.com", tmp_path)


def test_plan_input_client_resolution_error_raises_planner_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki import input_planner

    def _fail_create(root: Path, timeout_seconds: int | None = None) -> Any:
        raise ValueError("LLM backend resolution failed: no key")

    monkeypatch.setattr("aiwiki.runner.clients.create_client", _fail_create)

    with pytest.raises(input_planner.PlannerError):
        input_planner.plan_input("https://example.com", tmp_path)


def test_plan_input_bad_json_raises_planner_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki import input_planner
    from aiwiki.llm import CompletionResult

    class _GarbageClient:
        def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
            return CompletionResult(text="I cannot help with that.", response_id="stub", usage={})

    monkeypatch.setattr("aiwiki.runner.clients.create_client", lambda root, timeout_seconds=None: _GarbageClient())

    with pytest.raises(input_planner.PlannerError):
        input_planner.plan_input("https://example.com", tmp_path)


def test_tokenize_cjk_bigrams_overlap_across_phrasings() -> None:
    from aiwiki.utils.text import tokenize

    query = tokenize("为什么编译很慢")
    haystack = tokenize("编译流程很慢的原因")
    # CJK runs are segmented into overlapping bigrams, so differently-phrased
    # Chinese text shares matchable units for retrieval ranking.
    assert "编译" in query and "编译" in haystack
    assert "很慢" in query and "很慢" in haystack
    assert set(query) & set(haystack)


def test_tokenize_preserves_latin_and_mixed() -> None:
    from aiwiki.utils.text import tokenize

    assert tokenize("the quick brown fox") == ["quick", "brown", "fox"]
    mixed = tokenize("aiwiki 编译 pipeline")
    assert "aiwiki" in mixed and "pipeline" in mixed and "编译" in mixed


def test_conflict_signals_detect_cjk_upgrade_downgrade() -> None:
    from aiwiki.content.concepts import detect_concept_conflict_signals

    contexts = [
        {"path": "wiki/sources/a.md", "title": "A", "status": "ready", "summary": "这次变更是一次升级"},
        {"path": "wiki/sources/b.md", "title": "B", "status": "ready", "summary": "这次变更其实是降级"},
    ]
    signals = detect_concept_conflict_signals(contexts)
    labels = {signal["label"] for signal in signals}
    assert "升级-vs-降级" in labels


def test_distill_synthesizer_disabled_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki.runner.alchemy import _llm_distill_synthesizer

    monkeypatch.setenv("AIWIKI_LLM_DISTILL", "0")
    assert _llm_distill_synthesizer(tmp_path) is None


def test_distill_synthesizer_no_backend_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki.runner.alchemy import _llm_distill_synthesizer

    monkeypatch.setenv("AIWIKI_LLM_DISTILL", "1")
    ref = "wiki/derived/src.md"
    src = tmp_path / ref
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# Src\n\nsome evidence", encoding="utf-8")

    def _fail_create(root: Path, timeout_seconds: int | None = None) -> Any:
        raise ValueError("no backend configured")

    monkeypatch.setattr("aiwiki.runner.clients.create_client", _fail_create)
    synth = _llm_distill_synthesizer(tmp_path)
    assert synth is not None
    # No backend -> synthesizer returns None so the mutation layer uses the
    # deterministic seed (replay-safe).
    assert synth("why", [ref]) is None


def test_distill_synthesizer_mocked_llm_returns_body(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aiwiki.llm import CompletionResult
    from aiwiki.runner.alchemy import _llm_distill_synthesizer

    monkeypatch.setenv("AIWIKI_LLM_DISTILL", "1")
    ref = "wiki/derived/src.md"
    src = tmp_path / ref
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\nkey: v\n---\n# Src\n\nevidence body", encoding="utf-8")

    class _StubClient:
        def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
            assert "evidence body" in user_prompt
            return CompletionResult(text="## Thesis\n- synthesized", response_id="stub", usage={})

    monkeypatch.setattr("aiwiki.runner.clients.create_client", lambda root, timeout_seconds=None: _StubClient())
    synth = _llm_distill_synthesizer(tmp_path)
    assert synth is not None
    assert synth("why", [ref]) == "## Thesis\n- synthesized"


def test_cjk_concept_terms_and_slug_survive_bigrams() -> None:
    from aiwiki.content.concepts import entry_concept_terms
    from aiwiki.utils.text import slugify, tokenize

    title = "炼丹炉检索能力"
    tokens = tokenize(title)
    assert "炼丹" in tokens and "检索" in tokens
    terms = entry_concept_terms({"title": title, "id": "x1"}, f"{title}需要提升。")
    assert terms, "CJK bigrams must pass concept length gate"
    assert slugify("炼丹炉") == "炼丹炉"
    assert slugify("炼丹炉") != slugify("中文标题")


def test_cjk_stopwords_filter_function_bigrams() -> None:
    from aiwiki.utils.text import tokenize

    tokens = tokenize("这是一个测试，我们发现这个系统很好")
    assert "这是" not in tokens
    assert "一个" not in tokens
    assert "我们" not in tokens
    assert "这个" not in tokens
    assert "测试" in tokens or "系统" in tokens


def test_fetch_raw_all_fail_raises(tmp_path: Path) -> None:
    from aiwiki.executor import execute_plan
    from aiwiki.input_planner import Plan
    from aiwiki.protocol.scaffold import ensure_layout

    ensure_layout(tmp_path)
    plan = Plan(
        action="fetch_raw",
        targets=["http://127.0.0.1:9/blocked"],
        title="blocked",
        reason="test",
    )
    with pytest.raises(RuntimeError, match="fetch_raw failed for all targets"):
        execute_plan(tmp_path, plan, "https://github.com/owner/repo")
    assert not any((tmp_path / "raw" / "inbox").glob("*.md"))


def test_executor_rejects_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.executor import execute_plan
    from aiwiki.input_planner import Plan
    from aiwiki.protocol.scaffold import ensure_layout
    from aiwiki.utils.security import PathOutsideWorkspaceError

    ensure_layout(tmp_path)
    outside = Path("/tmp/aiwiki-outside-note-test.md")
    outside.write_text("secret", encoding="utf-8")
    plan = Plan(action="read_local_note", targets=[str(outside)], title="x", reason="injection")
    with pytest.raises(PathOutsideWorkspaceError):
        execute_plan(tmp_path, plan, "https://example.com/article")
    outside.unlink(missing_ok=True)


def test_universal_drop_path_like_ask_fails_with_planner_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.cli.universal_input import _rewrite_universal_drop_argv

    monkeypatch.setenv("AIWIKI_LLM_PLANNER", "1")
    with pytest.raises(SystemExit) as caught:
        _rewrite_universal_drop_argv(["drop", "notes/no-such-type.docx"])
    assert caught.value.code == 2


def test_cjk_slash_question_not_treated_as_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.cli.universal_input import _looks_like_local_path, _rewrite_universal_drop_argv

    assert not _looks_like_local_path("A/B测试怎么做？")
    monkeypatch.setenv("AIWIKI_LLM_PLANNER", "1")
    rewritten = _rewrite_universal_drop_argv(["drop", "A/B测试怎么做？"])
    assert rewritten[:3] == ["drop", "plan", "A/B测试怎么做？"]


def test_existing_dir_routes_to_drop_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.cli.universal_input import _rewrite_universal_drop_argv

    repo = tmp_path / "reponame"
    repo.mkdir()
    (repo / "README.md").write_text("# hi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIWIKI_LLM_PLANNER", "1")
    rewritten = _rewrite_universal_drop_argv(["drop", "reponame"])
    assert rewritten[:3] == ["drop", "repo", "reponame"]


def test_github_raw_rewrite_deterministic() -> None:
    from aiwiki.input_router import classify_universal_input, rewrite_github_raw_url

    blob = "https://github.com/34306/vphone-aio/blob/main/README.md"
    assert rewrite_github_raw_url(blob) == "https://raw.githubusercontent.com/34306/vphone-aio/main/README.md"
    decision = classify_universal_input("https://github.com/34306/vphone-aio")
    assert decision.reason == "github-raw-rewrite"
    assert decision.payload.endswith("/HEAD/README.md")


def test_executor_rejects_unrelated_vault_internal(tmp_path: Path) -> None:
    from aiwiki.executor import execute_plan
    from aiwiki.input_planner import Plan
    from aiwiki.protocol.scaffold import ensure_layout
    from aiwiki.utils.security import PathOutsideWorkspaceError

    ensure_layout(tmp_path)
    internal = tmp_path / ".aiwiki"
    plan = Plan(action="read_local_repo", targets=[str(internal)], title="x", reason="injection")
    with pytest.raises(PathOutsideWorkspaceError):
        execute_plan(tmp_path, plan, "https://example.com/unrelated")
