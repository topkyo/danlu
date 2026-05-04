from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.config import BACKEND_ANTHROPIC_API, BACKEND_OPENAI_API, LLMConfig
from aiwiki.llm import AnthropicClient, OpenAICompatClient


class LLMSafetyTests(unittest.TestCase):
    def test_openai_chat_uses_safe_fetch(self) -> None:
        config = LLMConfig(backend=BACKEND_OPENAI_API, model="gpt", api_key="secret", base_url="https://api.example.com/v1")
        client = OpenAICompatClient(config)

        with patch(
            "aiwiki.llm.safe_fetch",
            return_value=(b'{"choices":[{"message":{"content":"ok"}}]}', "https://api.example.com/v1/chat/completions"),
        ) as mock_fetch:
            client.complete("system", "user")

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args[0], "https://api.example.com/v1/chat/completions")
        call_kwargs = mock_fetch.call_args.kwargs
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["max_bytes"], 10 * 1024 * 1024)

    def test_openai_image_analysis_uses_safe_fetch(self) -> None:
        config = LLMConfig(backend=BACKEND_OPENAI_API, model="gpt", api_key="secret", base_url="https://api.example.com/v1")
        client = OpenAICompatClient(config)
        image_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z3ioAAAAASUVORK5CYII="
        )

        with tempfile.TemporaryDirectory() as tempdir:
            image_path = Path(tempdir) / "tiny.png"
            image_path.write_bytes(image_bytes)
            with patch(
                "aiwiki.llm.safe_fetch",
                return_value=(b'{"choices":[{"message":{"content":"ok"}}]}', "https://api.example.com/v1/chat/completions"),
            ) as mock_fetch:
                client.analyze_image("system", "user", image_path)

        mock_fetch.assert_called_once()
        call_kwargs = mock_fetch.call_args.kwargs
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertIn("Authorization", call_kwargs["headers"])

    def test_anthropic_chat_uses_safe_fetch(self) -> None:
        config = LLMConfig(
            backend=BACKEND_ANTHROPIC_API,
            model="claude",
            anthropic_api_key="sk-ant-test",
            anthropic_base_url="https://anthropic.example.com",
        )
        client = AnthropicClient(config)

        with patch(
            "aiwiki.llm.safe_fetch",
            return_value=(b'{"content":[{"type":"text","text":"ok"}],"usage":{}}', "https://anthropic.example.com/v1/messages"),
        ) as mock_fetch:
            client.complete("system", "user")

        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args[0], "https://anthropic.example.com/v1/messages")
        call_kwargs = mock_fetch.call_args.kwargs
        self.assertEqual(call_kwargs["method"], "POST")
        self.assertIn("x-api-key", call_kwargs["headers"])


if __name__ == "__main__":
    unittest.main()
