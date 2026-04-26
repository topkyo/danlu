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

    def _run_main_raw(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = main(["--root", str(self.root), *argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def _write_jsonl(self, relative_path: str, records: list[dict[str, object]]) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    def _read_jsonl(self, relative_path: str) -> list[dict[str, object]]:
        path = self.root / relative_path
        if not path.exists():
            return []
        records: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
        return records

    @staticmethod
    def _signal_record(
        signal_id: str,
        *,
        kind: str,
        trace_id: str,
        emitted_at: str,
        severity: str = "medium",
        source_event_ref: str = ".aiwiki/state/runtime-history.jsonl#L1",
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{kind}:research:runtime_history:{signal_id}",
            "kind": kind,
            "scope": {
                "protocol": "research",
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": [],
                "judgment_refs": [],
            },
            "severity": severity,
            "evidence_refs": [],
            "emitted_at": emitted_at,
            "emitted_by": "compile",
            "source_kind": "runtime_history",
            "source_event_ref": source_event_ref,
            "trace_id": trace_id,
        }

    @staticmethod
    def _planner_record(
        signal_id: str,
        *,
        decision: str,
        trace_id: str,
        decided_at: str,
        mode: str = "observe_only",
        reason_codes: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": signal_id,
            "dedupe_key": f"{signal_id}:{mode}",
            "trace_id": trace_id,
            "decision": decision,
            "mode": mode,
            "reason_codes": reason_codes or ["review_feedback_routine"],
            "budget_used": {},
            "locks_acquired": [],
            "primitive_refs": [],
            "side_effects_allowed": False,
            "decided_at": decided_at,
        }

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

    def test_legacy_settled_alias_is_absent(self) -> None:
        from aiwiki import runner
        from aiwiki.execution import alchemy

        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        legacy_command = "alchemy-" + "seal"
        self.assertNotIn(legacy_command, action.choices)
        self.assertFalse(hasattr(runner, "run_alchemy_" + "seal"))
        self.assertFalse(hasattr(alchemy, "seal_" + "elixir"))

    def test_removed_settled_alias_parse_is_rejected(self) -> None:
        parser = build_parser()
        removed_command = "alchemy-" + "seal"

        with self.assertRaises(SystemExit):
            parser.parse_args([removed_command, "elixir-vla-robotics-deadbeef"])

    def test_main_dispatches_command_handlers(self) -> None:
        (self.root / "proposal-content.md").write_text("Updated prompt.\n", encoding="utf-8")
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
            ("alchemy-finalize", ["alchemy-finalize", "--elixir-id", "elixir-vla-robotics-deadbeef"], "run_alchemy_finalize", (self.root,), {"elixir_id": "elixir-vla-robotics-deadbeef"}),
            (
                "alchemy-promote",
                ["alchemy-promote", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "ship it"],
                "run_alchemy_promote",
                (self.root,),
                {"elixir_id": "elixir-vla-robotics-deadbeef", "note": "ship it"},
            ),
            (
                "alchemy-heavy-dry-run",
                ["alchemy", "heavy", "all", "--dry-run", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7"],
                "run_alchemy_lane_dry_run",
                (self.root,),
                {
                    "lane": "heavy",
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                },
            ),
            (
                "alchemy-heavy-apply",
                [
                    "alchemy",
                    "heavy",
                    "all",
                    "--apply",
                    "--action-id",
                    "act-1",
                    "--action-id",
                    "act-2",
                    "--primitive",
                    "compile",
                    "--note",
                    "ship",
                ],
                "run_alchemy_lane_apply",
                (self.root,),
                {
                    "lane": "heavy",
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": None,
                    "max_pages": None,
                    "max_tokens": None,
                    "action_ids": ["act-1", "act-2"],
                    "primitives": ["compile"],
                    "note": "ship",
                },
            ),
            (
                "alchemy-legacy-migration-preview",
                ["alchemy", "legacy-migration", "--dry-run", "--limit", "4"],
                "run_alchemy_legacy_migration_preview",
                (self.root,),
                {"limit": 4},
            ),
            (
                "alchemy-legacy-migration-apply",
                ["alchemy", "legacy-migration", "--apply", "--limit", "4", "--note", "migrate"],
                "run_alchemy_legacy_migration_apply",
                (self.root,),
                {"limit": 4, "note": "migrate"},
            ),
            (
                "alchemy-auto-apply",
                [
                    "alchemy",
                    "auto",
                    "--apply",
                    "--scope",
                    "protocol:ops",
                    "--lane",
                    "light",
                    "--primitive",
                    "compile",
                    "--note",
                    "auto",
                ],
                "run_alchemy_auto",
                (self.root,),
                {
                    "apply": True,
                    "lanes": ["light"],
                    "scope": "protocol:ops",
                    "primitives": ["compile"],
                    "note": "auto",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": None,
                    "max_pages": None,
                    "max_tokens": None,
                },
            ),
            (
                "alchemy-superseded-cleanup-preview",
                ["alchemy", "superseded-cleanup", "--dry-run", "--limit", "4"],
                "run_alchemy_superseded_cleanup_preview",
                (self.root,),
                {"limit": 4},
            ),
            (
                "alchemy-superseded-cleanup-apply",
                ["alchemy", "superseded-cleanup", "--apply", "--limit", "4", "--note", "cleanup"],
                "run_alchemy_superseded_cleanup_apply",
                (self.root,),
                {"limit": 4, "note": "cleanup"},
            ),
            (
                "l3-proposal-create",
                [
                    "l3-proposal-create",
                    "--kind",
                    "prompt_proposal",
                    "--proposal-id",
                    "prop-ask",
                    "--target-file",
                    "prompts/ask.md",
                    "--content-file",
                    "proposal-content.md",
                    "--rationale",
                    "tighten",
                    "--evidence-ref",
                    "receipt-1",
                    "--signal-id",
                    "sig-1",
                ],
                "run_l3_proposal_create",
                (self.root,),
                {
                    "kind": "prompt_proposal",
                    "proposal_id": "prop-ask",
                    "target_file": "prompts/ask.md",
                    "content": "Updated prompt.\n",
                    "rationale": "tighten",
                    "evidence_refs": ["receipt-1"],
                    "signal_ids": ["sig-1"],
                    "pattern": "manual_fixture",
                },
            ),
            (
                "l3-proposal-generate",
                ["l3-proposal-generate", "--apply", "--planner-log-path", "custom/planner-log.jsonl", "--limit", "3"],
                "run_l3_proposal_generate",
                (self.root,),
                {"planner_log_path": Path("custom/planner-log.jsonl"), "limit": 3, "apply": True},
            ),
            (
                "review-proposals",
                ["review", "proposals", "--kind", "prompt_proposal", "--state", "candidate", "--json"],
                "run_l3_proposal_list",
                (self.root,),
                {"kind": "prompt_proposal", "state": "candidate"},
            ),
            (
                "review-proposal-generation",
                ["review", "proposal-generation", "--planner-log-path", "custom/planner-log.jsonl", "--limit", "3", "--json"],
                "run_l3_proposal_generation_preview",
                (self.root,),
                {"planner_log_path": Path("custom/planner-log.jsonl"), "limit": 3},
            ),
            (
                "review-proposal-reject",
                ["review", "proposal", "prop-ask", "--status", "rejected", "--note", "skip"],
                "run_l3_proposal_reject",
                (self.root, "prop-ask"),
                {"note": "skip"},
            ),
            (
                "apply-l3-proposal",
                ["apply", "prop-ask", "--note", "accept"],
                "run_l3_proposal_apply",
                (self.root, "prop-ask"),
                {"note": "accept"},
            ),
            (
                "revert-l3-proposal",
                ["revert", "l3-proposal-apply-prop-ask", "--note", "undo"],
                "run_l3_proposal_revert",
                (self.root, "l3-proposal-apply-prop-ask"),
                {"note": "undo"},
            ),
            ("protocol-learn-add", ["protocol-learn-add", "general", "--title", "Learning", "--source-ref", "wiki/derived/a.md"], "run_protocol_learn_add", (self.root, "general", "Learning", ["wiki/derived/a.md"]), {}),
            ("protocol-learn-list", ["protocol-learn-list", "general"], "run_protocol_learn_list", (self.root, "general"), {"state_filter": None, "include_archived": False}),
            ("protocol-learn-show", ["protocol-learn-show", "learn-general-abc"], "run_protocol_learn_show", (self.root, "learn-general-abc"), {}),
            ("protocol-learn-revert-activate", ["protocol-learn-revert-activate", "learn-general-abc", "--note", "undo"], "run_protocol_learn_revert_activate", (self.root, "learn-general-abc"), {"note": "undo"}),
            (
                "signals-list",
                ["signals-list", "--kind", "drift", "--trace-id", "550e8400-e29b-41d4-a716-446655440000", "--since", "2026-04-24T00:00:00Z", "--limit", "7", "--json"],
                "run_signals_list",
                (self.root,),
                {
                    "kind": "drift",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "since": "2026-04-24T00:00:00Z",
                    "limit": 7,
                },
            ),
            ("signals-show", ["signals-show", "sig-20260424-abc123", "--json"], "run_signals_show", (self.root, "sig-20260424-abc123"), {}),
            (
                "planner-log-list",
                [
                    "planner-log-list",
                    "--decision",
                    "enqueue-heavy",
                    "--signal-id",
                    "sig-20260424-abc123",
                    "--trace-id",
                    "550e8400-e29b-41d4-a716-446655440000",
                    "--since",
                    "2026-04-24T00:00:00Z",
                    "--limit",
                    "9",
                    "--json",
                ],
                "run_planner_log_list",
                (self.root,),
                {
                    "decision": "enqueue-heavy",
                    "signal_id": "sig-20260424-abc123",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "since": "2026-04-24T00:00:00Z",
                    "limit": 9,
                },
            ),
            (
                "planner-log-rollback",
                [
                    "planner-log-rollback",
                    "--apply",
                    "--signal-id",
                    "sig-20260424-abc123",
                    "--trace-id",
                    "550e8400-e29b-41d4-a716-446655440000",
                    "--limit",
                    "5",
                ],
                "run_planner_log_rollback",
                (self.root,),
                {
                    "signal_id": "sig-20260424-abc123",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "limit": 5,
                    "apply": True,
                },
            ),
            (
                "audit-preview",
                ["audit-preview", "--dry-run", "--limit", "6"],
                "run_audit_preview",
                (self.root,),
                {"limit": 6},
            ),
            (
                "audit-backfill",
                ["audit-backfill", "--apply", "--limit", "6"],
                "run_audit_backfill",
                (self.root,),
                {"limit": 6, "apply": True},
            ),
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

    def test_alchemy_finalize_cli_smoke(self) -> None:
        with patch("aiwiki.cli.run_alchemy_finalize", return_value={"command": "alchemy-finalize"}) as mocked:
            code, payload, stderr = self._run_main(["alchemy-finalize", "--elixir-id", "elixir-vla-robotics-deadbeef"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload.get("command"), "alchemy-finalize")
        mocked.assert_called_once_with(self.root, elixir_id="elixir-vla-robotics-deadbeef")

    def test_alchemy_finalize_requires_elixir_id(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["alchemy-finalize"])

    def test_alchemy_promote_cli_smoke(self) -> None:
        with patch("aiwiki.cli.run_alchemy_promote", return_value={"command": "alchemy-promote"}) as mocked:
            code, payload, stderr = self._run_main(
                ["alchemy-promote", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "ship it"]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload.get("command"), "alchemy-promote")
        mocked.assert_called_once_with(
            self.root,
            elixir_id="elixir-vla-robotics-deadbeef",
            note="ship it",
        )

    def test_alchemy_promote_requires_elixir_id(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["alchemy-promote"])

    def test_alchemy_revert_cli_smoke(self) -> None:
        with patch(
            "aiwiki.cli.run_alchemy_revert",
            return_value=self.root / "output" / "_candidates" / "elixirs" / "elixir-vla-robotics-deadbeef.md",
        ) as mocked:
            code, payload, stderr = self._run_main(
                ["alchemy-revert", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "undo"]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload.get("elixir_id"), "elixir-vla-robotics-deadbeef")
        self.assertEqual(payload.get("path"), "output/_candidates/elixirs/elixir-vla-robotics-deadbeef.md")
        mocked.assert_called_once_with(
            self.root,
            elixir_id="elixir-vla-robotics-deadbeef",
            note="undo",
        )

    def test_alchemy_revert_requires_elixir_id(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["alchemy-revert"])

    def test_alchemy_demote_cli_smoke(self) -> None:
        with patch(
            "aiwiki.cli.run_alchemy_demote",
            return_value=self.root / "output" / "_candidates" / "elixirs" / "elixir-vla-robotics-deadbeef.md",
        ) as mocked:
            code, payload, stderr = self._run_main(
                ["alchemy-demote", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "reopen"]
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload.get("elixir_id"), "elixir-vla-robotics-deadbeef")
        self.assertEqual(payload.get("path"), "output/_candidates/elixirs/elixir-vla-robotics-deadbeef.md")
        mocked.assert_called_once_with(
            self.root,
            elixir_id="elixir-vla-robotics-deadbeef",
            note="reopen",
        )

    def test_alchemy_demote_requires_elixir_id(self) -> None:
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["alchemy-demote"])

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
        self.assertEqual(pl_payload["emitted_by_decision"]["enqueue-heavy"], 0)
        self.assertEqual(pl_payload["emitted_by_decision"]["enqueue-light"], 1)
        self.assertEqual(pl_payload["emitted_by_decision"]["generate-proposal"], 1)

        planner_log_path = self.root / ".aiwiki/state/planner-log.jsonl"
        records = [json.loads(line) for line in planner_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(records), 2)
        self.assertFalse(any("unmapped_kind" in record.get("reason_codes", []) for record in records))

    def test_signals_list_cli_text_output(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal_record(
                    "sig-20260424-txt0001",
                    kind="drift",
                    severity="high",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    emitted_at="2026-04-24T12:00:00Z",
                    source_event_ref=".aiwiki/state/execution-receipts.jsonl#L1",
                ),
                self._signal_record(
                    "sig-20260424-txt0002",
                    kind="review_feedback",
                    trace_id="550e8400-e29b-41d4-a716-446655440001",
                    emitted_at="2026-04-24T12:01:00Z",
                ),
            ],
        )

        code, stdout, stderr = self._run_main_raw(
            [
                "signals-list",
                "--kind",
                "drift",
                "--trace-id",
                "550e8400-e29b-41d4-a716-446655440000",
            ]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("sig-20260424-txt0001", stdout)
        self.assertIn("drift", stdout)
        self.assertIn("high", stdout)
        self.assertNotIn("sig-20260424-txt0002", stdout)

    def test_signals_list_cli_json_output(self) -> None:
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal_record(
                    "sig-20260424-json0001",
                    kind="runtime_failure",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    emitted_at="2026-04-24T12:05:00Z",
                )
            ],
        )

        code, payload, stderr = self._run_main(["signals-list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["signal_id"], "sig-20260424-json0001")
        self.assertEqual(payload[0]["kind"], "runtime_failure")

    def test_signals_show_cli_includes_planner_decisions(self) -> None:
        signal_id = "sig-20260424-show0001"
        self._write_jsonl(
            ".aiwiki/state/signals.jsonl",
            [
                self._signal_record(
                    signal_id,
                    kind="elixir_dependency_break",
                    severity="high",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    emitted_at="2026-04-24T12:10:00Z",
                    source_event_ref=".aiwiki/state/execution-receipts.jsonl#L9",
                )
            ],
        )
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner_record(
                    signal_id,
                    decision="generate-proposal",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    decided_at="2026-04-24T12:11:00Z",
                    reason_codes=["elixir_dependency_break_observed", "proposal_recommended"],
                )
            ],
        )

        code, stdout, stderr = self._run_main_raw(["signals-show", signal_id])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Signal:", stdout)
        self.assertIn("kind: elixir_dependency_break", stdout)
        self.assertIn("Related planner decisions:", stdout)
        self.assertIn("generate-proposal", stdout)

    def test_signals_show_cli_not_found_exits_nonzero(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "signals-show", "sig-20260424-missing"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("signal not found: sig-20260424-missing", stderr.getvalue())

    def test_planner_log_list_cli_text_output(self) -> None:
        signal_id = "sig-20260424-pltxt001"
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner_record(
                    signal_id,
                    decision="generate-proposal",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    decided_at="2026-04-24T12:20:00Z",
                    reason_codes=["elixir_dependency_break_observed", "proposal_recommended"],
                ),
                self._planner_record(
                    "sig-20260424-pltxt002",
                    decision="enqueue-light",
                    trace_id="550e8400-e29b-41d4-a716-446655440001",
                    decided_at="2026-04-24T12:19:00Z",
                    reason_codes=["review_feedback_routine"],
                ),
            ],
        )

        code, stdout, stderr = self._run_main_raw(["planner-log-list", "--decision", "generate-proposal"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("generate-proposal", stdout)
        self.assertIn(signal_id, stdout)
        self.assertNotIn("enqueue-light", stdout)

    def test_planner_log_list_cli_json_output(self) -> None:
        signal_id = "sig-20260424-pljson001"
        self._write_jsonl(
            ".aiwiki/state/planner-log.jsonl",
            [
                self._planner_record(
                    signal_id,
                    decision="ignore",
                    trace_id="550e8400-e29b-41d4-a716-446655440000",
                    decided_at="2026-04-24T12:25:00Z",
                    reason_codes=["schedule_tick_routine"],
                )
            ],
        )

        code, payload, stderr = self._run_main(["planner-log-list", "--signal-id", signal_id, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["signal_id"], signal_id)
        self.assertEqual(payload[0]["decision"], "ignore")

    def test_signals_list_invalid_since_exits_nonzero(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "signals-list", "--since", "not-a-datetime"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Invalid since datetime", stderr.getvalue())

    def test_signals_list_invalid_limit_exits_nonzero(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "signals-list", "--limit", "0"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("limit must be greater than 0", stderr.getvalue())

    def test_planner_log_list_invalid_since_exits_nonzero(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "planner-log-list", "--since", "not-a-datetime"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Invalid since datetime", stderr.getvalue())

    def test_planner_log_list_invalid_limit_exits_nonzero(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as ctx:
                main(["--root", str(self.root), "planner-log-list", "--limit", "0"])

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("limit must be greater than 0", stderr.getvalue())

    def test_signals_show_elixir_dependency_break_end_to_end(self) -> None:
        receipts_path = self.root / ".aiwiki/state/execution-receipts.jsonl"
        receipts_path.parent.mkdir(parents=True, exist_ok=True)
        receipts_path.write_text(
            json.dumps(
                {
                    "kind": "execution-receipt",
                    "subject_kind": "elixir_demotion",
                    "subject_id": "elixir-a",
                    "protocol": "research",
                    "action_id": "elixir-demote-a-1714000000000",
                    "applied_at": "2026-04-24T11:23:00+00:00",
                    "bundle": {
                        "dependency_breaks": [
                            {
                                "dependent_elixir_id": "elixir-b",
                                "break_reason": "source_demoted",
                            }
                        ]
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        sig_code, sig_payload, sig_stderr = self._run_main(
            ["signals-replay", "--source", "archive", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"]
        )
        self.assertEqual(sig_code, 0)
        self.assertEqual(sig_stderr, "")
        self.assertEqual(sig_payload["new_count"], 1)

        planner_code, planner_payload, planner_stderr = self._run_main(["planner-log-replay"])
        self.assertEqual(planner_code, 0)
        self.assertEqual(planner_stderr, "")
        self.assertEqual(planner_payload["new_count"], 1)

        records = self._read_jsonl(".aiwiki/state/signals.jsonl")
        self.assertEqual(len(records), 1)
        signal_id = str(records[0]["signal_id"])

        show_code, show_stdout, show_stderr = self._run_main_raw(["signals-show", signal_id])
        self.assertEqual(show_code, 0)
        self.assertEqual(show_stderr, "")
        self.assertIn(signal_id, show_stdout)
        self.assertIn("elixir_dependency_break", show_stdout)
        self.assertIn("Related planner decisions:", show_stdout)
        self.assertIn("generate-proposal", show_stdout)


if __name__ == "__main__":
    unittest.main()
