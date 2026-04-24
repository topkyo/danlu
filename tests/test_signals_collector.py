from __future__ import annotations

import ast
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiwiki.signals.adapters as adapters
import aiwiki.signals.collector as collector
from aiwiki.cli import build_parser, main
from aiwiki.signals import collect_signals
from aiwiki.signals.schema import parse_trace_id, validate

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "signals_collector"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
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


def _normalized_signal_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for record in records:
        copy = dict(record)
        copy.pop("signal_id", None)
        normalized.append(copy)
    return normalized


def _snapshot_files(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel == ".aiwiki/state/runtime.lock":
                continue
            snapshot[rel] = path.read_bytes()
    return snapshot


class _FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.temp_root = Path(self._tmpdir.name).resolve()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _copy_case_root(self, case_name: str) -> Path:
        dst = self.temp_root / case_name
        shutil.copytree(FIXTURE_DIR / case_name / "root", dst)
        return dst


class TestIdempotency(_FixtureCase):
    def test_full_replay_then_idempotent_then_append_new_event(self) -> None:
        root = self._copy_case_root("case_basic")
        trace_id = "550e8400-e29b-41d4-a716-446655440000"

        first = collect_signals(root, trace_id=trace_id)
        self.assertEqual(first["new_count"], 3)
        self.assertEqual(first["duplicate_count"], 0)

        signals_path = root / ".aiwiki/state/signals.jsonl"
        first_bytes = signals_path.read_bytes()
        self.assertEqual(len(_read_jsonl(signals_path)), 3)

        actual_records = _normalized_signal_records(_read_jsonl(signals_path))
        expected_records = _normalized_signal_records(_read_jsonl(FIXTURE_DIR / "case_basic" / "expected" / "signals.jsonl"))
        self.assertEqual(actual_records, expected_records)

        second = collect_signals(root, trace_id=trace_id)
        self.assertEqual(second["new_count"], 0)
        self.assertEqual(second["duplicate_count"], 3)
        self.assertEqual(signals_path.read_bytes(), first_bytes)

        with (root / ".aiwiki/state/runtime-history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "event_type": "nightly",
                        "occurred_at": "2026-04-24T00:40:00Z",
                        "protocol": "ops",
                        "overdue_pages": ["wiki/decisions/new.md"],
                        "escalated_pages": [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

        third = collect_signals(root, trace_id=trace_id)
        self.assertEqual(third["new_count"], 1)
        self.assertEqual(third["duplicate_count"], 3)
        self.assertEqual(len(_read_jsonl(signals_path)), 4)

    def test_default_trace_id_replay_is_idempotent(self) -> None:
        root = self._copy_case_root("case_basic")
        signals_path = root / ".aiwiki/state/signals.jsonl"

        first = collect_signals(root)
        self.assertGreater(first["new_count"], 0)
        first_lines = len(_read_jsonl(signals_path))
        first_bytes = signals_path.read_bytes()

        second = collect_signals(root)
        self.assertEqual(second["new_count"], 0)
        self.assertEqual(second["duplicate_count"], first["new_count"])
        self.assertEqual(len(_read_jsonl(signals_path)), first_lines)
        self.assertEqual(signals_path.read_bytes(), first_bytes)

    def test_fixture_idempotent_summary_matches(self) -> None:
        root = self._copy_case_root("case_idempotent")
        expected = json.loads((FIXTURE_DIR / "case_idempotent" / "expected" / "summary.json").read_text(encoding="utf-8"))
        signals_path = root / ".aiwiki/state/signals.jsonl"
        before = signals_path.read_bytes()

        result = collect_signals(root, trace_id=expected["trace_id"])

        for key, value in expected.items():
            self.assertEqual(result[key], value)
        self.assertEqual(signals_path.read_bytes(), before)

    def test_collect_without_trace_id_bootstraps_uuidv4(self) -> None:
        root = self._copy_case_root("case_basic")
        result = collect_signals(root)
        self.assertIsInstance(result["trace_id"], str)
        self.assertEqual(parse_trace_id(result["trace_id"]), result["trace_id"])

    def test_replay_existing_dedupe_with_different_trace_is_duplicate(self) -> None:
        root = self._copy_case_root("case_idempotent")
        result = collect_signals(root, trace_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["duplicate_count"], 3)

    def test_collect_empty_root_noop(self) -> None:
        root = self.temp_root / "empty"
        root.mkdir(parents=True)
        result = collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(result["scanned_count"], 0)
        self.assertEqual(result["new_count"], 0)
        self.assertFalse((root / ".aiwiki/state/signals.jsonl").exists())

    def test_batch_duplicate_in_same_replay_counts_duplicate(self) -> None:
        root = self.temp_root / "batch-dup"
        runtime_path = root / ".aiwiki/state/runtime-history.jsonl"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "event_type": "review",
                "occurred_at": "2026-04-24T01:00:00Z",
                "protocol": "research",
                "page_path": "wiki/decisions/dup.md",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        runtime_path.write_text(line + "\n" + line + "\n", encoding="utf-8")

        result = collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)

    def test_source_filter_runtime_history_only(self) -> None:
        root = self._copy_case_root("case_basic")
        result = collect_signals(
            root,
            sources=["runtime_history"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["sources"], ["runtime_history"])
        self.assertEqual(result["new_count"], 2)
        self.assertEqual(result["scanned_count"], 6)
        self.assertEqual(result["emitted_by_kind"]["runtime_failure"], 0)

    def test_source_filter_llm_only(self) -> None:
        root = self._copy_case_root("case_basic")
        result = collect_signals(
            root,
            sources=["llm_receipt"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["sources"], ["llm_receipt"])
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["scanned_count"], 2)
        self.assertEqual(result["unmapped_count"], 1)

    def test_archive_source_is_wired_but_noop(self) -> None:
        root = self.temp_root / "archive-only"
        path = root / ".aiwiki/state/execution-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"kind": "execution-receipt"}, sort_keys=True) + "\n", encoding="utf-8")

        result = collect_signals(
            root,
            sources=["archive"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["unmapped_count"], 1)
        self.assertEqual(result["scanned_count"], 1)

    def test_skip_examples_are_capped_at_five(self) -> None:
        root = self.temp_root / "skip-cap"
        path = root / ".aiwiki/state/runtime-history.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(["{bad"] * 7) + "\n", encoding="utf-8")

        result = collect_signals(
            root,
            sources=["runtime_history"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["invalid_count"], 7)
        self.assertEqual(len(result["skip_examples"]), 5)


class TestTraceConflictFailFast(_FixtureCase):
    def test_trace_conflict_fixture_hard_fail_and_file_unchanged(self) -> None:
        root = self._copy_case_root("case_trace_conflict")
        signals_path = root / ".aiwiki/state/signals.jsonl"
        before = signals_path.read_bytes()
        expected_fragment = (FIXTURE_DIR / "case_trace_conflict" / "expected" / "exception.txt").read_text(encoding="utf-8").strip()

        with self.assertRaisesRegex(RuntimeError, expected_fragment):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

        self.assertEqual(signals_path.read_bytes(), before)

    def test_existing_signals_internal_trace_conflict_hard_fail(self) -> None:
        root = self.temp_root / "existing-conflict"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        base = _read_jsonl(FIXTURE_DIR / "case_trace_conflict" / "root" / ".aiwiki" / "state" / "signals.jsonl")[0]
        conflict = dict(base)
        conflict["signal_id"] = "sig-20260424-confl9999"
        conflict["trace_id"] = "22222222-2222-4222-8222-222222222222"
        conflict["source_event_ref"] = ".aiwiki/state/runtime-history.jsonl#L9"
        signals_path.write_text(json.dumps(base, separators=(",", ":")) + "\n" + json.dumps(conflict, separators=(",", ":")) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "(corrupt|conflict)"):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

    def test_existing_signals_malformed_json_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-json"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text("{bad\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid signals.jsonl JSON"):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

    def test_existing_signals_non_object_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-non-object"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text("[]\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "expected object"):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

    def test_existing_signals_schema_invalid_hard_fail(self) -> None:
        root = self.temp_root / "bad-existing-schema"
        signals_path = root / ".aiwiki/state/signals.jsonl"
        signals_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.write_text(json.dumps({"schema_version": 1}, sort_keys=True) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "invalid signals.jsonl record"):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")


class TestBadEventTolerance(_FixtureCase):
    def test_bad_event_fixture_tolerates_errors_and_keeps_valid_rows(self) -> None:
        root = self._copy_case_root("case_bad_event")
        expected_summary = json.loads((FIXTURE_DIR / "case_bad_event" / "expected" / "summary.json").read_text(encoding="utf-8"))

        result = collect_signals(root, trace_id=expected_summary["trace_id"])

        for key in ("scanned_count", "new_count", "duplicate_count", "unmapped_count", "invalid_count"):
            self.assertEqual(result[key], expected_summary[key])
        self.assertEqual(result["emitted_by_kind"], expected_summary["emitted_by_kind"])
        self.assertEqual(result["skip_examples"], expected_summary["skip_examples"])

        actual_records = _normalized_signal_records(_read_jsonl(root / ".aiwiki/state/signals.jsonl"))
        expected_records = _normalized_signal_records(_read_jsonl(FIXTURE_DIR / "case_bad_event" / "expected" / "signals.jsonl"))
        self.assertEqual(actual_records, expected_records)

    def test_llm_failed_with_unknown_protocol_is_invalid(self) -> None:
        root = self.temp_root / "llm-invalid-protocol"
        llm_path = root / ".aiwiki/logs/llm-receipts.jsonl"
        llm_path.parent.mkdir(parents=True, exist_ok=True)
        llm_path.write_text(
            json.dumps({"created_at": "2026-04-24T01:00:00+00:00", "status": "failed", "protocol": "unknown"}, sort_keys=True)
            + "\n"
            + json.dumps({"created_at": "2026-04-24T01:01:00+00:00", "status": "success", "protocol": "research"}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        result = collect_signals(
            root,
            sources=["llm_receipt"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["unmapped_count"], 1)
        self.assertTrue(any(item["reason"] == "llm_receipt_invalid_protocol" for item in result["skip_examples"]))

    def test_runtime_review_missing_protocol_is_invalid(self) -> None:
        root = self.temp_root / "runtime-missing-protocol"
        runtime_path = root / ".aiwiki/state/runtime-history.jsonl"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(
            json.dumps({"event_type": "review", "occurred_at": "2026-04-24T01:02:00Z", "page_path": "wiki/decisions/x.md"}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        result = collect_signals(
            root,
            sources=["runtime_history"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["unmapped_count"], 0)
        self.assertEqual(result["new_count"], 0)

    def test_non_object_json_line_is_invalid(self) -> None:
        root = self.temp_root / "runtime-non-object"
        runtime_path = root / ".aiwiki/state/runtime-history.jsonl"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(
            "[]\n"
            + json.dumps({"event_type": "review", "occurred_at": "2026-04-24T01:03:00Z", "protocol": "research"}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

        result = collect_signals(
            root,
            sources=["runtime_history"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(result["new_count"], 1)

    def test_invalid_trace_id_input_is_rejected(self) -> None:
        root = self._copy_case_root("case_basic")
        with self.assertRaises(ValueError):
            collect_signals(root, trace_id="NOT-A-UUID")


class TestObserveOnlyAST(unittest.TestCase):
    _ALLOWED_PREFIXES = {
        "aiwiki.signals",
        "aiwiki.app_utils",
    }

    def _collect_imports(self, module_path: Path, module_name: str) -> list[str]:
        return self._collect_imports_from_source(module_path.read_text(encoding="utf-8"), module_name)

    def _collect_imports_from_source(self, source: str, module_name: str) -> list[str]:
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
                continue
            if not isinstance(node, ast.ImportFrom):
                continue

            parts = module_name.split(".")
            prefix = parts[:-node.level] if node.level > 0 else []
            if node.module:
                base = ".".join([*prefix, node.module]) if prefix else node.module
            else:
                base = ".".join(prefix)

            for alias in node.names:
                if base == "aiwiki":
                    imports.append(f"aiwiki.{alias.name}")
                elif base:
                    imports.append(base)
                else:
                    imports.append(alias.name)
        return imports

    def _is_allowed(self, module: str) -> bool:
        if module in sys.stdlib_module_names or module.split(".")[0] in sys.stdlib_module_names:
            return True
        for prefix in self._ALLOWED_PREFIXES:
            if module == prefix or module.startswith(prefix + "."):
                return True
        return False

    def test_only_allowlisted_imports_in_collector_and_adapters(self) -> None:
        src_root = Path(__file__).resolve().parent.parent / "src" / "aiwiki" / "signals"
        collector_imports = self._collect_imports(src_root / "collector.py", "aiwiki.signals.collector")
        adapters_imports = self._collect_imports(src_root / "adapters.py", "aiwiki.signals.adapters")
        all_imports = collector_imports + adapters_imports

        offending = sorted(name for name in all_imports if not self._is_allowed(name))
        self.assertEqual(offending, [])

    def test_adapters_does_not_import_app_utils(self) -> None:
        src_root = Path(__file__).resolve().parent.parent / "src" / "aiwiki" / "signals"
        adapters_imports = self._collect_imports(src_root / "adapters.py", "aiwiki.signals.adapters")
        self.assertTrue(all(not name.startswith("aiwiki.app_utils") for name in adapters_imports))

    def test_from_aiwiki_runner_is_rejected_by_allowlist(self) -> None:
        imports = self._collect_imports_from_source("from aiwiki import runner\n", "aiwiki.signals.collector")
        self.assertEqual(imports, ["aiwiki.runner"])
        self.assertFalse(self._is_allowed(imports[0]))


class TestFileSystemDiff(_FixtureCase):
    def test_only_signals_file_changes_on_basic_replay(self) -> None:
        root = self._copy_case_root("case_basic")
        before = _snapshot_files(root)

        collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

        after = _snapshot_files(root)
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        self.assertEqual(changed, [".aiwiki/state/signals.jsonl"])

    def test_conflict_replay_keeps_files_unchanged(self) -> None:
        root = self._copy_case_root("case_trace_conflict")
        before = _snapshot_files(root)

        with self.assertRaises(RuntimeError):
            collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

        after = _snapshot_files(root)
        self.assertEqual(before, after)

    def test_idempotent_replay_keeps_files_unchanged(self) -> None:
        root = self._copy_case_root("case_idempotent")
        before = _snapshot_files(root)

        collect_signals(root, trace_id="550e8400-e29b-41d4-a716-446655440000")

        after = _snapshot_files(root)
        self.assertEqual(before, after)


class TestKindMapping(unittest.TestCase):
    def test_runtime_review_maps_to_review_feedback(self) -> None:
        seeds = adapters._runtime_history_to_signals(
            {
                "event_type": "review",
                "occurred_at": "2026-04-24T02:00:00Z",
                "protocol": "research",
                "page_path": "wiki/decisions/a.md",
            },
            line_no=1,
            rel_path=".aiwiki/state/runtime-history.jsonl",
        )
        self.assertEqual(seeds[0].record_base["kind"], "review_feedback")
        self.assertEqual(seeds[0].record_base["severity"], "medium")
        self.assertEqual(seeds[0].record_base["emitted_by"], "user")

    def test_runtime_nightly_maps_to_schedule_tick(self) -> None:
        seeds = adapters._runtime_history_to_signals(
            {
                "event_type": "nightly",
                "occurred_at": "2026-04-24T02:01:00Z",
                "protocol": "ops",
            },
            line_no=2,
            rel_path=".aiwiki/state/runtime-history.jsonl",
        )
        self.assertEqual(seeds[0].record_base["kind"], "schedule_tick")
        self.assertEqual(seeds[0].record_base["severity"], "low")
        self.assertEqual(seeds[0].record_base["emitted_by"], "nightly")

    def test_llm_failed_maps_to_runtime_failure(self) -> None:
        seeds = adapters._llm_receipt_to_signals(
            {
                "status": "failed",
                "protocol": "general",
                "created_at": "2026-04-24T02:02:00+00:00",
            },
            line_no=1,
            rel_path=".aiwiki/logs/llm-receipts.jsonl",
            allowed_protocols={"general", "investing", "research", "product", "ops"},
        )
        self.assertEqual(seeds[0].record_base["kind"], "runtime_failure")
        self.assertEqual(seeds[0].record_base["severity"], "high")
        self.assertEqual(seeds[0].record_base["emitted_by"], "external")

    def test_query_event_is_unmapped(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "query", "occurred_at": "2026-04-24T02:03:00Z", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_rewrite_apply_event_is_unmapped(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "rewrite-apply", "occurred_at": "2026-04-24T02:04:00Z", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_nightly_auto_bundle_event_is_unmapped(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "nightly-auto-bundle", "occurred_at": "2026-04-24T02:05:00Z", "protocol": "ops"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_judgment_relation_refresh_event_is_unmapped(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "judgment-relation-refresh", "occurred_at": "2026-04-24T02:06:00Z", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_mapped_invalid_reason_for_runtime_missing_protocol(self) -> None:
        reason = collector._mapped_invalid_reason("runtime_history", {"event_type": "review"})
        self.assertEqual(reason, "runtime_history_missing_protocol")

    def test_mapped_invalid_reason_for_llm_missing_protocol(self) -> None:
        reason = collector._mapped_invalid_reason("llm_receipt", {"status": "failed"})
        self.assertEqual(reason, "llm_receipt_missing_protocol")


class TestCLI(_FixtureCase):
    def _run_main(self, root: Path, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = main(["--root", str(root), *argv])
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_parser_registers_signals_replay_between_run_nightly_and_llm_check(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        names = list(action.choices.keys())
        self.assertLess(names.index("run-nightly"), names.index("signals-replay"))
        self.assertLess(names.index("signals-replay"), names.index("llm-check"))

    def test_parser_signals_replay_flags(self) -> None:
        parser = build_parser()
        action = next(item for item in parser._actions if getattr(item, "dest", "") == "command")
        replay_parser = action.choices["signals-replay"]
        source_action = next(item for item in replay_parser._actions if item.dest == "source")
        trace_action = next(item for item in replay_parser._actions if item.dest == "trace_id")
        self.assertEqual(tuple(source_action.choices), ("runtime_history", "llm_receipt", "archive"))
        self.assertEqual(source_action.option_strings, ["--source"])
        self.assertEqual(trace_action.option_strings, ["--trace-id"])

    def test_main_dispatches_signals_replay_with_filters_and_trace_id(self) -> None:
        with patch("aiwiki.cli.collect_signals", return_value={"status": "ok"}) as mocked:
            code, payload, stderr = self._run_main(
                self.temp_root,
                ["signals-replay", "--source", "runtime_history", "--source", "archive", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"],
            )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        mocked.assert_called_once_with(
            self.temp_root,
            sources=["runtime_history", "archive"],
            trace_id="550e8400-e29b-41d4-a716-446655440000",
        )
        self.assertEqual(payload["status"], "ok")

    def test_main_dispatches_signals_replay_defaults(self) -> None:
        with patch("aiwiki.cli.collect_signals", return_value={"status": "ok"}) as mocked:
            code, payload, stderr = self._run_main(self.temp_root, ["signals-replay"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        mocked.assert_called_once_with(self.temp_root, sources=None, trace_id=None)
        self.assertEqual(payload["status"], "ok")

    def test_cli_outputs_summary_fixed_keys_end_to_end(self) -> None:
        root = self._copy_case_root("case_basic")
        code, payload, stderr = self._run_main(root, ["signals-replay", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            set(payload.keys()),
            {
                "status",
                "trace_id",
                "signals_path",
                "sources",
                "scanned_count",
                "new_count",
                "duplicate_count",
                "unmapped_count",
                "invalid_count",
                "emitted_by_kind",
                "skip_examples",
            },
        )

    def test_cli_source_filter_end_to_end(self) -> None:
        root = self._copy_case_root("case_basic")
        code, payload, _stderr = self._run_main(
            root,
            ["signals-replay", "--source", "llm_receipt", "--trace-id", "550e8400-e29b-41d4-a716-446655440000"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["sources"], ["llm_receipt"])
        self.assertEqual(payload["new_count"], 1)


class TestSchemaDeferredFix(unittest.TestCase):
    def _base(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "signal_id": "sig-20260424-schema01",
            "dedupe_key": "review_feedback:research:runtime_history:sha256-1234567890abcdef",
            "kind": "review_feedback",
            "scope": {
                "protocol": "research",
                "source_ids": [],
                "concept_slugs": [],
                "elixir_refs": [],
                "judgment_refs": [],
            },
            "severity": "medium",
            "evidence_refs": [],
            "emitted_at": "2026-04-24T04:00:00Z",
            "emitted_by": "user",
            "source_kind": "runtime_history",
            "source_event_ref": ".aiwiki/state/runtime-history.jsonl#L1",
            "trace_id": "550e8400-e29b-41d4-a716-446655440000",
        }

    def test_row_id_rejected_for_runtime_history(self) -> None:
        record = self._base()
        record["source_kind"] = "runtime_history"
        record["source_event_ref"] = ".aiwiki/state/runtime-history.jsonl:row-1"
        self.assertFalse(validate(record).ok)

    def test_row_id_rejected_for_llm_receipt(self) -> None:
        record = self._base()
        record["source_kind"] = "llm_receipt"
        record["source_event_ref"] = ".aiwiki/logs/llm-receipts.jsonl:row-1"
        self.assertFalse(validate(record).ok)

    def test_row_id_rejected_for_archive_event(self) -> None:
        record = self._base()
        record["source_kind"] = "archive_event"
        record["source_event_ref"] = ".aiwiki/state/execution-receipts.jsonl:row-1"
        self.assertFalse(validate(record).ok)

    def test_row_id_rejected_for_review_outcome(self) -> None:
        record = self._base()
        record["source_kind"] = "review_outcome"
        record["source_event_ref"] = ".aiwiki/state/review-outcome.jsonl:row-1"
        self.assertFalse(validate(record).ok)

    def test_row_id_allowed_for_protocol_learning_event(self) -> None:
        record = self._base()
        record["source_kind"] = "protocol_learning_event"
        record["source_event_ref"] = ".aiwiki/state/protocol-learning.json:row-1"
        self.assertTrue(validate(record).ok)

    def test_absolute_path_with_allowed_substring_rejected(self) -> None:
        record = self._base()
        record["source_kind"] = "runtime_history"
        record["source_event_ref"] = "/foo/runtime-history.jsonl#L1"
        result = validate(record)
        self.assertFalse(result.ok)
        self.assertTrue(any("absolute" in error or "relative" in error for error in result.errors))


class TestAdapters(unittest.TestCase):
    def test_source_rel_path_mapping(self) -> None:
        self.assertEqual(adapters.source_rel_path("runtime_history"), ".aiwiki/state/runtime-history.jsonl")
        self.assertEqual(adapters.source_rel_path("llm_receipt"), ".aiwiki/logs/llm-receipts.jsonl")
        self.assertEqual(adapters.source_rel_path("archive"), ".aiwiki/state/execution-receipts.jsonl")

    def test_source_rel_path_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            adapters.source_rel_path("unknown")

    def test_source_path_joins_root(self) -> None:
        root = Path("/tmp/demo-root")
        self.assertEqual(adapters.source_path(root, "runtime_history"), root / ".aiwiki/state/runtime-history.jsonl")

    def test_iter_source_lines_handles_missing_file(self) -> None:
        root = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(list(adapters.iter_source_lines(root, "runtime_history")), [])
        finally:
            shutil.rmtree(root)

    def test_iter_source_lines_skips_blank_lines(self) -> None:
        root = Path(tempfile.mkdtemp())
        try:
            path = root / ".aiwiki/state/runtime-history.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n" + json.dumps({"a": 1}) + "\n\n", encoding="utf-8")
            rows = list(adapters.iter_source_lines(root, "runtime_history"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], 2)
        finally:
            shutil.rmtree(root)

    def test_runtime_adapter_unmapped_event(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "query", "occurred_at": "2026-04-24T03:00:00Z", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_runtime_adapter_requires_protocol(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "review", "occurred_at": "2026-04-24T03:01:00Z"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_runtime_adapter_requires_emitted_at(self) -> None:
        self.assertEqual(
            adapters._runtime_history_to_signals(
                {"event_type": "review", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/state/runtime-history.jsonl",
            ),
            [],
        )

    def test_runtime_adapter_sets_corpus_id_if_present(self) -> None:
        seeds = adapters._runtime_history_to_signals(
            {
                "event_type": "review",
                "occurred_at": "2026-04-24T03:02:00Z",
                "protocol": "research",
                "corpus_id": "research-c1",
            },
            line_no=1,
            rel_path=".aiwiki/state/runtime-history.jsonl",
        )
        self.assertEqual(seeds[0].record_base["scope"]["corpus_id"], "research-c1")

    def test_llm_adapter_requires_failed_status(self) -> None:
        self.assertEqual(
            adapters._llm_receipt_to_signals(
                {"status": "success", "protocol": "research", "created_at": "2026-04-24T03:03:00+00:00"},
                line_no=1,
                rel_path=".aiwiki/logs/llm-receipts.jsonl",
                allowed_protocols={"research"},
            ),
            [],
        )

    def test_llm_adapter_requires_protocol_in_closed_set(self) -> None:
        self.assertEqual(
            adapters._llm_receipt_to_signals(
                {"status": "failed", "protocol": "unknown", "created_at": "2026-04-24T03:04:00+00:00"},
                line_no=1,
                rel_path=".aiwiki/logs/llm-receipts.jsonl",
                allowed_protocols={"research"},
            ),
            [],
        )

    def test_llm_adapter_requires_created_at(self) -> None:
        self.assertEqual(
            adapters._llm_receipt_to_signals(
                {"status": "failed", "protocol": "research"},
                line_no=1,
                rel_path=".aiwiki/logs/llm-receipts.jsonl",
                allowed_protocols={"research"},
            ),
            [],
        )

    def test_archive_adapter_returns_empty(self) -> None:
        self.assertEqual(
            adapters._archive_receipt_to_signals({"a": 1}, receipt_rel_path=".aiwiki/state/execution-receipts.jsonl", history_line_no=None),
            [],
        )

    def test_source_identity_is_stable_with_sorted_json(self) -> None:
        left = adapters._source_identity({"b": 1, "a": 2})
        right = adapters._source_identity({"a": 2, "b": 1})
        self.assertEqual(left, right)
        self.assertTrue(left.startswith("sha256-"))

    def test_string_list_and_unique_sorted_helpers(self) -> None:
        self.assertEqual(adapters._string_list("bad"), [])
        self.assertEqual(adapters._string_list(["a", 1, "b"]), ["a", "b"])
        self.assertEqual(adapters._unique_sorted_strings(["b", "a", "a", 1]), ["a", "b"])

    def test_normalize_emitted_at_variants(self) -> None:
        self.assertEqual(adapters._normalize_emitted_at("2026-04-24T03:05:00Z"), "2026-04-24T03:05:00Z")
        self.assertEqual(adapters._normalize_emitted_at("2026-04-24T03:05:00+00:00"), "2026-04-24T03:05:00Z")
        self.assertIsNone(adapters._normalize_emitted_at("2026-04-24 03:05:00"))
        self.assertIsNone(adapters._normalize_emitted_at("bad"))


if __name__ == "__main__":
    unittest.main()
