from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.config import BACKEND_CODEX_CLI, BACKEND_OPENAI_API, LLMConfig
from aiwiki.llm import CodexCLIClient, OpenAICompatClient


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


class LLMClientTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
