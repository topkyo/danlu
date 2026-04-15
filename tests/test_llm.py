from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

from aiwiki.config import BACKEND_CLAUDE_CLI, BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig
from aiwiki.llm import ClaudeCLIClient, CodexCLIClient, LLMError, OpenAICompatClient, create_backend_client


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
        self.assertIn(str(image_path), command)
        self.assertEqual(result.text, "- Visual summary\n- Confidence: low")

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
            codex_command="codex",
            codex_path="/usr/bin/codex",
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            client = CodexCLIClient(config, root)

            def fake_run(command, **kwargs):
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("", encoding="utf-8")
                return type("Completed", (), {"returncode": 0, "stdout": "fallback text\n", "stderr": ""})()

            with patch("aiwiki.llm.subprocess.run", side_effect=fake_run):
                result = client.complete("System prompt", "User prompt")

        self.assertEqual(result.text, "fallback text")

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
            with patch("aiwiki.llm.subprocess.run", return_value=completed):
                result = client.complete("System prompt", "User prompt")

            image_path = root / "tiny.png"
            image_path.write_bytes(b"png")
            with self.assertRaises(LLMError) as ctx:
                client.analyze_image("System prompt", "User prompt", image_path)

        self.assertEqual(result.text, "claude answer")
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
            claude = create_backend_client(
                LLMConfig(backend=BACKEND_CLAUDE_CLI, claude_path="/usr/bin/claude"),
                root,
            )

        self.assertIsInstance(openai, OpenAICompatClient)
        self.assertIsInstance(codex, CodexCLIClient)
        self.assertIsInstance(claude, ClaudeCLIClient)


if __name__ == "__main__":
    unittest.main()
