from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from aiwiki.cli import build_parser, main


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_main(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = main(["--root", str(self.root), *argv])
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_build_parser_includes_extended_ask_formats(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        self.assertIsNotNone(action)
        ask_parser = next(choice for name, choice in action.choices.items() if name == "ask")
        format_action = next(item for item in ask_parser._actions if item.dest == "format")
        self.assertEqual(format_action.choices, ("report", "decision-memo", "sop", "slides", "figure"))

    def test_main_dispatches_command_handlers(self) -> None:
        cases = [
            ("layout", ["layout"], "ensure_layout", (self.root,), {}),
            ("ingest", ["ingest", "input.md", "--title", "Input"], "ingest_source", (self.root, "input.md"), {"title": "Input"}),
            ("drop-url", ["drop-url", "https://example.com"], "drop_url", (self.root, "https://example.com"), {"title": None}),
            ("drop-pdf", ["drop-pdf", "paper.pdf", "--title", "Paper"], "drop_pdf", (self.root, "paper.pdf"), {"title": "Paper"}),
            ("drop-image", ["drop-image", "chart.png", "--no-vision"], "drop_image", (self.root, "chart.png"), {"title": None, "enable_vision": False}),
            ("drop-repo", ["drop-repo", "repo", "--max-files", "10"], "drop_repo", (self.root, "repo"), {"title": None, "max_files": 10}),
            ("compile", ["compile"], "compile_wiki", (self.root,), {}),
            ("protocol-status", ["protocol-status"], "load_protocol_state", (self.root,), {}),
            ("protocol-status-set", ["protocol-status", "--set", "research"], "set_active_protocol", (self.root, "research"), {}),
            ("protocol-set", ["protocol-set", "ops"], "set_active_protocol", (self.root, "ops"), {}),
            ("shell-status", ["shell-status"], "shell_status", (self.root,), {}),
            ("run-compile", ["run-compile", "--limit", "3"], "run_compile", (self.root,), {"limit": 3}),
            ("ask", ["ask", "What changed?", "--format", "slides", "--protocol", "research"], "ask_question", (self.root, "What changed?", "slides"), {"protocol": "research"}),
            ("run-ask", ["run-ask", "What changed?", "--format", "decision-memo"], "run_ask", (self.root, "What changed?", "decision-memo"), {"protocol": None}),
            ("file-back", ["file-back", "artifact.md", "--title", "Filed", "--kind", "decision", "--protocol", "ops"], "file_back", (self.root, "artifact.md"), {"title": "Filed", "kind": "decision", "protocol": "ops"}),
            ("review-page", ["review-page", "page.md", "--status", "approved", "--note", "ok", "--confidence", "high"], "review_page", (self.root, "page.md", "approved"), {"note": "ok", "confidence": "high"}),
            ("review-rewrite", ["review-rewrite", "latency", "--status", "accepted", "--note", "ok"], "review_concept_rewrite", (self.root, "latency", "accepted"), {"note": "ok"}),
            ("apply-rewrite", ["apply-rewrite", "latency", "--note", "apply"], "apply_concept_rewrite", (self.root, "latency"), {"note": "apply"}),
            ("verify-rewrite", ["verify-rewrite", "latency", "--note", "verify"], "verify_concept_rewrite", (self.root, "latency"), {"note": "verify"}),
            ("revert-rewrite", ["revert-rewrite", "latency", "--note", "rollback"], "revert_concept_rewrite", (self.root, "latency"), {"note": "rollback"}),
            ("retire-concept", ["retire-concept", "latency", "--note", "retire"], "retire_concept", (self.root, "latency"), {"note": "retire"}),
            ("reactivate-concept", ["reactivate-concept", "latency", "--note", "wake"], "reactivate_concept", (self.root, "latency"), {"note": "wake"}),
            ("review-action", ["review-action", "act-1", "--status", "accepted", "--note", "ok"], "review_machine_memory_action", (self.root, "act-1", "accepted"), {"note": "ok"}),
            ("apply-action", ["apply-action", "act-1", "--note", "apply", "--dry-run", "--bundle", "bundle.json"], "apply_machine_memory_action", (self.root, "act-1"), {"note": "apply", "dry_run": True, "bundle_path": "bundle.json"}),
            ("revert-action", ["revert-action", "act-1", "--note", "rollback"], "revert_machine_memory_action", (self.root, "act-1"), {"note": "rollback"}),
            ("apply-archive", ["apply-archive", "entry-1", "--note", "archive"], "apply_material_archive", (self.root, "entry-1"), {"note": "archive"}),
            ("revert-archive", ["revert-archive", "entry-1", "--note", "restore"], "revert_material_archive", (self.root, "entry-1"), {"note": "restore"}),
            ("lint", ["lint"], "lint_wiki", (self.root,), {}),
            ("run-lint", ["run-lint"], "run_lint", (self.root,), {}),
            ("nightly", ["nightly"], "nightly_health", (self.root,), {}),
            ("run-nightly", ["run-nightly", "--compile-limit", "7", "--no-semantic-lint"], "run_nightly", (self.root,), {"compile_limit": 7, "semantic_lint": False}),
            ("llm-check", ["llm-check"], "llm_status", (), {}),
            ("auto-once", ["auto-once", "--compile-limit", "4", "--deterministic-only", "--no-semantic-lint"], "auto_process_once", (self.root,), {"compile_limit": 4, "deterministic_only": True, "semantic_lint": False}),
            ("watch", ["watch", "--interval", "2.5", "--compile-limit", "4", "--deterministic-only", "--no-semantic-lint", "--skip-initial", "--max-cycles", "3"], "watch_inbox", (self.root,), {"interval_seconds": 2.5, "compile_limit": 4, "deterministic_only": True, "semantic_lint": False, "process_initial": False, "max_cycles": 3}),
        ]

        for name, argv, target, expected_args, expected_kwargs in cases:
            with self.subTest(command=name):
                stdout = io.StringIO()
                with patch("sys.stdout", new=stdout):
                    if target == "ensure_layout":
                        with patch("aiwiki.cli.ensure_layout") as mocked:
                            code = main(["--root", str(self.root), *argv])
                            mocked.assert_called_once_with(*expected_args, **expected_kwargs)
                    else:
                        with patch(f"aiwiki.cli.{target}", return_value={"command": name}) as mocked:
                            code = main(["--root", str(self.root), *argv])
                            mocked.assert_called_once_with(*expected_args, **expected_kwargs)
                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                if target == "ensure_layout":
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["root"], str(self.root))
                else:
                    self.assertEqual(payload["command"], name)

    def test_main_merges_auto_process_result_for_drop_commands(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url", "note_path": "raw/inbox/note.md"}) as drop_mock:
            with patch("aiwiki.cli.auto_process_once", return_value={"compiled": 1}) as auto_mock:
                code, payload, stderr = self._run_main(
                    ["drop-url", "https://example.com", "--auto", "--deterministic-only", "--no-semantic-lint"]
                )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        drop_mock.assert_called_once_with(self.root, "https://example.com", title=None)
        auto_mock.assert_called_once_with(self.root, deterministic_only=True, semantic_lint=False)
        self.assertEqual(payload["auto_process"], {"compiled": 1})
        self.assertEqual(payload["material"], "url")

    def test_main_exits_with_error_message_on_handler_failure(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("aiwiki.cli.compile_wiki", side_effect=RuntimeError("boom")):
            with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
                with self.assertRaises(SystemExit) as ctx:
                    main(["--root", str(self.root), "compile"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("error: boom", stderr.getvalue())

    def test_main_exits_with_interrupt_status_on_keyboard_interrupt(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("aiwiki.cli.watch_inbox", side_effect=KeyboardInterrupt):
            with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
                with self.assertRaises(SystemExit) as ctx:
                    main(["--root", str(self.root), "watch"])

        self.assertEqual(ctx.exception.code, 130)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("interrupted", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
