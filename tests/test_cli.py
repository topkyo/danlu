from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import ask_question
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_utils import parse_frontmatter
from aiwiki.cli import (
    _resolve_action_id,
    _resolve_action_ids,
    _resolve_review_pages,
    build_parser,
    main,
)
from aiwiki.execution.candidates import promote_candidate

SIGNALS_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "signals_collector"


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

    def _copy_signals_fixture_root(self, case_name: str) -> None:
        fixture_root = SIGNALS_FIXTURE_DIR / case_name / "root"
        shutil.copytree(fixture_root, self.root, dirs_exist_ok=True)

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
            ("new-vault", ["new-vault", "child-vault", "--force"], "bootstrap_new_vault", (self.root, Path("child-vault").resolve()), {"force": True}),
            ("ingest", ["ingest", "input.md", "--title", "Input"], "ingest_source", (self.root, "input.md"), {"title": "Input"}),
            ("drop-url", ["drop-url", "https://example.com"], "drop_url", (self.root, "https://example.com"), {"title": None}),
            ("drop-pdf", ["drop-pdf", "paper.pdf", "--title", "Paper"], "drop_pdf", (self.root, "paper.pdf"), {"title": "Paper"}),
            ("drop-image", ["drop-image", "chart.png", "--no-vision"], "drop_image", (self.root, "chart.png"), {"title": None, "enable_vision": False}),
            ("drop-repo", ["drop-repo", "repo", "--max-files", "10"], "drop_repo", (self.root, "repo"), {"title": None, "max_files": 10}),
            ("drop-note", ["drop-note", "--text", "meeting notes", "--kind", "transcript"], "drop_note", (self.root, None), {"title": None, "text": "meeting notes", "kind": "transcript"}),
            ("compile", ["compile"], "compile_wiki", (self.root,), {}),
            ("protocol-status", ["protocol-status"], "load_protocol_state", (self.root,), {}),
            ("protocol-status-set", ["protocol-status", "--set", "research"], "set_active_protocol", (self.root, "research"), {}),
            ("protocol-set", ["protocol-set", "ops"], "set_active_protocol", (self.root, "ops"), {}),
            ("shell-status", ["shell-status"], "shell_status", (self.root,), {}),
            ("dashboard", ["dashboard"], "shell_status_dashboard", (self.root,), {}),
            ("search", ["search", "latency", "--limit", "5"], "shell_search", (self.root, "latency"), {"limit": 5}),
            ("run-compile", ["run-compile", "--limit", "3"], "run_compile", (self.root,), {"limit": 3}),
            (
                "ask",
                ["ask", "What changed?", "--format", "slides", "--protocol", "research", "--no-cache"],
                "ask_question",
                (self.root, "What changed?", "slides"),
                {"protocol": "research", "no_cache": True, "load_protocol_learnings": False},
            ),
            ("ask-load-learnings", ["ask", "What changed?", "--load-learnings"], "ask_question", (self.root, "What changed?", "report"), {"protocol": None, "no_cache": False, "load_protocol_learnings": True}),
            (
                "run-ask",
                ["run-ask", "What changed?", "--format", "decision-memo", "--fallback-to-ask"],
                "run_ask",
                (self.root, "What changed?", "decision-memo"),
                {"protocol": None, "lean": False, "timeout_seconds": None, "no_cache": False, "fallback_to_ask": True},
            ),
            (
                "run-ask-lean-timeout",
                ["run-ask", "What changed?", "--format", "report", "--lean", "--timeout", "45", "--no-cache"],
                "run_ask",
                (self.root, "What changed?", "report"),
                {"protocol": None, "lean": True, "timeout_seconds": 45, "no_cache": True, "fallback_to_ask": False},
            ),
            (
                "run-ask-corpus",
                ["run-ask", "What next?", "--format", "report", "--corpus", "investing-foo-abc12345"],
                "run_ask",
                (self.root, "What next?", "report"),
                {"protocol": None, "lean": False, "timeout_seconds": None, "no_cache": False, "fallback_to_ask": False, "corpus_id_override": "investing-foo-abc12345"},
            ),
            (
                "ask-corpus",
                ["ask", "What next?", "--format", "report", "--corpus", "investing-foo-abc12345"],
                "ask_question",
                (self.root, "What next?", "report"),
                {"protocol": None, "no_cache": False, "load_protocol_learnings": False, "corpus_id_override": "investing-foo-abc12345"},
            ),
            ("file-back", ["file-back", "artifact.md", "--title", "Filed", "--kind", "decision", "--protocol", "ops"], "file_back", (self.root, "artifact.md"), {"title": "Filed", "kind": "decision", "protocol": "ops"}),
            (
                "alchemy-start",
                ["alchemy-start", "investing-foo-abc12345", "--topic", "VLA robotics", "--protocol", "investing"],
                "run_alchemy_start",
                (self.root, "investing-foo-abc12345", "VLA robotics"),
                {"protocol": "investing"},
            ),
            ("alchemy-distill", ["alchemy-distill", "elixir-vla-robotics-deadbeef", "--question", "What about latency?"], "run_alchemy_distill", (self.root, "elixir-vla-robotics-deadbeef", "What about latency?"), {}),
            ("alchemy-seal", ["alchemy-seal", "elixir-vla-robotics-deadbeef"], "run_alchemy_seal", (self.root, "elixir-vla-robotics-deadbeef"), {}),
            ("protocol-learn-add", ["protocol-learn-add", "general", "--title", "Learning", "--source-ref", "wiki/derived/a.md"], "run_protocol_learn_add", (self.root, "general", "Learning", ["wiki/derived/a.md"]), {}),
            ("protocol-learn-list", ["protocol-learn-list", "general"], "run_protocol_learn_list", (self.root, "general"), {"state_filter": None, "include_archived": False}),
            ("protocol-learn-show", ["protocol-learn-show", "learn-general-abc"], "run_protocol_learn_show", (self.root, "learn-general-abc"), {}),
            ("protocol-learn-supersede", ["protocol-learn-supersede", "replacement", "old-one", "old-two"], "run_protocol_learn_supersede", (self.root, "replacement", ["old-one", "old-two"]), {}),
            ("review-page", ["review-page", "page.md", "--status", "approved", "--note", "ok", "--confidence", "high"], "review_page", (self.root, "page.md", "approved"), {"note": "ok", "confidence": "high"}),
            ("review-rewrite", ["review-rewrite", "latency", "--status", "accepted", "--note", "ok"], "review_concept_rewrite", (self.root, "latency", "accepted"), {"note": "ok"}),
            ("apply-rewrite", ["apply-rewrite", "latency", "--note", "apply", "--dry-run"], "apply_concept_rewrite", (self.root, "latency"), {"note": "apply", "dry_run": True}),
            ("verify-rewrite", ["verify-rewrite", "latency", "--note", "verify"], "verify_concept_rewrite", (self.root, "latency"), {"note": "verify"}),
            ("revert-rewrite", ["revert-rewrite", "latency", "--note", "rollback"], "revert_concept_rewrite", (self.root, "latency"), {"note": "rollback"}),
            ("retire-concept", ["retire-concept", "latency", "--note", "retire"], "retire_concept", (self.root, "latency"), {"note": "retire"}),
            ("reactivate-concept", ["reactivate-concept", "latency", "--note", "wake"], "reactivate_concept", (self.root, "latency"), {"note": "wake"}),
            ("review-action", ["review-action", "act-1", "--status", "accepted", "--note", "ok"], "review_machine_memory_action", (self.root, "act-1", "accepted"), {"note": "ok"}),
            ("apply-action", ["apply-action", "act-1", "--note", "apply", "--dry-run", "--bundle", "bundle.json"], "apply_machine_memory_action", (self.root, "act-1"), {"note": "apply", "dry_run": True, "bundle_path": "bundle.json"}),
            ("revert-action", ["revert-action", "act-1", "--note", "rollback"], "revert_machine_memory_action", (self.root, "act-1"), {"note": "rollback"}),
            ("apply-archive", ["apply-archive", "entry-1", "--note", "archive", "--dry-run"], "apply_material_archive", (self.root, "entry-1"), {"note": "archive", "dry_run": True}),
            ("revert-archive", ["revert-archive", "entry-1", "--note", "restore"], "revert_material_archive", (self.root, "entry-1"), {"note": "restore"}),
            ("lint", ["lint"], "lint_wiki", (self.root,), {}),
            ("run-lint", ["run-lint"], "run_lint", (self.root,), {}),
            ("nightly", ["nightly"], "nightly_health", (self.root,), {}),
            ("run-nightly", ["run-nightly", "--compile-limit", "7", "--no-semantic-lint"], "run_nightly", (self.root,), {"compile_limit": 7, "semantic_lint": False}),
            (
                "signals-replay",
                ["signals-replay", "--source", "runtime_history", "--source", "archive", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"],
                "collect_signals",
                (self.root,),
                {"sources": ["runtime_history", "archive"], "trace_id": "550e8400-e29b-41d4-a716-446655440000"},
            ),
            ("llm-check", ["llm-check"], "llm_status", (), {}),
            ("cache-status", ["cache", "--status"], "cache_status_summary", (self.root,), {}),
            ("cache-rebuild", ["cache", "--rebuild"], "force_rebuild_query_cache", (self.root,), {}),
            ("cache-drop", ["cache", "--drop"], "drop_query_cache", (self.root,), {}),
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
                    elif target == "bootstrap_new_vault":
                        with patch("aiwiki.cli.bootstrap_new_vault", return_value={"command": name}) as mocked:
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

    def test_main_dispatches_llm_check_probe_variants(self) -> None:
        with patch("aiwiki.cli.llm_probe", return_value={"probe": {"ok": True}}) as mocked:
            code, payload, stderr = self._run_main(["llm-check", "--probe", "--probe-timeout", "9"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        mocked.assert_called_once_with(self.root, probe_all=False, timeout_seconds=9)
        self.assertTrue(payload["probe"]["ok"])

        with patch("aiwiki.cli.llm_probe", return_value={"probes": [{"backend": "codex-cli"}]}) as mocked_all:
            code, payload, stderr = self._run_main(["llm-check", "--probe-all", "--probe-timeout", "14"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        mocked_all.assert_called_once_with(self.root, probe_all=True, timeout_seconds=14)
        self.assertEqual(payload["probes"][0]["backend"], "codex-cli")

    def test_alchemy_start_requires_protocol_arg(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["alchemy-start", "investing-foo-abc12345", "--topic", "VLA robotics"])

    def test_alchemy_start_propagates_protocol_to_frontmatter(self) -> None:
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")
        ask_result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        promote_candidate(self.root, ask_result["path"])
        corpus_id = str(ask_result["active_corpus_id"])

        code, payload, stderr = self._run_main(
            ["alchemy-start", corpus_id, "--topic", "VLA robotics", "--protocol", "research"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        path = self.root / str(payload["path"])
        self.assertTrue(path.exists())
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["protocol"], "research")

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

    def test_compile_command_wraps_runtime_owned_rewrite_recovery_payload(self) -> None:
        compile_payload = {
            "compiled_at": "2026-04-22T00:00:00+00:00",
            "concept_rewrite": {
                "proposal_paths": ["wiki/rewrite-proposals/transformer-scaling.md"],
            },
        }
        rewrite_payload = {
            "updated_rewrite_proposals": [{"slug": "transformer-scaling", "proposal_path": "wiki/rewrite-proposals/transformer-scaling.md"}],
            "rewrite_recovery_actions": [{"slug": "transformer-scaling", "command": "PYTHONPATH=src python3 -m aiwiki.cli --root . review-rewrite transformer-scaling --status accepted"}],
        }

        with patch("aiwiki.cli.compile_wiki", return_value=compile_payload) as compile_mock:
            with patch("aiwiki.cli.rewrite_recovery_payload_for_paths", return_value=rewrite_payload) as recovery_mock:
                code, payload, stderr = self._run_main(["compile"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        compile_mock.assert_called_once_with(self.root)
        recovery_mock.assert_called_once_with(self.root, ["wiki/rewrite-proposals/transformer-scaling.md"])
        self.assertEqual(payload["updated_rewrite_proposals"][0]["slug"], "transformer-scaling")
        self.assertEqual(payload["rewrite_recovery_actions"][0]["slug"], "transformer-scaling")

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

    def test_cache_command_requires_single_action_flag(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "cache"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("exactly one of --status, --rebuild, or --drop", stderr.getvalue())

    def test_cache_command_rejects_multiple_action_flags(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "cache", "--status", "--drop"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("exactly one of --status, --rebuild, or --drop", stderr.getvalue())

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

    def test_review_page_resolution_helpers_cover_conflicts_and_empty_queue(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_review_pages(
                self.root,
                "page.md",
                use_next=True,
                batch=None,
                all_pending=False,
            )
        with self.assertRaises(ValueError):
            _resolve_review_pages(
                self.root,
                None,
                use_next=True,
                batch=["page-a.md"],
                all_pending=False,
            )
        with patch("aiwiki.cli.build_shell_summary", return_value={"review_controls": {"pages": []}}):
            with self.assertRaises(RuntimeError):
                _resolve_review_pages(
                    self.root,
                    None,
                    use_next=True,
                    batch=None,
                    all_pending=False,
                )
            with self.assertRaises(RuntimeError):
                _resolve_review_pages(
                    self.root,
                    None,
                    use_next=False,
                    batch=None,
                    all_pending=True,
                )

    def test_action_resolution_helpers_cover_empty_missing_ambiguous_and_batch_paths(self) -> None:
        with self.assertRaises(ValueError):
            _resolve_action_id(self.root, "   ")

        state = {
            "actions": [
                {"id": "action-a", "title": "Alpha repair", "status": "accepted", "kind": "add-source-concept-link", "active": True},
                {"id": "action-b", "title": "Alpha audit", "status": "accepted", "kind": "add-source-concept-link", "active": True},
            ]
        }
        with patch("aiwiki.cli.load_machine_memory_action_state", return_value=state):
            self.assertEqual(_resolve_action_id(self.root, "action-a"), "action-a")
            with self.assertRaises(RuntimeError):
                _resolve_action_id(self.root, "Alpha")
            with self.assertRaises(FileNotFoundError):
                _resolve_action_id(self.root, "missing")
            resolved = _resolve_action_ids(
                self.root,
                None,
                batch=["action-a", "action-b"],
                all_accepted_low_risk=False,
            )
            self.assertEqual(resolved, ["action-a", "action-b"])
            accepted = _resolve_action_ids(
                self.root,
                None,
                batch=None,
                all_accepted_low_risk=True,
            )
            self.assertEqual(accepted, ["action-a", "action-b"])

        with self.assertRaises(ValueError):
            _resolve_action_ids(self.root, "action-a", batch=["action-b"], all_accepted_low_risk=False)
        with patch("aiwiki.cli.load_machine_memory_action_state", return_value={"actions": []}):
            with self.assertRaises(RuntimeError):
                _resolve_action_ids(
                    self.root,
                    None,
                    batch=None,
                    all_accepted_low_risk=True,
                )

    def test_archive_cli_smoke_signals_replay_then_planner_log_replay(self) -> None:
        self._copy_signals_fixture_root("case_archive_apply_revert")

        sig_code, sig_payload, sig_stderr = self._run_main(
            ["signals-replay", "--source", "archive", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"]
        )
        self.assertEqual(sig_code, 0)
        self.assertEqual(sig_stderr, "")
        self.assertEqual(sig_payload["scanned_count"], 3)
        self.assertEqual(sig_payload["new_count"], 2)
        self.assertEqual(sig_payload["emitted_by_kind"]["drift"], 2)

        pl_code, pl_payload, pl_stderr = self._run_main(["planner-log-replay"])
        self.assertEqual(pl_code, 0)
        self.assertEqual(pl_stderr, "")
        self.assertEqual(pl_payload["scanned_count"], 2)
        self.assertEqual(pl_payload["new_count"], 2)
        self.assertEqual(pl_payload["emitted_by_decision"]["enqueue-heavy"], 1)
        self.assertEqual(pl_payload["emitted_by_decision"]["enqueue-light"], 1)

        planner_log_path = self.root / ".aiwiki/state/planner-log.jsonl"
        records = [json.loads(line) for line in planner_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(records), 2)
        self.assertFalse(any("unmapped_kind" in record.get("reason_codes", []) for record in records))


if __name__ == "__main__":
    unittest.main()
