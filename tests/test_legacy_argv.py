"""Unit tests for CLI primary-surface legacy argv rewrite."""

from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from aiwiki.cli.legacy_argv import rewrite_legacy_top_level_argv


class LegacyArgvRewriteTests(unittest.TestCase):
    def test_primary_surface_unchanged(self) -> None:
        for argv in (
            ["drop", "url", "https://example.com"],
            ["today"],
            ["metrics", "--json"],
            ["advanced", "compile"],
        ):
            self.assertEqual(rewrite_legacy_top_level_argv(argv, emit_warning=False), argv)

    def test_drop_legacy_rewrites_to_primary_drop(self) -> None:
        self.assertEqual(
            rewrite_legacy_top_level_argv(
                ["--root", "/vault", "drop-url", "https://example.com", "--title", "T"],
                emit_warning=False,
            ),
            ["--root", "/vault", "drop", "url", "https://example.com", "--title", "T"],
        )
        self.assertEqual(
            rewrite_legacy_top_level_argv(["drop-note", "--text", "hi"], emit_warning=False),
            ["drop", "markdown", "--text", "hi"],
        )

    def test_operator_legacy_prefixes_advanced(self) -> None:
        self.assertEqual(
            rewrite_legacy_top_level_argv(["compile"], emit_warning=False),
            ["advanced", "compile"],
        )
        self.assertEqual(
            rewrite_legacy_top_level_argv(
                ["--model-fallback", "a", "run-ask", "Q", "--format", "report"],
                emit_warning=False,
            ),
            ["--model-fallback", "a", "advanced", "run-ask", "Q", "--format", "report"],
        )

    def test_emits_deprecation_warning(self) -> None:
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            rewrite_legacy_top_level_argv(["lint"])
        self.assertIn("deprecated", stderr.getvalue().lower())
        self.assertIn("advanced lint", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
