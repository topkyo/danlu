from __future__ import annotations

import io
import json
import os
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
from aiwiki.today_feed import build_today_feed as real_build_today_feed

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

    def test_advanced_subcommand_exists(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")

        self.assertIn("advanced", action.choices)
        advanced_parser = action.choices["advanced"]
        advanced_action = next(item for item in advanced_parser._actions if getattr(item, "dest", "") == "advanced_command")
        self.assertIn("compile", advanced_action.choices)

    def test_drop_subcommand_exists(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")

        self.assertIn("drop", action.choices)
        drop_parser = action.choices["drop"]
        drop_action = next(item for item in drop_parser._actions if getattr(item, "dest", "") == "drop_command")
        self.assertEqual(
            {"url", "pdf", "image", "repo", "note", "question"},
            set(drop_action.choices),
        )

    def test_today_subcommand_exists(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")

        self.assertIn("today", action.choices)

    def test_trace_subcommand_exists_top_level_and_advanced(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        self.assertIn("trace", action.choices)
        # also under advanced
        advanced = action.choices["advanced"]
        adv_action = next(
            item for item in advanced._actions if getattr(item, "dest", "") == "advanced_command"
        )
        self.assertIn("trace", adv_action.choices)

    def test_trace_dispatches_with_unknown_asset(self) -> None:
        # Empty vault → unknown asset → still exit 0 (renders 'not found' marker)
        code, stdout, stderr = self._run_main_raw(["trace", "judgment-does-not-exist"])
        self.assertEqual(code, 0, msg=stderr)
        self.assertIn("(not found)", stdout)
        self.assertIn("[judgment]", stdout)

    def test_trace_json_output_is_valid(self) -> None:
        code, stdout, stderr = self._run_main_raw(
            ["trace", "judgment-does-not-exist", "--json"]
        )
        self.assertEqual(code, 0, msg=stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["kind"], "judgment")
        self.assertTrue(payload.get("not_found"))

    def test_today_dispatches_to_today_handler(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["today"])

        self.assertEqual(args.handler_command, "today")

    def test_today_prints_section_headings(self) -> None:
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Today's Reports", stdout)
        self.assertIn("Needs Review", stdout)
        self.assertIn("Completed Elixirs", stdout)
        self.assertIn("L3 Proposals", stdout)
        self.assertIn("Suggested Next Actions", stdout)
        self.assertIn("Advanced", stdout)

    def test_today_command_uses_feed_builder(self) -> None:
        """today_command 输出仍含 5 个 section heading 与 Advanced 提示。"""
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            with patch("aiwiki.cli.build_today_feed", wraps=real_build_today_feed) as feed_builder:
                code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        feed_builder.assert_called_once_with(summary)
        self.assertIn("Today's Reports", stdout)
        self.assertIn("Needs Review", stdout)
        self.assertIn("Completed Elixirs", stdout)
        self.assertIn("L3 Proposals", stdout)
        self.assertIn("Suggested Next Actions", stdout)
        self.assertIn("Advanced", stdout)

    def test_today_command_no_mechanism_words(self) -> None:
        """首屏不暴露具体技术 artifact 名。"""
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "review_backlog_counts": {"decision": 2},
            "suggested_next_actions": [{"title": "Review next page", "command": "aiwiki review-page --next"}],
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        for word in {"shell-summary", "review_backlog_counts", "planner-log", "audit.jsonl", "execution-receipts"}:
            self.assertNotIn(word, stdout)

    def test_today_command_advanced_hint_present(self) -> None:
        """Advanced 提示行保留。"""
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Run `aiwiki advanced ...`", stdout)
        self.assertIn("Run `aiwiki metrics`", stdout)

    def test_metrics_text_output_contains_all_metric_keys(self) -> None:
        code, stdout, stderr = self._run_main_raw(["metrics"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        for key in (
            "provenance_completeness",
            "stale_ratio",
            "review_closure_rate",
            "proposal_acceptance_rate",
            "judgment_revisit_rate",
            "output_file_back_rate",
            "elixir_reuse_count",
        ):
            self.assertIn(key, stdout)

    def test_metrics_json_output_is_valid_with_seven_entries(self) -> None:
        code, stdout, stderr = self._run_main_raw(["metrics", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(len(payload), 7)
        self.assertEqual(payload[0]["key"], "provenance_completeness")

    def test_metrics_empty_vault_does_not_raise(self) -> None:
        code, stdout, stderr = self._run_main_raw(["metrics"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("炼丹炉 Knowledge Compounding Metrics", stdout)

    def test_metrics_text_output_contains_chinese_label(self) -> None:
        code, stdout, stderr = self._run_main_raw(["metrics"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("知识溯源完整度", stdout)

    def test_metrics_appends_history_jsonl_each_invocation(self) -> None:
        # M7.3.1 Stage B: every metrics call appends one snapshot line.
        code1, _, _ = self._run_main_raw(["metrics"])
        self.assertEqual(code1, 0)
        history = Path(self.root) / ".aiwiki" / "state" / "metrics-history.jsonl"
        self.assertTrue(history.exists())
        first_lines = history.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(first_lines), 1)
        record = json.loads(first_lines[0])
        self.assertIn("ts", record)
        self.assertIn("metrics", record)
        self.assertIn("provenance_completeness", record["metrics"])

        code2, _, _ = self._run_main_raw(["metrics"])
        self.assertEqual(code2, 0)
        second_lines = history.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(second_lines), 2)

    def test_metrics_delta_window_without_baseline_reports_no_baseline(self) -> None:
        # M7.3.1 Stage B: --delta 7d with no historical sample older than
        # 7d emits a "no baseline within window" trailing block.
        code, stdout, stderr = self._run_main_raw(["metrics", "--delta", "7d"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("delta 7d: no baseline within window", stdout)

    def test_metrics_delta_30d_accepted(self) -> None:
        code, stdout, _ = self._run_main_raw(["metrics", "--delta", "30d"])
        self.assertEqual(code, 0)
        self.assertIn("delta 30d", stdout)

    def test_autonomy_status_text_default_state(self) -> None:
        # M7.4c: status command on empty vault prints all flags as enabled.
        code, stdout, stderr = self._run_main_raw(["autonomy-status"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("disable_lane_apply", stdout)
        self.assertIn("disable_external_llm", stdout)
        self.assertIn("file exists : False", stdout)

    def test_autonomy_disable_persists_and_status_reflects(self) -> None:
        # M7.4c: disable + status round-trip.
        code, _, _ = self._run_main_raw(["autonomy-disable", "disable_lane_apply"])
        self.assertEqual(code, 0)
        code, stdout, _ = self._run_main_raw(["autonomy-status", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["policy_file_exists"])
        self.assertTrue(payload["flags"]["disable_lane_apply"]["effective"])
        self.assertFalse(payload["flags"]["disable_alchemy_auto"]["effective"])

    def test_autonomy_unknown_flag_exits_nonzero(self) -> None:
        # M7.4c: unknown flag → exit 2 + stderr listing valid flags.
        code, stdout, stderr = self._run_main_raw(["autonomy-disable", "disable_made_up"])
        self.assertEqual(code, 2)
        self.assertIn("Unknown autonomy flag", stderr)
        self.assertIn("disable_lane_apply", stderr)

    def test_today_does_not_mutate_shell_summary(self) -> None:
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "recent_outputs": [{"generated_at": "2026-04-27T09:00:00+00:00", "path": "output/reports/a.md"}],
            "suggested_next_actions": [{"title": "Review", "command": "aiwiki review-page --next --status approved"}],
        }
        before = json.loads(json.dumps(summary, sort_keys=True))

        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, _stdout, _stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(summary, before)

    def test_today_renders_empty_placeholders(self) -> None:
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("(no reports today)", stdout)
        self.assertIn("(no pending review)", stdout)
        self.assertIn("(no completed elixirs today)", stdout)
        self.assertIn("(no L3 proposals need attention)", stdout)
        self.assertIn("(no suggested next actions)", stdout)

    def test_today_json_outputs_structured_buckets(self) -> None:
        """P4-22: today --json 按 5 个 section 桶化输出，human 路径不变。"""
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "review_backlog_counts": {"decision": 2, "concept_backlog": 5},
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        # 顶层 keys
        self.assertEqual(
            set(payload.keys()),
            {
                "generated_at",
                "active_protocol",
                "todays_reports",
                "needs_review",
                "completed_elixirs",
                "l3_proposals",
                "suggested_next_actions",
            },
        )
        self.assertEqual(payload["active_protocol"], "research")
        # needs_review 桶应有 2 项（decision + concept_backlog）
        self.assertEqual(len(payload["needs_review"]), 2)
        # entry 字段对齐 FeedEntry
        sample = payload["needs_review"][0]
        self.assertEqual(
            set(sample.keys()),
            {"kind", "title", "summary", "target", "timestamp", "protocol"},
        )

    def test_retire_concept_batch_multiple_slugs_calls_each(self) -> None:
        """P4-19a: retire-concept 接受多 slug，按顺序循环调；receipt 桶化 count/slugs/receipts。"""
        with patch("aiwiki.cli.retire_concept") as mocked:
            mocked.side_effect = lambda root, slug, note=None: {"slug": slug, "status": "retired"}
            code, payload, stderr = self._run_main(
                ["retire-concept", "alpha", "beta", "gamma", "--note", "noise"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["slugs"], ["alpha", "beta", "gamma"])
        self.assertEqual([r["slug"] for r in payload["receipts"]], ["alpha", "beta", "gamma"])
        self.assertEqual(mocked.call_count, 3)
        for call, slug in zip(mocked.call_args_list, ["alpha", "beta", "gamma"], strict=True):
            self.assertEqual(call.args[1], slug)
            self.assertEqual(call.kwargs.get("note"), "noise")

    def test_retire_concept_single_slug_backwards_compatible(self) -> None:
        """单 slug 仍直接返回原 receipt（不包到 batch wrapper）。"""
        with patch("aiwiki.cli.retire_concept", return_value={"slug": "solo", "status": "retired"}) as mocked:
            code, payload, stderr = self._run_main(["retire-concept", "solo"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload, {"slug": "solo", "status": "retired"})
        mocked.assert_called_once()

    def test_retire_concept_batch_fail_fast_on_first_error(self) -> None:
        """fail-fast：第一个失败立即停止，不调后续 slug。"""
        calls: list[str] = []

        def fake_retire(root: Path, slug: str, note: str | None = None) -> dict[str, str]:
            calls.append(slug)
            if slug == "bad":
                raise ValueError(f"cannot retire {slug}")
            return {"slug": slug, "status": "retired"}

        with patch("aiwiki.cli.retire_concept", side_effect=fake_retire):
            with self.assertRaises(SystemExit) as ctx:
                self._run_main(["retire-concept", "ok1", "bad", "ok2"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(calls, ["ok1", "bad"])

    def test_reactivate_concept_batch_multiple_slugs(self) -> None:
        """reactivate-concept 同样支持批量。"""
        with patch("aiwiki.cli.reactivate_concept") as mocked:
            mocked.side_effect = lambda root, slug, note=None: {"slug": slug, "status": "active"}
            code, payload, stderr = self._run_main(
                ["reactivate-concept", "alpha", "beta", "--note", "wake"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(mocked.call_count, 2)

    def test_review_concept_single_slug_calls_review_concept(self) -> None:
        """P4-19b: 单 slug 直接调 review_concept，不走 batch wrapper。"""
        with patch(
            "aiwiki.cli.review_concept",
            return_value={"slug": "alpha", "status": "deferred"},
        ) as mocked:
            code, payload, stderr = self._run_main(
                ["review-concept", "alpha", "--status", "deferred", "--note", "ack"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload, {"slug": "alpha", "status": "deferred"})
        mocked.assert_called_once()
        call = mocked.call_args
        self.assertEqual(call.args[1], "alpha")
        self.assertEqual(call.kwargs.get("status"), "deferred")
        self.assertEqual(call.kwargs.get("note"), "ack")

    def test_review_concept_batch_multiple_slugs_uses_batch_helper(self) -> None:
        """P4-19b: 多 slug 走 review_concepts_batch，receipt 桶化。"""
        with patch(
            "aiwiki.cli.review_concepts_batch",
            return_value={
                "slugs": ["alpha", "beta"],
                "receipts": [
                    {"slug": "alpha", "status": "deferred"},
                    {"slug": "beta", "status": "deferred"},
                ],
                "count": 2,
                "status": "deferred",
            },
        ) as mocked:
            code, payload, stderr = self._run_main(
                ["review-concept", "alpha", "beta", "--status", "deferred"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["count"], 2)
        mocked.assert_called_once()
        call = mocked.call_args
        self.assertEqual(call.args[1], ["alpha", "beta"])
        self.assertEqual(call.kwargs.get("status"), "deferred")

    def test_review_concept_rejects_status_not_in_choices(self) -> None:
        """argparse 拒绝非法 --status (e.g. retired 走 retire-concept；revisit 是启发式状态)."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main(["review-concept", "alpha", "--status", "retired"])
        self.assertEqual(ctx.exception.code, 2)

    def test_review_concept_requires_slug_or_all_pending(self) -> None:
        """无 slug 且无 --all-pending → ValueError → exit 1."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main(["review-concept", "--status", "deferred"])
        self.assertEqual(ctx.exception.code, 1)

    def test_review_concept_all_pending_drains_revisit_and_review_buckets(self) -> None:
        """--all-pending 从 lifecycle entries 抽取 revisit/review 概念，去重 override_active。"""
        lifecycle = {
            "entries": [
                {"kind": "concept", "path": "wiki/concepts/alpha.md", "lifecycle_state": "revisit", "override_active": False},
                {"kind": "concept", "path": "wiki/concepts/beta.md", "lifecycle_state": "review", "override_active": False},
                {"kind": "concept", "path": "wiki/concepts/gamma.md", "lifecycle_state": "active", "override_active": False},
                {"kind": "concept", "path": "wiki/concepts/already-acked.md", "lifecycle_state": "deferred", "override_active": True},
                {"kind": "decision", "path": "wiki/decisions/d1.md", "lifecycle_state": "revisit", "override_active": False},
            ]
        }
        with patch(
            "aiwiki.app_compile.refresh_knowledge_lifecycle_runtime",
            return_value=lifecycle,
        ), patch(
            "aiwiki.cli.review_concepts_batch",
            return_value={"slugs": [], "receipts": [], "count": 0, "status": "deferred"},
        ) as batch_mock:
            code, _payload, stderr = self._run_main(
                ["review-concept", "--status", "deferred", "--all-pending"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        batch_mock.assert_called_once()
        slugs_arg = batch_mock.call_args.args[1]
        self.assertEqual(sorted(slugs_arg), ["alpha", "beta"])

    def test_review_concept_all_pending_errors_when_empty(self) -> None:
        """--all-pending 且 lifecycle 中无 revisit/review 概念 → exit 1。"""
        lifecycle = {"entries": []}
        with patch(
            "aiwiki.app_compile.refresh_knowledge_lifecycle_runtime",
            return_value=lifecycle,
        ):
            with self.assertRaises(SystemExit) as ctx:
                self._run_main(
                    ["review-concept", "--status", "deferred", "--all-pending"]
                )
        self.assertEqual(ctx.exception.code, 1)

    def test_review_concept_rejects_slugs_with_all_pending(self) -> None:
        """互斥：传 slug 又传 --all-pending → exit 1."""
        with self.assertRaises(SystemExit) as ctx:
            self._run_main(
                ["review-concept", "alpha", "--status", "deferred", "--all-pending"]
            )
        self.assertEqual(ctx.exception.code, 1)

    def test_review_queue_json_buckets_decision_entries(self) -> None:
        """P4-16a: review-queue --json 桶化 needs_review entries。"""
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "review_backlog_counts": {"concept_backlog": 30, "revisit": 5, "mm_actions": 2},
            "counter_evidence_pages": [
                {"path": "wiki/judgments/j1.md", "subject": "j1", "summary": "反证", "detected_at": "2026-04-27T10:00:00+00:00"},
            ],
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, payload, stderr = self._run_main(["review-queue", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["active_protocol"], "research")
        # 有 3 个 review_backlog_counts buckets + counter_evidence
        self.assertIn("concept_backlog", payload["buckets"])
        self.assertIn("revisit", payload["buckets"])
        self.assertIn("mm_actions", payload["buckets"])
        self.assertIn("counter_evidence", payload["buckets"])
        self.assertEqual(payload["total"], 4)
        # entry schema
        sample = payload["buckets"]["concept_backlog"][0]
        self.assertEqual(set(sample.keys()), {"title", "summary", "target", "timestamp", "protocol"})

    def test_review_queue_filter_by_bucket(self) -> None:
        """--bucket 过滤到单 bucket。"""
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "review_backlog_counts": {"concept_backlog": 30, "revisit": 5},
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, payload, stderr = self._run_main(["review-queue", "--bucket", "concept_backlog", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(set(payload["buckets"].keys()), {"concept_backlog"})
        self.assertEqual(payload["total"], 1)

    def test_review_queue_text_renders_headings(self) -> None:
        """text 模式输出 # Review Queue + 每 bucket heading。"""
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "review_backlog_counts": {"concept_backlog": 30},
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["review-queue"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("# Review Queue", stdout)
        self.assertIn("## concept_backlog", stdout)
        self.assertIn("total        : 1", stdout)

    def test_review_queue_empty_renders_placeholder(self) -> None:
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["review-queue"])
        self.assertEqual(code, 0)
        self.assertIn("(no pending review)", stdout)

    def test_today_text_unchanged_when_no_json(self) -> None:
        """P4-22 fail-gate: 默认（无 --json）输出 byte-for-byte 仍含原 5 个 heading + Advanced。"""
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        for heading in [
            "Today's Reports",
            "Needs Review",
            "Completed Elixirs",
            "L3 Proposals",
            "Suggested Next Actions",
            "Advanced",
        ]:
            self.assertIn(heading, stdout)

    def test_cli_model_fallback_single(self) -> None:
        captured: dict[str, object] = {}

        def fake_status() -> dict[str, object]:
            captured["fallback"] = os.environ.get("AIWIKI_MODEL_FALLBACK")
            return {"status": "ok"}

        with patch.dict(os.environ, {"AIWIKI_MODEL_FALLBACK": "env-fallback"}, clear=False):
            with patch("aiwiki.cli.llm_status", side_effect=fake_status) as mocked_status:
                code, payload, stderr = self._run_main(["--model-fallback", "foo", "llm-check"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload, {"status": "ok"})
        mocked_status.assert_called_once()
        self.assertEqual(captured["fallback"], "foo")

    def test_cli_model_fallback_repeated(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--model-fallback", "a", "--model-fallback", "b", "llm-check"])

        self.assertEqual(args.model_fallback, ["a", "b"])

    def test_cli_model_fallback_comma(self) -> None:
        from aiwiki.cli import _flatten_model_fallback_args

        self.assertEqual(_flatten_model_fallback_args(["a,b,c"]), ["a", "b", "c"])

    def test_cli_overrides_env(self) -> None:
        captured: dict[str, object] = {}

        def fake_status() -> dict[str, object]:
            captured["fallback"] = os.environ.get("AIWIKI_MODEL_FALLBACK")
            return {"status": "ok"}

        with patch.dict(os.environ, {"AIWIKI_MODEL_FALLBACK": "env-a,env-b"}, clear=False):
            with patch("aiwiki.cli.llm_status", side_effect=fake_status):
                code, payload, stderr = self._run_main(["--model-fallback", "cli-a,cli-b", "llm-check"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload, {"status": "ok"})
        self.assertEqual(captured["fallback"], "cli-a,cli-b")

    def test_today_renders_today_reports(self) -> None:
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "recent_outputs": [
                {
                    "generated_at": "2026-04-27T09:00:00+00:00",
                    "protocol": "research",
                    "title": "Daily Report",
                    "format": "report",
                    "path": "output/reports/daily.md",
                }
            ],
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("- [research] Daily Report — report 输出 — output/reports/daily.md", stdout)

    def test_today_filters_non_today_reports(self) -> None:
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "recent_outputs": [
                {
                    "generated_at": "2026-04-26T23:59:59+00:00",
                    "protocol": "research",
                    "title": "Yesterday",
                    "format": "report",
                    "path": "output/reports/yesterday.md",
                }
            ],
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn("output/reports/yesterday.md", stdout)
        self.assertIn("(no reports today)", stdout)

    def test_today_renders_suggested_next_actions(self) -> None:
        summary = {
            "generated_at": "2026-04-27T10:00:00+00:00",
            "active_protocol": "research",
            "suggested_next_actions": [
                {"title": "Review next page", "command": "aiwiki review-page --next --status approved"}
            ],
        }
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            code, stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Review next page", stdout)
        self.assertIn("aiwiki review-page --next --status approved", stdout)

    def test_today_no_llm_call(self) -> None:
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            with patch("aiwiki.llm.create_backend_client") as llm_mock:
                code, _stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        llm_mock.assert_not_called()

    def test_today_does_not_mutate_shell_status_json(self) -> None:
        summary = {"generated_at": "2026-04-27T10:00:00+00:00", "active_protocol": "research"}
        with patch("aiwiki.cli.build_shell_summary", return_value=summary):
            with patch("aiwiki.cli.shell_status") as shell_status_mock:
                code, _stdout, stderr = self._run_main_raw(["today"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        shell_status_mock.assert_not_called()

    def test_drop_url_dispatches_to_drop_url_handler(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-url", "https://example.com", "--title", "Example"])
        drop_args = parser.parse_args(["drop", "url", "https://example.com", "--title", "Example"])

        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.url, legacy_args.url)
        self.assertEqual(drop_args.title, legacy_args.title)

    def test_drop_pdf_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-pdf", "paper.pdf", "--title", "Paper"])
        drop_args = parser.parse_args(["drop", "pdf", "paper.pdf", "--title", "Paper"])

        self.assertEqual(drop_args.handler_command, "drop-pdf")
        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.source, legacy_args.source)
        self.assertEqual(drop_args.title, legacy_args.title)

    def test_drop_image_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-image", "chart.png", "--title", "Chart", "--no-vision"])
        drop_args = parser.parse_args(["drop", "image", "chart.png", "--title", "Chart", "--no-vision"])

        self.assertEqual(drop_args.handler_command, "drop-image")
        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.source, legacy_args.source)
        self.assertEqual(drop_args.title, legacy_args.title)
        self.assertEqual(drop_args.no_vision, legacy_args.no_vision)

    def test_drop_repo_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-repo", "repo", "--title", "Repo", "--max-files", "10"])
        drop_args = parser.parse_args(["drop", "repo", "repo", "--title", "Repo", "--max-files", "10"])

        self.assertEqual(drop_args.handler_command, "drop-repo")
        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.source, legacy_args.source)
        self.assertEqual(drop_args.title, legacy_args.title)
        self.assertEqual(drop_args.max_files, legacy_args.max_files)

    def test_drop_note_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-note", "notes.md", "--text", "hello", "--kind", "transcript"])
        drop_args = parser.parse_args(["drop", "note", "notes.md", "--text", "hello", "--kind", "transcript"])

        self.assertEqual(drop_args.handler_command, "drop-note")
        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.source, legacy_args.source)
        self.assertEqual(drop_args.text, legacy_args.text)
        self.assertEqual(drop_args.kind, legacy_args.kind)

    def test_drop_question_dispatches_to_ask_handler(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["ask", "What changed?", "--format", "slides", "--protocol", "research"])
        drop_args = parser.parse_args(
            ["drop", "question", "What changed?", "--format", "slides", "--protocol", "research"]
        )

        self.assertEqual(drop_args.handler_command, "ask")
        self.assertEqual(drop_args.handler_command, legacy_args.handler_command)
        self.assertEqual(drop_args.question, legacy_args.question)
        self.assertEqual(drop_args.format, legacy_args.format)
        self.assertEqual(drop_args.protocol, legacy_args.protocol)

    def test_legacy_drop_url_emits_deprecation_warning(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url"}):
            code, stdout, stderr = self._run_main_raw(["drop-url", "https://example.com"])

        self.assertEqual(code, 0)
        self.assertIn("deprecated", stderr.lower())
        self.assertNotIn("deprecated", stdout.lower())

    def test_advanced_drop_url_no_warning(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url"}):
            code, payload, stderr = self._run_main(["advanced", "drop-url", "https://example.com"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["material"], "url")
        self.assertNotIn("deprecated", stderr.lower())

    def test_drop_url_no_warning(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url"}):
            code, payload, stderr = self._run_main(["drop", "url", "https://example.com"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["material"], "url")
        self.assertNotIn("deprecated", stderr.lower())

    def test_bare_drop_routes_to_typed_handlers(self) -> None:
        cases = [
            (
                "url",
                ["drop", "https://example.com"],
                "drop_url",
                (self.root, "https://example.com"),
                {"title": None},
            ),
            (
                "pdf",
                ["drop", "paper.pdf"],
                "drop_pdf",
                (self.root, "paper.pdf"),
                {"title": None},
            ),
            (
                "image",
                ["drop", "chart.png"],
                "drop_image",
                (self.root, "chart.png"),
                {"title": None, "enable_vision": True},
            ),
            (
                "repo",
                ["drop", "git@example.com:org/repo.git"],
                "drop_repo",
                (self.root, "git@example.com:org/repo.git"),
                {"title": None, "max_files": 200},
            ),
            (
                "note-prefix",
                ["drop", "note: my note"],
                "drop_note",
                (self.root, "my note"),
                {"title": None, "text": None, "kind": "note"},
            ),
            (
                "note-multiline",
                ["drop", "line1\nline2"],
                "drop_note",
                (self.root, "line1\nline2"),
                {"title": None, "text": None, "kind": "note"},
            ),
        ]
        for name, argv, target, expected_args, expected_kwargs in cases:
            with self.subTest(route=name):
                with patch(f"aiwiki.cli.{target}", return_value={"route": name}) as mocked:
                    code, payload, stderr = self._run_main(argv)

                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertEqual(payload["route"], name)
                mocked.assert_called_once_with(*expected_args, **expected_kwargs)

    def test_bare_drop_url_equivalent_to_typed_drop_url(self) -> None:
        calls: list[tuple[Path, str, str | None]] = []

        def fake_drop_url(root: Path, url: str, *, title: str | None = None) -> dict[str, object]:
            calls.append((root, url, title))
            return {"url": url, "title": title}

        with patch("aiwiki.cli.drop_url", side_effect=fake_drop_url):
            bare_code, bare_payload, bare_stderr = self._run_main(["drop", "https://example.com"])
            typed_code, typed_payload, typed_stderr = self._run_main(["drop", "url", "https://example.com"])

        self.assertEqual(bare_code, typed_code)
        self.assertEqual(bare_stderr, typed_stderr)
        self.assertEqual(bare_payload, typed_payload)
        self.assertEqual(calls, [(self.root, "https://example.com", None), (self.root, "https://example.com", None)])

    def test_bare_drop_stdin_routes_to_url(self) -> None:
        with patch("sys.stdin", new=io.StringIO("https://example.com\n")):
            with patch("aiwiki.cli.drop_url", return_value={"material": "url"}) as mocked:
                code, payload, stderr = self._run_main(["drop", "-"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["material"], "url")
        mocked.assert_called_once_with(self.root, "https://example.com", title=None)

    def test_bare_drop_empty_stdin_exits_argparse_style(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdin", new=io.StringIO("\n")):
            with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
                with self.assertRaises(SystemExit) as raised:
                    main(["--root", str(self.root), "drop", "-"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("empty stdin payload", stderr.getvalue())

    def test_typed_drop_url_is_not_rewritten_by_universal_router(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url"}) as mocked:
            code, payload, stderr = self._run_main(["drop", "url", "https://example.com"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["material"], "url")
        self.assertNotIn("deprecated", stderr.lower())
        mocked.assert_called_once_with(self.root, "https://example.com", title=None)

    def test_bare_drop_question_routes_to_ask(self) -> None:
        with patch("aiwiki.cli.ask_question", return_value={"question": "what is x?"}) as mocked:
            code, payload, stderr = self._run_main(["drop", "what is x?"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["question"], "what is x?")
        mocked.assert_called_once_with(
            self.root,
            "what is x?",
            "report",
            protocol=None,
            no_cache=False,
            load_protocol_learnings=False,
        )

    def test_bare_drop_ask_prefix_strips_prefix(self) -> None:
        with patch("aiwiki.cli.ask_question", return_value={"question": "hello"}) as mocked:
            code, payload, stderr = self._run_main(["drop", "ask: hello"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["question"], "hello")
        mocked.assert_called_once_with(
            self.root,
            "hello",
            "report",
            protocol=None,
            no_cache=False,
            load_protocol_learnings=False,
        )

    def test_drop_without_payload_keeps_required_subparser_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--root", str(self.root), "drop"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("required", stderr.getvalue())

    def test_universal_drop_rewrite_preserves_help_requests(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["--root", str(self.root), "drop", "https://example.com", "--help"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("invalid choice", stderr.getvalue())

    def test_universal_drop_rewrite_handles_sys_argv_and_global_option_forms(self) -> None:
        with patch("sys.argv", ["aiwiki", "--root=/tmp/root", "--verbose", "drop", "paper.pdf"]):
            with patch("sys.stdin", new=io.StringIO("https://example.com\n")):
                from aiwiki.cli import _rewrite_universal_drop_argv

                self.assertEqual(_rewrite_universal_drop_argv(None), ["--root=/tmp/root", "--verbose", "drop", "pdf", "paper.pdf"])

        from aiwiki.cli import _rewrite_universal_drop_argv

        self.assertEqual(_rewrite_universal_drop_argv(["--root", str(self.root)]), ["--root", str(self.root)])
        self.assertEqual(_rewrite_universal_drop_argv(["today"]), ["today"])

    def test_advanced_compile_dispatches_to_compile_handler(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["compile"])
        advanced_args = parser.parse_args(["advanced", "compile"])

        self.assertEqual(legacy_args.handler_command, "compile")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)

    def test_advanced_drop_url_dispatches_to_drop_url_handler(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["drop-url", "https://example.com", "--title", "Example"])
        advanced_args = parser.parse_args(["advanced", "drop-url", "https://example.com", "--title", "Example"])

        self.assertEqual(legacy_args.handler_command, "drop-url")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)
        self.assertEqual(advanced_args.url, legacy_args.url)
        self.assertEqual(advanced_args.title, legacy_args.title)

    def test_advanced_alchemy_nested_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["alchemy", "heavy", "all", "--dry-run", "--max-signals", "3"])
        advanced_args = parser.parse_args(["advanced", "alchemy", "heavy", "all", "--dry-run", "--max-signals", "3"])

        self.assertEqual(legacy_args.handler_command, "alchemy")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)
        self.assertEqual(advanced_args.alchemy_lane, legacy_args.alchemy_lane)
        self.assertEqual(advanced_args.scope, legacy_args.scope)
        self.assertEqual(advanced_args.max_signals, legacy_args.max_signals)

    def test_advanced_review_nested_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["review", "proposals", "--kind", "prompt_proposal", "--state", "candidate", "--json"])
        advanced_args = parser.parse_args(
            ["advanced", "review", "proposals", "--kind", "prompt_proposal", "--state", "candidate", "--json"]
        )

        self.assertEqual(legacy_args.handler_command, "review")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)
        self.assertEqual(advanced_args.review_command, legacy_args.review_command)
        self.assertEqual(advanced_args.kind, legacy_args.kind)
        self.assertEqual(advanced_args.state, legacy_args.state)
        self.assertEqual(advanced_args.json, legacy_args.json)

    def test_advanced_no_deprecation_warning(self) -> None:
        with patch("aiwiki.cli.drop_url", return_value={"material": "url"}):
            code, payload, stderr = self._run_main(["advanced", "drop-url", "https://example.com"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["material"], "url")
        self.assertNotIn("deprecated", stderr.lower())

    def test_advanced_audit_backfill_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["audit-backfill", "--dry-run", "--limit", "6"])
        advanced_args = parser.parse_args(["advanced", "audit-backfill", "--dry-run", "--limit", "6"])

        self.assertEqual(legacy_args.handler_command, "audit-backfill")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)
        self.assertEqual(advanced_args.dry_run, legacy_args.dry_run)
        self.assertEqual(advanced_args.limit, legacy_args.limit)

    def test_advanced_alchemy_revert_dispatch(self) -> None:
        parser = build_parser()

        legacy_args = parser.parse_args(["alchemy-revert", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "undo"])
        advanced_args = parser.parse_args(
            ["advanced", "alchemy-revert", "--elixir-id", "elixir-vla-robotics-deadbeef", "--note", "undo"]
        )

        self.assertEqual(legacy_args.handler_command, "alchemy-revert")
        self.assertEqual(advanced_args.handler_command, legacy_args.handler_command)
        self.assertEqual(advanced_args.elixir_id, legacy_args.elixir_id)
        self.assertEqual(advanced_args.note, legacy_args.note)

    def test_main_dispatches_command_handlers(self) -> None:
        parser = build_parser()
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
                "alchemy-judge-preview",
                ["alchemy", "judge", "all", "--dry-run", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11"],
                "run_alchemy_judge_preview",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
                },
            ),
            (
                "alchemy-judge-propose",
                ["alchemy", "judge", "all", "--propose", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11", "--note", "proposal"],
                "run_alchemy_judge_propose",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
                    "note": "proposal",
                },
            ),
            (
                "alchemy-judge-proposal-apply",
                ["alchemy", "judge-proposal", "output/_proposals/judge/proposal.md", "--apply", "--note", "accepted"],
                "run_alchemy_judge_proposal_apply",
                (self.root, "output/_proposals/judge/proposal.md"),
                {"note": "accepted"},
            ),
            (
                "alchemy-distill-preview",
                ["alchemy", "distill", "all", "--dry-run", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11"],
                "run_alchemy_distill_preview",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
                },
            ),
            (
                "alchemy-review-preview",
                ["alchemy", "review", "all", "--dry-run", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11"],
                "run_alchemy_review_preview",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
                },
            ),
            (
                "alchemy-review-apply",
                ["alchemy", "review", "all", "--apply", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11", "--note", "queue"],
                "run_alchemy_review_apply",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
                    "note": "queue",
                },
            ),
            (
                "alchemy-propose-preview",
                ["alchemy", "propose", "all", "--dry-run", "--max-signals", "3", "--max-pages", "5", "--max-tokens", "7", "--limit", "11"],
                "run_alchemy_propose_preview",
                (self.root,),
                {
                    "scope": "all",
                    "planner_log_path": None,
                    "signals_path": None,
                    "max_signals": 3,
                    "max_pages": 5,
                    "max_tokens": 7,
                    "limit": 11,
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
                    "--primitive",
                    "review",
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
                    "primitives": ["compile", "review"],
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
                parsed_args = parser.parse_args(argv)
                self.assertEqual(parsed_args.handler_command, parsed_args.command)
                stdout = io.StringIO()
                stderr = io.StringIO()
                with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
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
        self.assertIn("deprecated", stderr.lower())
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


class VaultRootResolutionTests(unittest.TestCase):
    """P4-11: CLI vault root resolution precedence + stderr breadcrumb."""

    def setUp(self) -> None:
        from aiwiki.cli import _resolve_vault_root, build_parser  # noqa: F401

        self._resolve = _resolve_vault_root
        self._build_parser = build_parser
        self._prev_env = os.environ.get("AIWIKI_VAULT")
        os.environ.pop("AIWIKI_VAULT", None)

    def tearDown(self) -> None:
        if self._prev_env is None:
            os.environ.pop("AIWIKI_VAULT", None)
        else:
            os.environ["AIWIKI_VAULT"] = self._prev_env

    def _parse(self, argv: list[str]):
        return self._build_parser().parse_args(argv)

    def test_explicit_root_wins_over_env(self) -> None:
        with tempfile.TemporaryDirectory() as explicit_dir, tempfile.TemporaryDirectory() as env_dir:
            os.environ["AIWIKI_VAULT"] = env_dir
            args = self._parse(["--root", explicit_dir, "today"])
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                resolved = self._resolve(args)
            self.assertEqual(resolved, Path(explicit_dir).resolve())
            self.assertEqual(stderr.getvalue(), "")

    def test_env_used_when_no_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as env_dir:
            os.environ["AIWIKI_VAULT"] = env_dir
            args = self._parse(["today"])
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                resolved = self._resolve(args)
            self.assertEqual(resolved, Path(env_dir).resolve())
            self.assertIn("AIWIKI_VAULT env", stderr.getvalue())
            self.assertIn(str(Path(env_dir).resolve()), stderr.getvalue())

    def test_default_cwd_when_neither_set(self) -> None:
        args = self._parse(["today"])
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            resolved = self._resolve(args)
        self.assertEqual(resolved, Path(".").resolve())
        self.assertEqual(stderr.getvalue(), "")

    def test_empty_env_treated_as_unset(self) -> None:
        os.environ["AIWIKI_VAULT"] = "   "
        args = self._parse(["today"])
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            resolved = self._resolve(args)
        self.assertEqual(resolved, Path(".").resolve())
        self.assertEqual(stderr.getvalue(), "")

    def test_explicit_dot_is_explicit_not_default(self) -> None:
        # User typing `--root .` should NOT trigger env fallback.
        with tempfile.TemporaryDirectory() as env_dir:
            os.environ["AIWIKI_VAULT"] = env_dir
            args = self._parse(["--root", ".", "today"])
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                resolved = self._resolve(args)
            self.assertEqual(resolved, Path(".").resolve())
            self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
