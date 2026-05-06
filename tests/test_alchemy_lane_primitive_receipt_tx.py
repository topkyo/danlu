from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiwiki.runner.alchemy as runner_alchemy
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import execution_receipt_history_path
from aiwiki.execution.audit_preview import AUDIT_STREAM_PATH
from aiwiki.render.paths import execution_receipts_dir


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class AlchemyLanePrimitiveReceiptTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        ensure_layout(self.root)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _plan(self, primitive: str) -> dict[str, object]:
        return {
            "status": "ok",
            "lane": "light",
            "scope": "all",
            "selected_count": 1,
            "scope_preview": {
                "protocols": ["research"],
                "trace_ids": ["550e8400-e29b-41d4-a716-446655440000"],
            },
            "primitive_plan": [
                {
                    "primitive": primitive,
                    "apply_supported": True,
                    "apply_blocker": "",
                }
            ],
        }

    def _primitive_result(self, primitive: str) -> dict[str, object]:
        return {
            "updated_source_pages": [f"wiki/sources/{primitive}.md"],
            "state_path": f".aiwiki/state/{primitive}-state.json",
            "counts": {"primitive": 1},
        }

    def _patch_primitive(self, primitive: str, *, result: dict[str, object] | None = None, sentinel: Path | None = None):
        """Patch primitive func; if sentinel given, primitive writes it to prove child artifact durability."""
        primitive_result = result or self._primitive_result(primitive)

        def _side_effect(_root: Path) -> dict[str, object]:
            if sentinel is not None:
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                sentinel.write_text(f"child-{primitive}-artifact", encoding="utf-8")
            return primitive_result

        return patch.object(runner_alchemy, self._primitive_func_name(primitive), side_effect=_side_effect)

    def _primitive_func_name(self, primitive: str) -> str:
        return {
            "compile": "compile_wiki",
            "lint": "lint_wiki",
            "nightly": "nightly_health",
        }[primitive]

    def _run_primitive(self, primitive: str) -> dict[str, object]:
        with self._patch_primitive(primitive):
            return runner_alchemy._run_receipted_lane_primitive(
                self.root,
                lane="light",
                scope="all",
                primitive=primitive,
                plan=self._plan(primitive),
                note="tx test",
            )

    def _receipt_files(self) -> set[str]:
        receipts_dir = execution_receipts_dir(self.root)
        if not receipts_dir.exists():
            return set()
        return {p.name for p in receipts_dir.glob("*.json")}

    def test_happy_path_writes_receipt_history_audit_for_compile_lint_nightly(self) -> None:
        for primitive in ("compile", "lint", "nightly"):
            with self.subTest(primitive=primitive):
                self.tempdir.cleanup()
                self.tempdir = tempfile.TemporaryDirectory()
                self.root = Path(self.tempdir.name).resolve()
                ensure_layout(self.root)

                result = self._run_primitive(primitive)

                self.assertEqual(result["primitive"], primitive)
                receipt_path = self.root / str(result["receipt_path"])
                self.assertTrue(receipt_path.exists())
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(receipt["operation"], "alchemy-lane-primitive")
                self.assertEqual(receipt["primitive"], primitive)
                self.assertEqual(receipt["result_summary"]["updated_source_pages_count"], 1)
                self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])
                self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})

    def test_receipt_write_failure_rolls_back_receipt_only_for_compile_lint_nightly(self) -> None:
        for primitive in ("compile", "lint", "nightly"):
            with self.subTest(primitive=primitive):
                self.tempdir.cleanup()
                self.tempdir = tempfile.TemporaryDirectory()
                self.root = Path(self.tempdir.name).resolve()
                ensure_layout(self.root)
                child_result = self._primitive_result(primitive)
                sentinel = self.root / f".aiwiki/state/sentinel-{primitive}.txt"
                original_atomic = runner_alchemy.atomic_write_text

                def flaky(path: Path, content: str, original_atomic=original_atomic, **kwargs: object) -> None:
                    if "execution-receipts" in path.parts and path.suffix == ".json":
                        raise OSError("receipt write failed")
                    original_atomic(path, content, **kwargs)

                with (
                    self._patch_primitive(primitive, result=child_result, sentinel=sentinel) as mocked_primitive,
                    patch.object(runner_alchemy, "atomic_write_text", side_effect=flaky),
                    self.assertRaises(runner_alchemy.AlchemyLanePrimitiveReceiptError),
                ):
                    runner_alchemy._run_receipted_lane_primitive(
                        self.root,
                        lane="light",
                        scope="all",
                        primitive=primitive,
                        plan=self._plan(primitive),
                        note="tx test",
                    )

                self.assertEqual(self._receipt_files(), set())
                self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root)), [])
                self.assertEqual(_read_jsonl(self.root / AUDIT_STREAM_PATH), [])
                mocked_primitive.assert_called_once_with(self.root)
                # child artifact (sentinel) MUST remain — independent fact, not rolled back.
                self.assertTrue(sentinel.exists(), f"child sentinel for {primitive} must survive rollback")
                self.assertEqual(sentinel.read_text(encoding="utf-8"), f"child-{primitive}-artifact")

    def test_history_append_failure_truncates_jsonls_for_compile_lint_nightly(self) -> None:
        for primitive in ("compile", "lint", "nightly"):
            with self.subTest(primitive=primitive):
                self.tempdir.cleanup()
                self.tempdir = tempfile.TemporaryDirectory()
                self.root = Path(self.tempdir.name).resolve()
                ensure_layout(self.root)
                history_path = execution_receipt_history_path(self.root)
                audit_path = self.root / AUDIT_STREAM_PATH
                sentinel = self.root / f".aiwiki/state/sentinel-{primitive}.txt"

                def partial_history(
                    _root: Path,
                    receipt: dict[str, object],
                    history_path=history_path,
                    audit_path=audit_path,
                ) -> None:
                    history_path.parent.mkdir(parents=True, exist_ok=True)
                    with history_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(receipt) + "\n")
                    audit_path.parent.mkdir(parents=True, exist_ok=True)
                    with audit_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"source_stream": "execution_receipts"}) + "\n")
                    raise OSError("history append failed")

                with (
                    self._patch_primitive(primitive, sentinel=sentinel) as mocked_primitive,
                    patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
                    self.assertRaises(runner_alchemy.AlchemyLanePrimitiveReceiptError),
                ):
                    runner_alchemy._run_receipted_lane_primitive(
                        self.root,
                        lane="light",
                        scope="all",
                        primitive=primitive,
                        plan=self._plan(primitive),
                        note="tx test",
                    )

                self.assertEqual(self._receipt_files(), set())
                self.assertEqual(_read_jsonl(history_path), [])
                self.assertEqual(_read_jsonl(audit_path), [])
                mocked_primitive.assert_called_once_with(self.root)
                # child artifact (sentinel) MUST remain — independent fact, not rolled back.
                self.assertTrue(sentinel.exists(), f"child sentinel for {primitive} must survive rollback")

    def test_pre_seeded_jsonl_bytes_preserved_on_history_append_failure(self) -> None:
        history_path = execution_receipt_history_path(self.root)
        audit_path = self.root / AUDIT_STREAM_PATH
        history_path.parent.mkdir(parents=True, exist_ok=True)
        seeded_history = json.dumps({"action_id": "pre-existing-history"}) + "\n"
        history_path.write_text(seeded_history, encoding="utf-8")
        history_size_seeded = history_path.stat().st_size
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        seeded_audit = json.dumps({"audit_event_id": "pre-existing-audit"}) + "\n"
        audit_path.write_text(seeded_audit, encoding="utf-8")
        audit_size_seeded = audit_path.stat().st_size

        def partial_history(_root: Path, receipt: dict[str, object]) -> None:
            with history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt) + "\n")
            with audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"source_stream": "execution_receipts"}) + "\n")
            raise OSError("history append failed")

        with (
            self._patch_primitive("compile"),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
            self.assertRaises(runner_alchemy.AlchemyLanePrimitiveReceiptError),
        ):
            runner_alchemy._run_receipted_lane_primitive(
                self.root,
                lane="light",
                scope="all",
                primitive="compile",
                plan=self._plan("compile"),
                note="tx test",
            )

        self.assertEqual(history_path.stat().st_size, history_size_seeded)
        self.assertEqual(history_path.read_text(encoding="utf-8"), seeded_history)
        self.assertEqual(audit_path.stat().st_size, audit_size_seeded)
        self.assertEqual(audit_path.read_text(encoding="utf-8"), seeded_audit)
        self.assertEqual(self._receipt_files(), set())

    def test_rollback_failure_raises_half_write_loud(self) -> None:
        history_path = execution_receipt_history_path(self.root)

        def partial_history(_root: Path, receipt: dict[str, object]) -> None:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with history_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(receipt) + "\n")
            raise OSError("history failed")

        with (
            self._patch_primitive("compile"),
            patch.object(runner_alchemy, "append_execution_receipt_history", side_effect=partial_history),
            patch.object(runner_alchemy, "_durable_truncate", side_effect=OSError("truncate failed")),
            self.assertRaises(runner_alchemy.AlchemyLanePrimitiveReceiptHalfWriteError) as ctx,
        ):
            runner_alchemy._run_receipted_lane_primitive(
                self.root,
                lane="light",
                scope="all",
                primitive="compile",
                plan=self._plan("compile"),
                note="tx test",
            )

        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertIn("truncate failed", str(ctx.exception.__cause__))
        self.assertIn("tx_error=history failed", str(ctx.exception))
        self.assertIn("rollback_error=truncate failed", str(ctx.exception))

    def test_phase2_lane_runtime_event_failure_isolated(self) -> None:
        with (
            patch("aiwiki.planner.preview_alchemy_lane", return_value=self._plan("compile")),
            patch.object(runner_alchemy, "compile_wiki", return_value=self._primitive_result("compile")),
            patch.object(runner_alchemy, "append_runtime_history", side_effect=OSError("runtime failed")),
            self.assertLogs(runner_alchemy.logger, level="WARNING") as log_ctx,
        ):
            result = runner_alchemy.run_alchemy_lane_apply(
                self.root,
                lane="light",
                scope="all",
                primitives=["compile"],
                note="tx test",
            )

        self.assertEqual(result["status"], "applied")
        primitive_result = result["primitive_results"][0]
        receipt_path = self.root / str(primitive_result["receipt_path"])
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["primitive"], "compile")
        self.assertEqual(_read_jsonl(execution_receipt_history_path(self.root))[-1]["action_id"], receipt["action_id"])
        self.assertIn("execution_receipts", {item["source_stream"] for item in _read_jsonl(self.root / AUDIT_STREAM_PATH)})
        self.assertTrue(any("runtime-history append failed" in msg for msg in log_ctx.output))

    def test_lane_apply_happy_path_writes_started_and_completed_runtime_events(self) -> None:
        """R96.2 NIT-2: prove lane started/completed runtime events are appended on happy path."""
        with (
            patch("aiwiki.planner.preview_alchemy_lane", return_value=self._plan("compile")),
            patch.object(runner_alchemy, "compile_wiki", return_value=self._primitive_result("compile")),
        ):
            result = runner_alchemy.run_alchemy_lane_apply(
                self.root,
                lane="light",
                scope="all",
                primitives=["compile"],
                note="tx test",
            )

        self.assertEqual(result["status"], "applied")
        runtime_history_path = self.root / ".aiwiki" / "state" / "runtime-history.jsonl"
        self.assertTrue(runtime_history_path.exists())
        events = _read_jsonl(runtime_history_path)
        event_types = [str(e.get("event_type") or "") for e in events]
        self.assertIn("alchemy-lane-started", event_types)
        self.assertIn("alchemy-lane-completed", event_types)
