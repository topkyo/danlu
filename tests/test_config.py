from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from aiwiki.config import (
    BACKEND_CLAUDE_CLI,
    BACKEND_CODEX_CLI,
    BACKEND_OPENAI_API,
    DEFAULT_CODEX_MODEL,
    LLMConfig,
)


class ConfigTests(unittest.TestCase):
    def _from_env(self, env: dict[str, str], which_map: dict[str, str] | None = None) -> LLMConfig:
        commands = which_map or {}
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", side_effect=lambda command: commands.get(command)):
                return LLMConfig.from_env()

    def _status_from_env(self, env: dict[str, str], which_map: dict[str, str] | None = None) -> dict[str, object]:
        commands = which_map or {}
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", side_effect=lambda command: commands.get(command)):
                return LLMConfig.status_from_env()

    def test_from_env_prefers_openai_when_model_and_api_key_are_present(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_MODEL": "gpt-4.1-mini",
                "AIWIKI_LLM_API_KEY": "secret",
                "AIWIKI_LLM_BASE_URL": "https://example.test/v1/",
                "AIWIKI_LLM_TIMEOUT": "45",
                "AIWIKI_LLM_TEMPERATURE": "0.5",
                "AIWIKI_LLM_MAX_CONTEXT_CHARS": "12000",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_OPENAI_API)
        self.assertEqual(config.model, "gpt-4.1-mini")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.timeout_seconds, 45)
        self.assertEqual(config.temperature, 0.5)
        self.assertEqual(config.max_context_chars, 12000)
        self.assertEqual(config.redacted()["api_key"], "***")

    def test_from_env_uses_requested_codex_backend_when_available(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_CODEX_COMMAND": "codex-beta",
            },
            which_map={"codex-beta": "/opt/codex-beta"},
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.codex_command, "codex-beta")
        self.assertEqual(config.codex_path, "/opt/codex-beta")
        self.assertEqual(config.model, DEFAULT_CODEX_MODEL)

    def test_from_env_preserves_explicit_codex_model(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_LLM_MODEL": "gpt-5.4-mini",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.model, "gpt-5.4-mini")

    def test_from_env_raises_for_unsupported_backend(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": "mystery-backend"})

        self.assertIn("Unsupported AIWIKI_LLM_BACKEND", str(ctx.exception))

    def test_from_env_raises_when_requested_codex_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI})

        self.assertIn("No usable LLM backend found", str(ctx.exception))

    def test_from_env_raises_when_requested_claude_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_CLAUDE_CLI})

        self.assertIn("No usable LLM backend found", str(ctx.exception))

    def test_status_from_env_reports_requested_backend_mismatch(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CLAUDE_CLI,
                "AIWIKI_CLAUDE_COMMAND": "claude-pro",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertFalse(status["configured"])
        self.assertEqual(status["backend_requested"], BACKEND_CLAUDE_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI])
        self.assertEqual(status["missing"], ["CLI command `claude-pro`"])
        self.assertEqual(status["auth_mode"], "")
        self.assertEqual(status["usage_visibility"], "")
        self.assertEqual(status["usage_accounting"], "")
        self.assertFalse(status["image_analysis_supported"])
        self.assertIn("available backends are: codex-cli", str(status["message"]))

    def test_status_from_env_reports_openai_auth_and_image_support(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_MODEL": "gpt-4.1-mini",
                "AIWIKI_LLM_API_KEY": "secret",
            },
            which_map={"claude": "/usr/bin/claude"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_OPENAI_API)
        self.assertEqual(status["available_backends"], [BACKEND_OPENAI_API, BACKEND_CLAUDE_CLI])
        self.assertEqual(status["effective_model"], "gpt-4.1-mini")
        self.assertEqual(status["model"], "gpt-4.1-mini")
        self.assertEqual(status["model_requested"], "gpt-4.1-mini")
        self.assertTrue(status["api_key_present"])
        self.assertEqual(status["auth_mode"], "api-key")
        self.assertEqual(status["usage_visibility"], "response-usage")
        self.assertEqual(status["usage_accounting"], "provider-api")
        self.assertTrue(status["image_analysis_supported"])
        self.assertEqual(status["message"], "")

    def test_status_from_env_uses_gpt_5_4_as_default_codex_model(self) -> None:
        status = self._status_from_env({}, which_map={"codex": "/usr/bin/codex"})

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_CODEX_CLI)
        self.assertEqual(status["effective_model"], DEFAULT_CODEX_MODEL)
        self.assertEqual(status["model"], DEFAULT_CODEX_MODEL)
        self.assertEqual(status["model_requested"], "")
        self.assertEqual(status["usage_visibility"], "opaque-cli")
        self.assertEqual(status["usage_accounting"], "copilot-cli-session")

    def test_status_from_env_reports_missing_auto_backends(self) -> None:
        status = self._status_from_env({})

        self.assertFalse(status["configured"])
        self.assertEqual(status["available_backends"], [])
        self.assertEqual(status["effective_model"], "")
        self.assertEqual(status["usage_visibility"], "")
        self.assertEqual(status["usage_accounting"], "")
        self.assertEqual(
            status["missing"],
            ["OPENAI-compatible API key", "LLM model name", "CLI command `codex`", "CLI command `claude`"],
        )
        self.assertIn("No usable LLM backend found", str(status["message"]))


if __name__ == "__main__":
    unittest.main()
