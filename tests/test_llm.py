from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib import error

from aiwiki.config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_DEEPSEEK_API,
    BACKEND_OPENAI_API,
    BACKEND_OPENCODE_API,
    LLMConfig,
)
from aiwiki.llm import (
    AnthropicClient,
    CompletionResult,
    LLMError,
    ModelFallbackClient,
    OpenAICompatClient,
    advance_client_model,
    create_backend_client,
    probe_available_backends,
    probe_backend,
)


class LLMClientTests(unittest.TestCase):
    def test_openai_compat_complete_supports_text_list_payloads(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)

        with patch(
            "aiwiki.llm.safe_fetch",
            return_value=(
                json.dumps(
                    {
                        "id": "resp_456",
                        "choices": [
                            {
                                "message": {
                                    "content": [
                                        {"type": "text", "text": "First line. "},
                                        {"type": "ignored", "text": "skip"},
                                        {"type": "text", "text": "Second line."},
                                    ]
                                }
                            }
                        ],
                        "usage": {"total_tokens": 21},
                    }
                ).encode("utf-8"),
                "https://api.openai.com/v1/chat/completions",
            ),
        ):
            result = client.complete("System prompt", "User prompt")

        self.assertEqual(result.text, "First line. Second line.")
        self.assertEqual(result.response_id, "resp_456")
        self.assertEqual(result.usage["total_tokens"], 21)

    def test_openai_compat_analyze_image_uses_image_url_payload(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)
        captured: dict[str, object] = {}
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as tempdir:
            image_path = Path(tempdir) / "tiny.png"
            image_path.write_bytes(image_bytes)

            def fake_safe_fetch(endpoint, **kwargs):
                captured["url"] = endpoint
                captured["body"] = json.loads(kwargs["data"].decode("utf-8"))
                return json.dumps(
                    {
                        "id": "resp_123",
                        "choices": [{"message": {"content": "Visible content summary."}}],
                        "usage": {"total_tokens": 42},
                    }
                ).encode("utf-8"), endpoint

            with patch("aiwiki.llm.safe_fetch", side_effect=fake_safe_fetch):
                result = client.analyze_image("System prompt", "User prompt", image_path)

        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        payload = captured["body"]
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "text")
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")
        self.assertTrue(payload["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(result.text, "Visible content summary.")

    def test_deepseek_complete_uses_openai_compat_endpoint_and_headers(self) -> None:
        config = LLMConfig(
            backend=BACKEND_DEEPSEEK_API,
            model="deepseek-v4-pro",
            api_key="deepseek_test_key",
            deepseek_api_key="deepseek_test_key",
            base_url="https://api.deepseek.com",
            deepseek_base_url="https://api.deepseek.com",
        )
        client = OpenAICompatClient(config)
        captured: dict[str, object] = {}

        def fake_safe_fetch(endpoint, **kwargs):
            captured["url"] = endpoint
            captured["headers"] = dict(kwargs["headers"])
            captured["body"] = json.loads(kwargs["data"].decode("utf-8"))
            return json.dumps(
                {
                    "id": "deepseek_resp",
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"total_tokens": 17},
                }
            ).encode("utf-8"), endpoint

        with patch("aiwiki.llm.safe_fetch", side_effect=fake_safe_fetch):
            result = client.complete("System prompt", "User prompt")

        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer deepseek_test_key")
        self.assertEqual(captured["body"]["model"], "deepseek-v4-pro")
        self.assertEqual(result.text, "OK")
        self.assertEqual(result.usage["total_tokens"], 17)

    def test_openai_compat_complete_wraps_http_error(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)
        http_error = error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=Message(),
            fp=io.BytesIO(b'{"error":"rate-limited"}'),
        )

        with patch.dict(os.environ, {"AIWIKI_LLM_RETRY_ATTEMPTS": "0"}):
            with patch("aiwiki.llm.safe_fetch", side_effect=http_error):
                with self.assertRaises(LLMError) as ctx:
                    client.complete("System prompt", "User prompt")

        self.assertIn("HTTP 429", str(ctx.exception))
        self.assertIn("rate-limited", str(ctx.exception))

    def test_openai_compat_retries_rate_limit_once_then_succeeds(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)
        http_error = error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=Message(),
            fp=io.BytesIO(b'{"error":"rate-limited"}'),
        )
        calls = [
            http_error,
            (
                b'{"id":"resp_1","choices":[{"message":{"content":"OK"}}],"usage":{"total_tokens":3}}',
                "https://api.openai.com/v1/chat/completions",
            ),
        ]

        def fake_safe_fetch(*args, **kwargs):
            del args, kwargs
            next_value = calls.pop(0)
            if isinstance(next_value, Exception):
                raise next_value
            return next_value

        with patch.dict(os.environ, {"AIWIKI_LLM_RETRY_ATTEMPTS": "1"}):
            with patch("aiwiki.llm.time.sleep") as sleep_mock:
                with patch("aiwiki.llm.safe_fetch", side_effect=fake_safe_fetch) as fetch_mock:
                    result = client.complete("System prompt", "User prompt")

        self.assertEqual(result.text, "OK")
        self.assertEqual(fetch_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_openai_compat_rejects_invalid_json_missing_choices_and_empty_content(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)

        cases = [
            ((b"not-json", "https://api.openai.com/v1/chat/completions"), "invalid JSON"),
            ((json.dumps({"id": "resp_123"}).encode("utf-8"), "https://api.openai.com/v1/chat/completions"), "missing `choices`"),
            (
                (json.dumps({"id": "resp_123", "choices": [{"message": {"content": "   "}}]}).encode("utf-8"), "url"),
                "empty content",
            ),
        ]
        for response, message in cases:
            with self.subTest(message=message):
                with patch("aiwiki.llm.safe_fetch", return_value=response):
                    with self.assertRaises(LLMError) as ctx:
                        client.complete("System prompt", "User prompt")
                self.assertIn(message, str(ctx.exception))

    def test_create_backend_client_returns_api_only_backend_clients(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            deepseek = create_backend_client(
                LLMConfig(
                    backend=BACKEND_DEEPSEEK_API,
                    model="deepseek-v4-pro",
                    api_key="deepseek",
                    deepseek_api_key="deepseek",
                    base_url="https://api.deepseek.com",
                    deepseek_base_url="https://api.deepseek.com",
                ),
                root,
            )
            openai = create_backend_client(LLMConfig(backend=BACKEND_OPENAI_API, model="gpt", api_key="secret"), root)
            opencode = create_backend_client(
                LLMConfig(
                    backend=BACKEND_OPENCODE_API,
                    model="deepseek-v4-pro",
                    api_key="opencode",
                    opencode_api_key="opencode",
                    base_url="https://opencode.ai/zen/go/v1",
                    opencode_base_url="https://opencode.ai/zen/go/v1",
                ),
                root,
            )
            anthropic = create_backend_client(
                LLMConfig(backend=BACKEND_ANTHROPIC_API, model="claude-sonnet-4-20250514", anthropic_api_key="sk-ant"),
                root,
            )
            with self.assertRaisesRegex(LLMError, "Unsupported backend"):
                create_backend_client(LLMConfig(backend="codex-cli"), root)

        self.assertIsInstance(deepseek, OpenAICompatClient)
        self.assertIsInstance(openai, OpenAICompatClient)
        self.assertIsInstance(opencode, OpenAICompatClient)
        self.assertIsInstance(anthropic, AnthropicClient)

    def test_model_fallback_handles_openai_compat_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = create_backend_client(
                LLMConfig(
                    backend=BACKEND_OPENCODE_API,
                    backend_requested=BACKEND_OPENCODE_API,
                    model="deepseek-v4-pro",
                    model_fallback_chain=("deepseek-v4-pro", "gpt-5.5"),
                    api_key="opencode",
                    opencode_api_key="opencode",
                    base_url="https://api.opencode.ai/v1",
                    opencode_base_url="https://api.opencode.ai/v1",
                    timeout_seconds=7,
                ),
                root,
            )

            attempts: list[str] = []

            def fake_safe_fetch(endpoint, **kwargs):
                payload = json.loads(kwargs["data"].decode("utf-8"))
                attempts.append(payload["model"])
                if len(attempts) == 1:
                    raise TimeoutError("read timed out")
                return json.dumps(
                    {
                        "id": "chatcmpl_opencode_fallback",
                        "choices": [{"message": {"content": "OK"}}],
                        "usage": {"total_tokens": 3},
                    }
                ).encode("utf-8"), endpoint

            with patch("aiwiki.llm.safe_fetch", side_effect=fake_safe_fetch):
                result = client.complete("System prompt", "User prompt")

        self.assertIsInstance(client, ModelFallbackClient)
        self.assertEqual(result.text, "OK")
        self.assertEqual(attempts, ["deepseek-v4-pro", "gpt-5.5"])
        self.assertEqual(client.config.model, "gpt-5.5")

    def test_advance_client_model_empty_chain(self) -> None:
        client = ModelFallbackClient(
            LLMConfig(backend=BACKEND_DEEPSEEK_API, model="primary"),
            Path.cwd(),
            [LLMConfig(backend=BACKEND_DEEPSEEK_API, model="primary")],
        )

        self.assertFalse(advance_client_model(client))
        self.assertEqual(client.index, 0)

    def test_probe_backend_compatible_degraded_requires_credential_and_unavailable(self) -> None:
        config = LLMConfig(backend=BACKEND_DEEPSEEK_API, backend_requested=BACKEND_DEEPSEEK_API, model="deepseek-v4-pro")

        class FakeClient:
            def __init__(self, result: CompletionResult | LLMError) -> None:
                self.config = config
                self.result = result

            def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
                del system_prompt
                del user_prompt
                if isinstance(self.result, LLMError):
                    raise self.result
                return self.result

        cases = [
            (CompletionResult("---\ntitle: probe\n---\nok\n", "probe", {}, "raw/probe.txt"), "compatible", True),
            (CompletionResult("● ---\ntitle: probe\n---\nok\n", "probe", {}, "raw/decorated.txt"), "degraded", False),
            (LLMError("HTTP 401: API key invalid", raw_response_path="raw/auth.txt"), "requires_credential", False),
            (LLMError("endpoint temporarily unavailable"), "unavailable", False),
        ]
        for result, compatibility, ok in cases:
            with self.subTest(compatibility=compatibility):
                with tempfile.TemporaryDirectory() as tempdir:
                    with patch("aiwiki.llm.create_backend_client", return_value=FakeClient(result)):
                        probe = probe_backend(config, Path(tempdir), timeout_seconds=5)
                self.assertEqual(probe["compatibility"], compatibility)
                self.assertEqual(probe["ok"], ok)

    def test_probe_available_backends_probes_each_available_api_backend(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENCODE_API,
            backend_requested=BACKEND_OPENCODE_API,
            model="deepseek-v4-pro",
            model_requested="",
            deepseek_api_key="deepseek",
            deepseek_base_url="https://api.deepseek.com",
            opencode_api_key="opencode",
            opencode_base_url="https://opencode.ai/zen/go/v1",
            anthropic_api_key="anthropic",
            api_key="openai",
        )
        seen: list[tuple[str, str]] = []

        def fake_probe(probe_config, workdir, timeout_seconds=None):
            del workdir
            seen.append((probe_config.backend_requested, probe_config.backend))
            return {
                "ok": True,
                "status": "ok",
                "backend_requested": probe_config.backend_requested,
                "backend": probe_config.backend,
                "model_requested": probe_config.model_requested,
                "model": probe_config.model,
                "duration_ms": timeout_seconds or 0,
                "response_preview": "OK",
                "matched_expected_output": True,
                "error": "",
            }

        with tempfile.TemporaryDirectory() as tempdir:
            with patch("aiwiki.llm.probe_backend", side_effect=fake_probe):
                probes = probe_available_backends(config, Path(tempdir), timeout_seconds=9)

        self.assertEqual(
            seen,
            [
                (BACKEND_OPENCODE_API, BACKEND_OPENCODE_API),
                (BACKEND_DEEPSEEK_API, BACKEND_DEEPSEEK_API),
                (BACKEND_ANTHROPIC_API, BACKEND_ANTHROPIC_API),
                (BACKEND_OPENAI_API, BACKEND_OPENAI_API),
            ],
        )
        self.assertEqual([probe["backend"] for probe in probes], [item[1] for item in seen])

    def test_anthropic_complete_basic(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="https://api.anthropic.com",
        )
        client = AnthropicClient(config)
        captured: dict[str, object] = {}

        def fake_safe_fetch(endpoint, **kwargs):
            captured["url"] = endpoint
            captured["headers"] = dict(kwargs["headers"])
            captured["body"] = json.loads(kwargs["data"].decode("utf-8"))
            return json.dumps(
                {
                    "id": "msg_123",
                    "content": [{"type": "text", "text": "Hello from Claude."}],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }
            ).encode("utf-8"), endpoint

        with patch("aiwiki.llm.safe_fetch", side_effect=fake_safe_fetch):
            result = client.complete("System prompt", "User prompt")

        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(captured["headers"]["x-api-key"], "sk-ant-test-key")
        self.assertEqual(captured["body"]["system"], "System prompt")
        self.assertEqual(result.text, "Hello from Claude.")
        self.assertEqual(result.response_id, "msg_123")


if __name__ == "__main__":
    unittest.main()
