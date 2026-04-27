from __future__ import annotations

import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

from aiwiki.config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_CLAUDE_CLI,
    BACKEND_CODEX_CLI,
    BACKEND_COPILOT_CLI,
    BACKEND_NVIDIA_NIM_API,
    BACKEND_OPENAI_API,
    LLMConfig,
)
from aiwiki.llm import (
    AnthropicClient,
    ClaudeCLIClient,
    CodexCLIClient,
    CopilotCLIClient,
    LLMError,
    ModelFallbackClient,
    OpenAICompatClient,
    advance_client_model,
    create_backend_client,
    probe_available_backends,
    probe_backend,
)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type
        del exc
        del tb
        return False


class RawHTTPResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "RawHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        del exc_type
        del exc
        del tb
        return False


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
            "aiwiki.llm.request.urlopen",
            return_value=FakeHTTPResponse(
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

            def fake_urlopen(http_request, timeout: int):
                del timeout
                captured["url"] = http_request.full_url
                captured["body"] = json.loads(http_request.data.decode("utf-8"))
                return FakeHTTPResponse(
                    {
                        "id": "resp_123",
                        "choices": [
                            {
                                "message": {
                                    "content": "Visible content summary.",
                                }
                            }
                        ],
                        "usage": {"total_tokens": 42},
                    }
                )

            with patch("aiwiki.llm.request.urlopen", side_effect=fake_urlopen):
                result = client.analyze_image("System prompt", "User prompt", image_path)

        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        payload = captured["body"]
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "text")
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")
        self.assertTrue(payload["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(result.text, "Visible content summary.")

    def test_codex_cli_analyze_image_attaches_image_flag(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CODEX_CLI,
            model="gpt-5-codex",
            codex_reasoning_effort="medium",
            codex_command="codex",
            codex_path="/usr/bin/codex",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CodexCLIClient(config, root)
            image_path = root / "tiny.png"
            image_path.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
                )
            )
            captured: dict[str, object] = {}

            def fake_run(command, **kwargs):
                captured["command"] = command
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("- Visual summary\n- Confidence: low\n", encoding="utf-8")
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                result = client.analyze_image("System prompt", "User prompt", image_path)

        command = captured["command"]
        self.assertIn("--image", command)
        self.assertIn("-c", command)
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertIn(str(image_path), command)
        self.assertEqual(result.text, "- Visual summary\n- Confidence: low")

    def test_nvidia_nim_complete_uses_openai_compat_endpoint_and_headers(self) -> None:
        config = LLMConfig(
            backend=BACKEND_NVIDIA_NIM_API,
            model="moonshotai/kimi-k2.5",
            api_key="nvapi_test_key",
            nvidia_nim_api_key="nvapi_test_key",
            base_url="https://integrate.api.nvidia.com/v1",
            nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
        )
        client = OpenAICompatClient(config)
        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout: int):
            del timeout
            captured["url"] = http_request.full_url
            captured["headers"] = dict(http_request.headers)
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "id": "nim_resp",
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"total_tokens": 17},
                }
            )

        with patch("aiwiki.llm.request.urlopen", side_effect=fake_urlopen):
            result = client.complete("System prompt", "User prompt")

        self.assertEqual(captured["url"], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer nvapi_test_key")
        self.assertEqual(captured["body"]["model"], "moonshotai/kimi-k2.5")
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
            hdrs=None,
            fp=io.BytesIO(b'{"error":"rate-limited"}'),
        )

        with patch("aiwiki.llm.request.urlopen", side_effect=http_error):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System prompt", "User prompt")

        self.assertIn("HTTP 429", str(ctx.exception))
        self.assertIn("rate-limited", str(ctx.exception))

    def test_openai_compat_complete_rejects_invalid_json(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)

        with patch("aiwiki.llm.request.urlopen", return_value=RawHTTPResponse(b"not-json")):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System prompt", "User prompt")

        self.assertIn("invalid JSON", str(ctx.exception))

    def test_openai_compat_complete_rejects_missing_choices(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)

        with patch("aiwiki.llm.request.urlopen", return_value=FakeHTTPResponse({"id": "resp_123"})):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System prompt", "User prompt")

        self.assertIn("missing `choices`", str(ctx.exception))

    def test_openai_compat_complete_rejects_empty_content(self) -> None:
        config = LLMConfig(
            backend=BACKEND_OPENAI_API,
            model="gpt-4.1-mini",
            api_key="secret",
            base_url="https://api.openai.com/v1",
        )
        client = OpenAICompatClient(config)

        with patch(
            "aiwiki.llm.request.urlopen",
            return_value=FakeHTTPResponse({"id": "resp_123", "choices": [{"message": {"content": "   "}}]}),
        ):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System prompt", "User prompt")

        self.assertIn("empty content", str(ctx.exception))

    def test_codex_cli_complete_uses_stdout_fallback_when_output_file_is_empty(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CODEX_CLI,
            model="gpt-5-codex",
            codex_reasoning_effort="high",
            codex_command="codex",
            codex_path="/usr/bin/codex",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CodexCLIClient(config, root)
            captured: dict[str, object] = {}

            def fake_run(command, **kwargs):
                captured["command"] = command
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("", encoding="utf-8")
                return type("Completed", (), {"returncode": 0, "stdout": "fallback text\n", "stderr": ""})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                result = client.complete("System prompt", "User prompt")

        self.assertEqual(result.text, "fallback text")
        self.assertIn('model_reasoning_effort="high"', captured["command"])

    def test_codex_cli_complete_raises_on_nonzero_exit(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CODEX_CLI,
            model="gpt-5-codex",
            codex_command="codex",
            codex_path="/usr/bin/codex",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CodexCLIClient(config, root)

            def fake_run(command, **kwargs):
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("partial text\n", encoding="utf-8")
                return type("Completed", (), {"returncode": 2, "stdout": "", "stderr": "boom"})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                with self.assertRaises(LLMError) as ctx:
                    client.complete("System prompt", "User prompt")

        self.assertIn("exit code 2", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_claude_cli_complete_and_image_support_contract(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CLAUDE_CLI,
            model="claude-sonnet",
            claude_command="claude",
            claude_path="/usr/bin/claude",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = ClaudeCLIClient(config, root)

            completed = type("Completed", (), {"returncode": 0, "stdout": "claude answer\n", "stderr": ""})()
            captured: dict[str, object] = {}

            def fake_run(command, **kwargs):
                captured["command"] = command
                captured["stdin"] = kwargs.get("stdin")
                return completed

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                result = client.complete("System prompt", "User prompt")

            image_path = root / "tiny.png"
            image_path.write_bytes(b"png")
            with self.assertRaises(LLMError) as ctx:
                client.analyze_image("System prompt", "User prompt", image_path)

        self.assertEqual(result.text, "claude answer")
        self.assertIs(captured["stdin"], subprocess.DEVNULL)
        self.assertIn("not supported", str(ctx.exception))

    def test_copilot_cli_complete_and_image_support_contract(self) -> None:
        config = LLMConfig(
            backend=BACKEND_COPILOT_CLI,
            model="gpt-5.3-codex",
            copilot_command="copilot",
            copilot_path="/usr/bin/copilot",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CopilotCLIClient(config, root)
            captured: dict[str, object] = {}

            def fake_run(command, **kwargs):
                captured["command"] = command
                return type("Completed", (), {"returncode": 0, "stdout": "copilot answer\n", "stderr": ""})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                result = client.complete("System prompt", "User prompt")

            image_path = root / "tiny.png"
            image_path.write_bytes(b"png")
            with self.assertRaises(LLMError) as ctx:
                client.analyze_image("System prompt", "User prompt", image_path)

        command = captured["command"]
        self.assertIn("--prompt", command)
        self.assertIn("--allow-tool=read", command)
        self.assertIn("--add-dir", command)
        self.assertIn(str(root), command)
        self.assertEqual(result.text, "copilot answer")
        self.assertIn("not supported", str(ctx.exception))

    def test_create_backend_client_returns_backend_specific_client(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            openai = create_backend_client(
                LLMConfig(backend=BACKEND_OPENAI_API, model="gpt", api_key="secret"),
                root,
            )
            codex = create_backend_client(
                LLMConfig(backend=BACKEND_CODEX_CLI, codex_path="/usr/bin/codex"),
                root,
            )
            copilot = create_backend_client(
                LLMConfig(backend=BACKEND_COPILOT_CLI, copilot_path="/usr/bin/copilot"),
                root,
            )
            nvidia_nim = create_backend_client(
                LLMConfig(
                    backend=BACKEND_NVIDIA_NIM_API,
                    api_key="nvapi_test_key",
                    nvidia_nim_api_key="nvapi_test_key",
                    base_url="https://integrate.api.nvidia.com/v1",
                    nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
                ),
                root,
            )
            claude = create_backend_client(
                LLMConfig(backend=BACKEND_CLAUDE_CLI, claude_path="/usr/bin/claude"),
                root,
            )
            anthropic = create_backend_client(
                LLMConfig(backend=BACKEND_ANTHROPIC_API, model="claude-sonnet-4-20250514", anthropic_api_key="sk-ant-test"),
                root,
            )

        self.assertIsInstance(openai, OpenAICompatClient)
        self.assertIsInstance(codex, CodexCLIClient)
        self.assertIsInstance(copilot, CopilotCLIClient)
        self.assertIsInstance(nvidia_nim, OpenAICompatClient)
        self.assertIsInstance(claude, ClaudeCLIClient)
        self.assertIsInstance(anthropic, AnthropicClient)

    def test_create_backend_client_uses_explicit_model_fallback_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = create_backend_client(
                LLMConfig(
                    backend=BACKEND_NVIDIA_NIM_API,
                    backend_requested=BACKEND_NVIDIA_NIM_API,
                    model="moonshotai/kimi-k2.5",
                    model_fallback_chain=("moonshotai/kimi-k2.5", "z-ai/glm-5.1"),
                    api_key="nvapi_test_key",
                    nvidia_nim_api_key="nvapi_test_key",
                    base_url="https://integrate.api.nvidia.com/v1",
                    nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
                ),
                root,
            )
            self.assertIsInstance(client, ModelFallbackClient)

            attempts: list[str] = []

            def fake_urlopen(http_request, timeout: int):
                del timeout
                payload = json.loads(http_request.data.decode("utf-8"))
                attempts.append(payload["model"])
                if len(attempts) == 1:
                    raise error.HTTPError(
                        url=http_request.full_url,
                        code=404,
                        msg="Not Found",
                        hdrs=None,
                        fp=io.BytesIO(b'{"error":{"message":"Unknown model"}}'),
                    )
                return FakeHTTPResponse(
                    {
                        "id": "chatcmpl_nim_fallback",
                        "choices": [{"message": {"content": "OK"}}],
                        "usage": {"total_tokens": 12},
                    }
                )

            with patch("aiwiki.llm.request.urlopen", side_effect=fake_urlopen):
                result = client.complete("System prompt", "User prompt")

        self.assertEqual(result.text, "OK")
        self.assertEqual(attempts[0], "moonshotai/kimi-k2.5")
        self.assertEqual(attempts[1], "z-ai/glm-5.1")
        self.assertEqual(client.config.model, "z-ai/glm-5.1")

    def test_nvidia_backend_no_implicit_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = create_backend_client(
                LLMConfig(
                    backend=BACKEND_NVIDIA_NIM_API,
                    backend_requested=BACKEND_NVIDIA_NIM_API,
                    model="moonshotai/kimi-k2.5",
                    model_fallback_chain=("moonshotai/kimi-k2.5",),
                    api_key="nvapi_test_key",
                    nvidia_nim_api_key="nvapi_test_key",
                    base_url="https://integrate.api.nvidia.com/v1",
                    nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
                ),
                root,
            )

        self.assertIsInstance(client, OpenAICompatClient)

    def test_advance_client_model_empty_chain(self) -> None:
        client = ModelFallbackClient(
            LLMConfig(backend=BACKEND_NVIDIA_NIM_API, model="primary"),
            Path.cwd(),
            [LLMConfig(backend=BACKEND_NVIDIA_NIM_API, model="primary")],
        )

        self.assertFalse(advance_client_model(client))
        self.assertEqual(client.index, 0)

    def test_probe_backend_reports_success_and_expected_output_match(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CODEX_CLI,
            backend_requested=BACKEND_CODEX_CLI,
            model="gpt-5.4",
            codex_command="codex",
            codex_path="/usr/bin/codex",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            def fake_run(command, **kwargs):
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("OK\n", encoding="utf-8")
                self.assertEqual(kwargs["timeout"], 11)
                return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                probe = probe_backend(config, root, timeout_seconds=11)

        self.assertTrue(probe["ok"])
        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["backend"], BACKEND_CODEX_CLI)
        self.assertEqual(probe["backend_requested"], BACKEND_CODEX_CLI)
        self.assertEqual(probe["model"], "gpt-5.4")
        self.assertTrue(probe["matched_expected_output"])
        self.assertEqual(probe["response_preview"], "OK")
        self.assertEqual(probe["error"], "")

    def test_probe_backend_classifies_quota_failures(self) -> None:
        config = LLMConfig(
            backend=BACKEND_COPILOT_CLI,
            backend_requested=BACKEND_COPILOT_CLI,
            model="gpt-5.3-codex",
            copilot_command="copilot",
            copilot_path="/usr/bin/copilot",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            def fake_run(command, **kwargs):
                del command
                del kwargs
                return type(
                    "Completed",
                    (),
                    {"returncode": 1, "stdout": "", "stderr": "402 You have no quota"},
                )()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                probe = probe_backend(config, root, timeout_seconds=7)

        self.assertFalse(probe["ok"])
        self.assertEqual(probe["status"], "quota")
        self.assertEqual(probe["backend"], BACKEND_COPILOT_CLI)
        self.assertIn("no quota", probe["error"].lower())

    def test_copilot_cli_complete_wraps_timeout_as_llm_error(self) -> None:
        config = LLMConfig(
            backend=BACKEND_COPILOT_CLI,
            model="gpt-5.3-codex",
            copilot_command="copilot",
            copilot_path="/usr/bin/copilot",
            timeout_seconds=7,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CopilotCLIClient(config, root)

            with patch("aiwiki.llm.subprocess.run", side_effect=subprocess.TimeoutExpired("copilot", 7)):
                with self.assertRaises(LLMError) as ctx:
                    client.complete("System prompt", "User prompt")

        self.assertIn("timed out after 7 seconds", str(ctx.exception))

    def test_probe_available_backends_probes_each_available_backend(self) -> None:
        config = LLMConfig(
            backend=BACKEND_CODEX_CLI,
            backend_requested=BACKEND_CODEX_CLI,
            model="gpt-5.4",
            model_requested="",
            codex_path="/usr/bin/codex",
            nvidia_nim_api_key="nvapi_test_key",
            nvidia_nim_base_url="https://integrate.api.nvidia.com/v1",
            copilot_path="/usr/bin/copilot",
            claude_path="/usr/bin/claude",
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
            root = Path(tempdir)
            with patch("aiwiki.llm.probe_backend", side_effect=fake_probe):
                probes = probe_available_backends(config, root, timeout_seconds=9)

        self.assertEqual(
            seen,
            [
                (BACKEND_CODEX_CLI, BACKEND_CODEX_CLI),
                (BACKEND_COPILOT_CLI, BACKEND_COPILOT_CLI),
                (BACKEND_CLAUDE_CLI, BACKEND_CLAUDE_CLI),
                (BACKEND_NVIDIA_NIM_API, BACKEND_NVIDIA_NIM_API),
            ],
        )
        self.assertEqual(
            [probe["backend"] for probe in probes],
            [BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI, BACKEND_NVIDIA_NIM_API],
        )

    def test_anthropic_complete_basic(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="https://api.anthropic.com",
        )
        client = AnthropicClient(config)

        captured: dict[str, object] = {}

        def fake_urlopen(http_request, timeout: int):
            del timeout
            captured["url"] = http_request.full_url
            captured["headers"] = dict(http_request.headers)
            captured["body"] = json.loads(http_request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "id": "msg_123",
                    "content": [{"type": "text", "text": "Hello from Claude."}],
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }
            )

        with patch("aiwiki.llm.request.urlopen", side_effect=fake_urlopen):
            result = client.complete("System prompt", "User prompt")

        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(captured["headers"]["X-api-key"], "sk-ant-test-key")
        self.assertEqual(captured["headers"]["Anthropic-version"], "2023-06-01")
        self.assertEqual(captured["body"]["model"], "claude-sonnet-4-20250514")
        self.assertEqual(captured["body"]["system"], "System prompt")
        self.assertEqual(result.text, "Hello from Claude.")
        self.assertEqual(result.response_id, "msg_123")
        self.assertEqual(result.usage["input_tokens"], 10)
        self.assertEqual(result.usage["output_tokens"], 5)

    def test_anthropic_complete_rejects_empty_content(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
        )
        client = AnthropicClient(config)

        with patch(
            "aiwiki.llm.request.urlopen",
            return_value=FakeHTTPResponse(
                {"id": "msg_x", "content": [{"type": "text", "text": "   "}], "usage": {}}
            ),
        ):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System", "User")

        self.assertIn("empty content", str(ctx.exception))

    def test_anthropic_complete_rejects_invalid_json(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
        )
        client = AnthropicClient(config)

        with patch("aiwiki.llm.request.urlopen", return_value=RawHTTPResponse(b"not-json")):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System", "User")

        self.assertIn("invalid JSON", str(ctx.exception))

    def test_anthropic_complete_rejects_missing_content(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
        )
        client = AnthropicClient(config)

        with patch("aiwiki.llm.request.urlopen", return_value=FakeHTTPResponse({"id": "msg_x"})):
            with self.assertRaises(LLMError) as ctx:
                client.complete("System", "User")

        self.assertIn("missing `content`", str(ctx.exception))

    def test_anthropic_analyze_image(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude-sonnet-4-20250514",
            anthropic_api_key="sk-ant-test-key",
            anthropic_base_url="https://api.anthropic.com",
        )
        client = AnthropicClient(config)
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )
        captured: dict[str, object] = {}

        with tempfile.TemporaryDirectory() as tempdir:
            image_path = Path(tempdir) / "tiny.png"
            image_path.write_bytes(image_bytes)

            def fake_urlopen(http_request, timeout: int):
                del timeout
                captured["body"] = json.loads(http_request.data.decode("utf-8"))
                return FakeHTTPResponse(
                    {
                        "id": "msg_img",
                        "content": [{"type": "text", "text": "Image analysis."}],
                        "usage": {"input_tokens": 100, "output_tokens": 20},
                    }
                )

            with patch("aiwiki.llm.request.urlopen", side_effect=fake_urlopen):
                result = client.analyze_image("System prompt", "Describe image", image_path)

        body = captured["body"]
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "image")
        self.assertEqual(content[0]["source"]["type"], "base64")
        self.assertEqual(content[0]["source"]["media_type"], "image/png")
        self.assertEqual(content[1]["type"], "text")
        self.assertEqual(content[1]["text"], "Describe image")
        self.assertEqual(result.text, "Image analysis.")


if __name__ == "__main__":
    unittest.main()
