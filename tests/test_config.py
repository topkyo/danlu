from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from aiwiki.config import (
    BACKEND_CLAUDE_CLI,
    BACKEND_CODEX_CLI,
    BACKEND_COPILOT_CLI,
    BACKEND_GITHUB_MODELS_API,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_GITHUB_MODELS_MODEL,
    LLMConfig,
)


class ConfigTests(unittest.TestCase):
    def _from_env(
        self,
        env: dict[str, str],
        which_map: dict[str, str] | None = None,
        gh_stdout: str = "",
        gh_returncode: int = 1,
    ) -> LLMConfig:
        commands = which_map or {}
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", side_effect=lambda command: commands.get(command)):
                with patch(
                    "aiwiki.config.subprocess.run",
                    return_value=type("Completed", (), {"returncode": gh_returncode, "stdout": gh_stdout, "stderr": ""})(),
                ):
                    return LLMConfig.from_env()

    def _status_from_env(
        self,
        env: dict[str, str],
        which_map: dict[str, str] | None = None,
        gh_stdout: str = "",
        gh_returncode: int = 1,
    ) -> dict[str, object]:
        commands = which_map or {}
        with patch.dict(os.environ, env, clear=True):
            with patch("aiwiki.config.shutil.which", side_effect=lambda command: commands.get(command)):
                with patch(
                    "aiwiki.config.subprocess.run",
                    return_value=type("Completed", (), {"returncode": gh_returncode, "stdout": gh_stdout, "stderr": ""})(),
                ):
                    return LLMConfig.status_from_env()

    def test_from_env_prefers_codex_before_other_cli_backends(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_MODEL": "gpt-4.1-mini",
                "AIWIKI_LLM_BASE_URL": "https://example.test/v1/",
                "AIWIKI_LLM_TIMEOUT": "45",
                "AIWIKI_LLM_TEMPERATURE": "0.5",
                "AIWIKI_LLM_MAX_CONTEXT_CHARS": "12000",
            },
            which_map={
                "codex": "/usr/bin/codex",
                "copilot": "/usr/bin/copilot",
                "claude": "/usr/bin/claude",
            },
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.model, "gpt-4.1-mini")
        self.assertEqual(config.base_url, "https://example.test/v1")
        self.assertEqual(config.timeout_seconds, 45)
        self.assertEqual(config.temperature, 0.5)
        self.assertEqual(config.max_context_chars, 12000)
        self.assertEqual(config.codex_reasoning_effort, DEFAULT_CODEX_REASONING_EFFORT)
        self.assertEqual(config.redacted()["api_key"], "")

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

    def test_from_env_preserves_explicit_codex_reasoning_effort(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_CODEX_REASONING_EFFORT": "high",
            },
            which_map={"codex": "/usr/bin/codex"},
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.codex_reasoning_effort, "high")

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

    def test_from_env_uses_requested_github_models_backend_with_env_token(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_GITHUB_MODELS_API,
                "GH_TOKEN": "gho_test_token",
            },
            which_map={"gh": "/usr/bin/gh"},
        )

        self.assertEqual(config.backend, BACKEND_GITHUB_MODELS_API)
        self.assertEqual(config.model, DEFAULT_GITHUB_MODELS_MODEL)
        self.assertEqual(config.github_token, "gho_test_token")
        self.assertEqual(config.github_token_source, "GH_TOKEN")

    def test_from_env_uses_requested_github_models_backend_with_gh_auth_token_fallback(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_GITHUB_MODELS_API,
            },
            which_map={"gh": "/usr/bin/gh"},
            gh_stdout="gho_from_gh\n",
            gh_returncode=0,
        )

        self.assertEqual(config.backend, BACKEND_GITHUB_MODELS_API)
        self.assertEqual(config.github_token, "gho_from_gh")
        self.assertEqual(config.github_token_source, "gh auth token")

    def test_from_env_raises_for_unsupported_backend(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": "mystery-backend"})

        self.assertIn("Unsupported AIWIKI_LLM_BACKEND", str(ctx.exception))

    def test_from_env_raises_when_requested_codex_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI})

        self.assertIn("No usable LLM backend found", str(ctx.exception))

    def test_from_env_raises_when_requested_copilot_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_COPILOT_CLI})

        self.assertIn("No usable LLM backend found", str(ctx.exception))

    def test_from_env_raises_when_requested_github_models_backend_is_unavailable(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self._from_env({"AIWIKI_LLM_BACKEND": BACKEND_GITHUB_MODELS_API})

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
            which_map={
                "codex": "/usr/bin/codex",
                "copilot": "/usr/bin/copilot",
            },
        )

        self.assertFalse(status["configured"])
        self.assertEqual(status["backend_requested"], BACKEND_CLAUDE_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_CODEX_CLI, BACKEND_COPILOT_CLI])
        self.assertEqual(status["missing"], ["CLI command `claude-pro`"])
        self.assertEqual(status["auth_mode"], "")
        self.assertEqual(status["usage_visibility"], "")
        self.assertEqual(status["usage_accounting"], "")
        self.assertFalse(status["image_analysis_supported"])
        self.assertIn("available backends are: codex-cli", str(status["message"]))

    def test_status_from_env_reports_copilot_cli_properties(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_COPILOT_CLI,
                "AIWIKI_LLM_MODEL": "claude-haiku-4.5",
            },
            which_map={"copilot": "/usr/bin/copilot"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_COPILOT_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_COPILOT_CLI])
        self.assertEqual(status["effective_model"], "claude-haiku-4.5")
        self.assertEqual(status["model"], "claude-haiku-4.5")
        self.assertEqual(status["model_requested"], "claude-haiku-4.5")
        self.assertEqual(status["auth_mode"], "cli-session")
        self.assertEqual(status["usage_visibility"], "opaque-cli")
        self.assertEqual(status["usage_accounting"], "copilot-cli-session")
        self.assertFalse(status["image_analysis_supported"])
        self.assertEqual(status["message"], "")

    def test_status_from_env_reports_github_models_properties(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_GITHUB_MODELS_API,
                "GH_TOKEN": "gho_test_token",
            },
            which_map={"gh": "/usr/bin/gh"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_GITHUB_MODELS_API)
        self.assertEqual(status["available_backends"], [BACKEND_GITHUB_MODELS_API])
        self.assertEqual(status["effective_model"], DEFAULT_GITHUB_MODELS_MODEL)
        self.assertEqual(status["max_context_chars"], 14000)
        self.assertEqual(status["auth_mode"], "github-token-or-gh-cli")
        self.assertEqual(status["usage_visibility"], "response-usage")
        self.assertEqual(status["usage_accounting"], "github-models-api")
        self.assertTrue(status["github_token_present"])
        self.assertEqual(status["github_token_source"], "GH_TOKEN")
        self.assertFalse(status["image_analysis_supported"])

    def test_status_from_env_uses_gpt_5_4_as_default_codex_model(self) -> None:
        status = self._status_from_env({}, which_map={"codex": "/usr/bin/codex"})

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_CODEX_CLI)
        self.assertEqual(status["effective_model"], DEFAULT_CODEX_MODEL)
        self.assertEqual(status["model"], DEFAULT_CODEX_MODEL)
        self.assertEqual(status["model_requested"], "")
        self.assertEqual(status["codex_reasoning_effort"], DEFAULT_CODEX_REASONING_EFFORT)
        self.assertEqual(status["usage_visibility"], "opaque-cli")
        self.assertEqual(status["usage_accounting"], "codex-cli-session")

    def test_status_from_env_reports_missing_auto_backends(self) -> None:
        status = self._status_from_env({})

        self.assertFalse(status["configured"])
        self.assertEqual(status["available_backends"], [])
        self.assertEqual(status["effective_model"], "")
        self.assertEqual(status["usage_visibility"], "")
        self.assertEqual(status["usage_accounting"], "")
        self.assertEqual(
            status["missing"],
            [
                "CLI command `codex`",
                "CLI command `copilot`",
                "CLI command `claude`",
            ],
        )
        self.assertIn("No usable LLM backend found", str(status["message"]))

    def test_status_from_env_prefers_copilot_when_codex_missing_even_if_github_token_exists(self) -> None:
        status = self._status_from_env(
            {
                "GH_TOKEN": "gho_test_token",
            },
            which_map={"copilot": "/usr/bin/copilot", "claude": "/usr/bin/claude"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_COPILOT_CLI)
        self.assertEqual(
            status["available_backends"],
            [BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI, BACKEND_GITHUB_MODELS_API],
        )
        self.assertEqual(status["effective_model"], "")
        self.assertEqual(status["max_context_chars"], 24000)
        self.assertEqual(status["usage_accounting"], "copilot-cli-session")

    def test_status_from_env_uses_copilot_when_codex_missing(self) -> None:
        status = self._status_from_env(
            {
                "AIWIKI_LLM_MODEL": "gpt-5.2",
            },
            which_map={"copilot": "/usr/bin/copilot", "claude": "/usr/bin/claude"},
        )

        self.assertTrue(status["configured"])
        self.assertEqual(status["backend"], BACKEND_COPILOT_CLI)
        self.assertEqual(status["available_backends"], [BACKEND_COPILOT_CLI, BACKEND_CLAUDE_CLI])
        self.assertEqual(status["effective_model"], "gpt-5.2")
        self.assertEqual(status["usage_accounting"], "copilot-cli-session")

    def test_from_env_codex_path_override(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_CODEX_CLI,
                "AIWIKI_CODEX_PATH": "/opt/custom/codex",
            },
        )

        self.assertEqual(config.backend, BACKEND_CODEX_CLI)
        self.assertEqual(config.codex_path, "/opt/custom/codex")

    def test_from_env_copilot_path_override(self) -> None:
        config = self._from_env(
            {
                "AIWIKI_LLM_BACKEND": BACKEND_COPILOT_CLI,
                "AIWIKI_COPILOT_PATH": "/opt/custom/copilot",
            },
        )

        self.assertEqual(config.backend, BACKEND_COPILOT_CLI)
        self.assertEqual(config.copilot_path, "/opt/custom/copilot")


if __name__ == "__main__":
    unittest.main()
