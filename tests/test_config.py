from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from aiwiki.config import (
    BACKEND_CLAUDE_CLI,
    BACKEND_CODEX_CLI,
    BACKEND_COPILOT_CLI,
    BACKEND_NVIDIA_NIM_API,
    BACKEND_OPENCODE_API,
    BACKEND_OPENROUTER_API,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_NVIDIA_NIM_BASE_URL,
    DEFAULT_NVIDIA_NIM_MODEL,
    DEFAULT_OPENCODE_BASE_URL,
    DEFAULT_OPENCODE_MODEL,
    DEFAULT_OPENROUTER_BASE_URL,
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

    def test_from_env_defaults_to_opencode_and_requires_key(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({}, which_map={"codex": "/usr/bin/codex"})

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
        self.assertEqual(config.backend_fallback_chain, ())
        self.assertEqual(config.backend_fallback_model, "")

    def test_from_env_uses_opencode_generic_key_and_base_url_override(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_OPENCODE_API,
                "AIWIKI_LLM_API_KEY": "generic_key",
                "AIWIKI_OPENCODE_BASE_URL": "https://opencode.example/v1/",
            }
        )

        self.assertEqual(config.api_key, "generic_key")
        self.assertEqual(config.opencode_api_key_source, "AIWIKI_LLM_API_KEY")
        self.assertEqual(config.base_url, "https://opencode.example/v1")

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

    def test_from_env_preserves_explicit_codex_model_and_reasoning_effort(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_LLM_MODEL": "gpt-5.4-mini",
                "AIWIKI_CODEX_REASONING_EFFORT": "high",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.model, "gpt-5.4-mini")
        self.assertEqual(config.codex_reasoning_effort, "high")

    def test_from_env_uses_requested_nvidia_nim_backend_with_env_key(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_NVIDIA_NIM_API,
                "AIWIKI_NVIDIA_NIM_API_KEY": "nvapi_test_key",
            }
        )

        self.assertEqual(config.backend, BACKEND_NVIDIA_NIM_API)
        self.assertEqual(config.model, DEFAULT_NVIDIA_NIM_MODEL)
        self.assertEqual(config.nvidia_nim_api_key, "nvapi_test_key")
        self.assertEqual(config.nvidia_nim_api_key_source, "AIWIKI_NVIDIA_NIM_API_KEY")
        self.assertEqual(config.api_key, "nvapi_test_key")
        self.assertEqual(config.base_url, DEFAULT_NVIDIA_NIM_BASE_URL)
        self.assertEqual(config.model_fallback_chain, (DEFAULT_NVIDIA_NIM_MODEL,))

    def test_env_model_fallback(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_NVIDIA_NIM_API,
                "AIWIKI_NVIDIA_NIM_API_KEY": "nvapi_test_key",
                "AIWIKI_MODEL_FALLBACK": "fallback-a, fallback-b,,fallback-a",
            }
        )

        self.assertEqual(config.model_fallback_chain, (DEFAULT_NVIDIA_NIM_MODEL, "fallback-a", "fallback-b"))

    def test_env_backend_fallback_is_ignored(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_OPENCODE_API_KEY": "opencode_test_key",
                "AIWIKI_BACKEND_FALLBACK": "codex-cli,codex-cli,unknown-backend",
                "AIWIKI_BACKEND_FALLBACK_MODEL": "gpt-5.5",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_OPENCODE_API)
        self.assertEqual(config.backend_fallback_chain, ())
        self.assertEqual(config.backend_fallback_model, "")

    def test_env_backend_fallback_empty_keeps_default_without_backend_fallback(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_OPENCODE_API_KEY": "opencode_test_key",
                "AIWIKI_BACKEND_FALLBACK": "",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_OPENCODE_API)
        self.assertEqual(config.backend_fallback_chain, ())
        self.assertEqual(config.backend_fallback_model, "")

    def test_from_env_uses_requested_openrouter_backend(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_OPENROUTER_API,
                "AIWIKI_OPENROUTER_API_KEY": "sk-or-test",
                "AIWIKI_LLM_MODEL": "anthropic/claude-sonnet-4",
            }
        )

        self.assertEqual(config.backend, BACKEND_OPENROUTER_API)
        self.assertEqual(config.model, "anthropic/claude-sonnet-4")
        self.assertEqual(config.api_key, "sk-or-test")
        self.assertEqual(config.openrouter_api_key_source, "AIWIKI_OPENROUTER_API_KEY")
        self.assertEqual(config.base_url, DEFAULT_OPENROUTER_BASE_URL)

    def test_from_env_uses_requested_copilot_backend_when_available(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_COPILOT_CLI,
                "AIWIKI_COPILOT_COMMAND": "copilot-beta",
                "AIWIKI_LLM_MODEL": "gpt-5.3-codex",
            },
            which_map={"copilot-beta": "/opt/copilot-beta"},
        )

        self.assertEqual(config.backend, BACKEND_COPILOT_CLI)
        self.assertEqual(config.copilot_command, "copilot-beta")
        self.assertEqual(config.copilot_path, "/opt/copilot-beta")
        self.assertEqual(config.model, "gpt-5.3-codex")

    def test_from_env_raises_for_unsupported_backend(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": "mystery-backend"})

        self.assertIn("Unsupported AIWIKI_LLM_BACKEND", str(ctx.exception))

    def test_from_env_raises_when_requested_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI})

        self.assertIn("LLM backend resolution failed", str(ctx.exception))

        with self.assertRaises(RuntimeError) as nim_ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_NVIDIA_NIM_API})

        self.assertIn("LLM backend resolution failed", str(nim_ctx.exception))

    def test_status_from_env_reports_default_opencode_missing_key(self) -> None:
        status = self._status_from_env({}, which_map={"codex": "/usr/bin/codex", "copilot": "/usr/bin/copilot"})

        self.assertFalse(status["configured"])
        self.assertEqual(status["backend_requested"], BACKEND_OPENCODE_API)
        self.assertEqual(status["backend"], "")
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI])
        self.assertEqual(status["missing"], ["OpenCode API key via AIWIKI_OPENCODE_API_KEY|AIWIKI_LLM_API_KEY"])
        self.assertIn("Requested `opencode-api`", str(status["message"]))

    def test_status_from_env_reports_requested_backend_mismatch(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CLAUDE_CLI,
                "AIWIKI_CLAUDE_COMMAND": "claude-pro",
            },
            which_map={"codex": "/usr/bin/codex", "copilot": "/usr/bin/copilot"},
        )

        self.assertFalse(status["configured"])
        self.assertEqual(status["backend_requested"], BACKEND_CLAUDE_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI])
        self.assertEqual(status["missing"], ["CLI command `claude-pro`"])
        self.assertEqual(status["auth_mode"], "")
        self.assertEqual(status["usage_visibility"], "")
        self.assertEqual(status["usage_accounting"], "")
        self.assertFalse(status["image_analysis_supported"])
        self.assertIn("available backends are: codex-cli, copilot-cli", str(status["message"]))

    def test_status_from_env_reports_codex_properties(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_LLM_MODEL": "gpt-5.4",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_CODEX_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI])
        self.assertEqual(status["effective_model"], "gpt-5.4")
        self.assertEqual(status["model"], "gpt-5.4")
        self.assertEqual(status["model_requested"], "gpt-5.4")
        self.assertEqual(status["codex_reasoning_effort"], DEFAULT_CODEX_REASONING_EFFORT)
        self.assertEqual(status["auth_mode"], "cli-session")
        self.assertEqual(status["usage_visibility"], "opaque-cli")
        self.assertEqual(status["usage_accounting"], "codex-cli-session")
        self.assertTrue(status["image_analysis_supported"])
        self.assertEqual(status["message"], "")

    def test_status_from_env_reports_nvidia_nim_properties(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_NVIDIA_NIM_API,
                "AIWIKI_NVIDIA_NIM_API_KEY": "nvapi_test_key",
            }
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_NVIDIA_NIM_API)
        self.assertEqual(status["available_backends"], [BACKEND_NVIDIA_NIM_API])
        self.assertEqual(status["effective_model"], DEFAULT_NVIDIA_NIM_MODEL)
        self.assertEqual(status["model_fallback_chain"], [DEFAULT_NVIDIA_NIM_MODEL])
        self.assertTrue(status["api_key_present"])
        self.assertEqual(status["base_url"], DEFAULT_NVIDIA_NIM_BASE_URL)
        self.assertEqual(status["nvidia_nim_base_url"], DEFAULT_NVIDIA_NIM_BASE_URL)
        self.assertEqual(status["auth_mode"], "api-key")
        self.assertEqual(status["usage_visibility"], "response-usage")
        self.assertEqual(status["usage_accounting"], "nvidia-nim-api")
        self.assertTrue(status["nvidia_nim_api_key_present"])
        self.assertEqual(status["nvidia_nim_api_key_source"], "AIWIKI_NVIDIA_NIM_API_KEY")
        self.assertFalse(status["image_analysis_supported"])

    def test_status_from_env_reports_opencode_properties(self) -> None:
        status = self._status_from_env({"AIWIKI_OPENCODE_API_KEY": "opencode_test_key"})

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend_requested"], BACKEND_OPENCODE_API)
        self.assertEqual(status["backend"], BACKEND_OPENCODE_API)
        self.assertEqual(status["available_backends"], [BACKEND_OPENCODE_API])
        self.assertEqual(status["effective_model"], DEFAULT_OPENCODE_MODEL)
        self.assertEqual(status["model_fallback_chain"], [DEFAULT_OPENCODE_MODEL])
        self.assertEqual(status["backend_fallback_chain"], [])
        self.assertEqual(status["backend_fallback_model"], "")
        self.assertTrue(status["api_key_present"])
        self.assertTrue(status["opencode_api_key_present"])
        self.assertEqual(status["opencode_api_key_source"], "AIWIKI_OPENCODE_API_KEY")
        self.assertEqual(status["base_url"], DEFAULT_OPENCODE_BASE_URL)
        self.assertEqual(status["auth_mode"], "api-key")
        self.assertEqual(status["usage_visibility"], "response-usage")
        self.assertEqual(status["usage_accounting"], "opencode-api")
        self.assertFalse(status["image_analysis_supported"])

    def test_status_from_env_reports_opencode_image_capable_model(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_OPENCODE_API_KEY": "opencode_test_key",
                "AIWIKI_LLM_MODEL": "gpt-4o",
            }
        )

        self.assertEqual(status["backend"], BACKEND_OPENCODE_API)
        self.assertEqual(status["effective_model"], "gpt-4o")
        self.assertTrue(status["image_analysis_supported"])

    def test_from_env_path_overrides_are_respected(self) -> None:
        codex = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_CODEX_PATH": "/opt/custom/codex",
            }
        )
        copilot = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_COPILOT_CLI,
                "AIWIKI_COPILOT_PATH": "/opt/custom/copilot",
            }
        )

        self.assertEqual(codex.codex_path, "/opt/custom/codex")
        self.assertEqual(copilot.copilot_path, "/opt/custom/copilot")


if __name__ == "__main__":
    unittest.main()
