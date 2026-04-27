"""M7.4d Model Policy tests.

Verify:
- AIWIKI_REQUIRE_EXPLICIT_MODEL strict mode rejects implicit backend default.
- LLMConfig.status_from_env always exposes model_source field.
- model_source classification: explicit / backend_default / none.
"""
from __future__ import annotations

import os
import unittest

_AIWIKI_PREFIXES = ("AIWIKI_", "OPENAI_", "ANTHROPIC_", "NVIDIA_")


def _clean_env(monkeypatch_dict: dict[str, str] | None = None) -> None:
    """Strip all AIWIKI/LLM env vars to make tests hermetic."""
    for key in list(os.environ):
        if key.startswith(_AIWIKI_PREFIXES):
            del os.environ[key]
    if monkeypatch_dict:
        os.environ.update(monkeypatch_dict)


class ModelPolicyTests(unittest.TestCase):

    def setUp(self) -> None:
        # Snapshot env so tearDown can restore.
        self._snapshot = {k: v for k, v in os.environ.items() if k.startswith(_AIWIKI_PREFIXES)}
        _clean_env({
            # Provide a usable codex backend without needing real binary.
            "AIWIKI_CODEX_PATH": "/usr/bin/true",
            "AIWIKI_LLM_BACKEND": "codex-cli",
        })

    def tearDown(self) -> None:
        for key in list(os.environ):
            if key.startswith(_AIWIKI_PREFIXES):
                del os.environ[key]
        os.environ.update(self._snapshot)

    def test_status_includes_model_source_field(self) -> None:
        from aiwiki.config import LLMConfig

        status = LLMConfig.status_from_env()
        self.assertIn("model_source", status)
        # Default codex-cli without explicit model → backend_default
        self.assertEqual(status["model_source"], "backend_default")
        self.assertTrue(status["model"], "Effective model must be non-empty for codex-cli default")

    def test_explicit_model_marks_source_explicit(self) -> None:
        from aiwiki.config import LLMConfig

        os.environ["AIWIKI_LLM_MODEL"] = "gpt-custom"
        status = LLMConfig.status_from_env()
        self.assertEqual(status["model_source"], "explicit")
        self.assertEqual(status["model"], "gpt-custom")

    def test_strict_mode_rejects_implicit_default(self) -> None:
        from aiwiki.config import LLMConfig

        os.environ["AIWIKI_REQUIRE_EXPLICIT_MODEL"] = "1"
        with self.assertRaises(RuntimeError) as ctx:
            LLMConfig.from_env()
        msg = str(ctx.exception)
        self.assertIn("AIWIKI_REQUIRE_EXPLICIT_MODEL", msg)
        self.assertIn("AIWIKI_LLM_MODEL", msg)
        # Message must surface the would-be fallback so users know what they
        # are rejecting.
        self.assertIn("codex-cli", msg)

    def test_strict_mode_passes_with_explicit_model(self) -> None:
        from aiwiki.config import LLMConfig

        os.environ["AIWIKI_REQUIRE_EXPLICIT_MODEL"] = "1"
        os.environ["AIWIKI_LLM_MODEL"] = "gpt-explicit"
        config = LLMConfig.from_env()
        self.assertEqual(config.model, "gpt-explicit")
        self.assertEqual(config.model_requested, "gpt-explicit")

    def test_strict_mode_off_default_fallback_unchanged(self) -> None:
        # Without strict flag, behavior is identical to pre-M7.4d.
        from aiwiki.config import LLMConfig

        # No AIWIKI_REQUIRE_EXPLICIT_MODEL set, no model set.
        config = LLMConfig.from_env()
        # Should not raise; model populated from backend default.
        self.assertTrue(config.model)
        self.assertEqual(config.model_requested, "")


if __name__ == "__main__":
    unittest.main()
