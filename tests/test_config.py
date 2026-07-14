from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from aiwiki.config import (
    BACKEND_ANTHROPIC_API,
    BACKEND_DEEPSEEK_API,
    BACKEND_OPENAI_API,
    BACKEND_OPENCODE_API,
    DEFAULT_ANTHROPIC_API_MODEL,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENCODE_BASE_URL,
    DEFAULT_OPENCODE_MODEL,
    LLMConfig,
)


class ConfigTests(unittest.TestCase):
    def _from_env(self, env: dict[str, str]) -> LLMConfig:
        with patch.dict(os.environ, env, clear=True):
            return LLMConfig.from_env()

    def _status_from_env(self, env: dict[str, str]) -> dict[str, object]:
        with patch.dict(os.environ, env, clear=True):
            return LLMConfig.status_from_env()

    def test_from_env_defaults_to_opencode_and_requires_key(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({})

        self.assertIn("Requested `opencode-api`", str(ctx.exception))

    def test_from_env_uses_default_opencode_profile_with_key(self) -> None:
        config = self._from_env({"AIWIKI_OPENCODE_API_KEY": "opencode_test_key"})

        self.assertEqual(config.backend, BACKEND_OPENCODE_API)
        self.assertEqual(config.backend_requested, BACKEND_OPENCODE_API)
        self.assertEqual(config.model, DEFAULT_OPENCODE_MODEL)
        self.assertEqual(config.api_key, "opencode_test_key")
        self.assertEqual(config.opencode_api_key_source, "AIWIKI_OPENCODE_API_KEY")
        self.assertEqual(config.base_url, DEFAULT_OPENCODE_BASE_URL)
        self.assertEqual(config.model_fallback_chain, (DEFAULT_OPENCODE_MODEL,))

    def test_from_env_uses_deepseek_profile_with_key_and_base_url_override(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_DEEPSEEK_API,
                "DEEPSEEK_API_KEY": "deepseek_test_key",
                "AIWIKI_DEEPSEEK_BASE_URL": "https://deepseek.example/v1/",
            }
        )

        self.assertEqual(config.backend, BACKEND_DEEPSEEK_API)
        self.assertEqual(config.model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(config.api_key, "deepseek_test_key")
        self.assertEqual(config.deepseek_api_key_source, "DEEPSEEK_API_KEY")
        self.assertEqual(config.base_url, "https://deepseek.example/v1")
        self.assertEqual(config.model_fallback_chain, (DEFAULT_DEEPSEEK_MODEL,))

    def test_from_env_uses_openai_and_anthropic_api_backends(self) -> None:
        openai = self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_OPENAI_API, "OPENAI_API_KEY": "openai_key"})
        anthropic = self._from_env(
            {"AIWIKI_LLM_BACKEND": BACKEND_ANTHROPIC_API, "ANTHROPIC_API_KEY": "anthropic_key"}
        )

        self.assertEqual(openai.backend, BACKEND_OPENAI_API)
        self.assertEqual(openai.api_key, "openai_key")
        self.assertEqual(anthropic.backend, BACKEND_ANTHROPIC_API)
        self.assertEqual(anthropic.model, DEFAULT_ANTHROPIC_API_MODEL)
        self.assertEqual(anthropic.anthropic_api_key, "anthropic_key")

    def test_model_fallback_env_keeps_backend_fallback_env_removed(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_OPENCODE_API_KEY": "opencode_test_key",
                "AIWIKI_MODEL_FALLBACK": "fallback-a, fallback-b,,fallback-a",
                "AIWIKI_BACKEND_FALLBACK": "codex-cli,nvidia-nim-api",
                "AIWIKI_BACKEND_FALLBACK_MODEL": "gpt-5.5",
            }
        )

        self.assertEqual(config.backend, BACKEND_OPENCODE_API)
        self.assertEqual(config.model_fallback_chain, (DEFAULT_OPENCODE_MODEL, "fallback-a", "fallback-b"))
        self.assertFalse(hasattr(config, "backend_fallback_chain"))
        self.assertFalse(hasattr(config, "backend_fallback_model"))

    def test_from_env_rejects_removed_or_unknown_backends(self) -> None:
        for backend in ["codex-cli", "copilot-cli", "claude-cli", "nvidia-nim-api", "openrouter-api", "mystery"]:
            with self.subTest(backend=backend):
                with self.assertRaises(RuntimeError) as ctx:
                    self._from_env({"AIWIKI_LLM_BACKEND": backend})
                self.assertIn("Unsupported AIWIKI_LLM_BACKEND", str(ctx.exception))

    def test_status_from_env_reports_available_api_backends_only(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_DEEPSEEK_API_KEY": "deepseek",
                "AIWIKI_OPENCODE_API_KEY": "opencode",
                "AIWIKI_ANTHROPIC_API_KEY": "anthropic",
                "OPENAI_API_KEY": "openai",
            }
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_OPENCODE_API)
        self.assertEqual(
            status["available_backends"],
            [BACKEND_DEEPSEEK_API, BACKEND_OPENCODE_API, BACKEND_ANTHROPIC_API, BACKEND_OPENAI_API],
        )
        self.assertTrue(status["deepseek_api_key_present"])
        self.assertEqual(status["deepseek_base_url"], DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(status["auth_mode"], "api-key")
        self.assertEqual(status["usage_visibility"], "response-usage")
        self.assertEqual(status["usage_accounting"], "opencode-api")
        self.assertNotIn("backend_fallback_chain", status)
        self.assertNotIn("backend_fallback_model", status)
        self.assertNotIn("backend_fallbacks", status)


if __name__ == "__main__":
    unittest.main()
