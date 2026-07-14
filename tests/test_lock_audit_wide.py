from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from aiwiki.app_utils import _RUNTIME_LOCKS


def _lock_depth(root: Path) -> int:
    return int((_RUNTIME_LOCKS.get(str(root.resolve())) or {}).get("depth", 0))


def _assert_lock_held(root: Path) -> None:
    assert _lock_depth(root) >= 1, "runtime_write_lock not held"


def _assert_lock_not_held(root: Path) -> None:
    assert _lock_depth(root) == 0, "runtime_write_lock unexpectedly held"


def _short_circuit_after_lock_probe(root: Path) -> None:
    _assert_lock_held(root)
    raise RuntimeError("short-circuit after lock probe")


def test_set_active_protocol_acquires_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.app_compile_ops import set_active_protocol

    def probe(*_args: object, **_kwargs: object) -> str:
        _short_circuit_after_lock_probe(tmp_path)

    monkeypatch.setattr("aiwiki.app_compile_ops.resolve_protocol", probe)
    with pytest.raises(RuntimeError, match="short-circuit after lock probe"):
        set_active_protocol(tmp_path, "general")


def test_append_snapshot_acquires_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.metrics_history import append_snapshot

    def probe(*_args: object, **_kwargs: object) -> None:
        _short_circuit_after_lock_probe(tmp_path)

    monkeypatch.setattr("aiwiki.metrics_history.atomic_append_jsonl", probe)
    with pytest.raises(RuntimeError, match="short-circuit after lock probe"):
        append_snapshot(tmp_path, "2026-05-06T00:00:00Z", {"a": 1.0})


def test_set_flag_acquires_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.autonomy_policy import set_flag

    def probe(*_args: object, **_kwargs: object) -> None:
        _short_circuit_after_lock_probe(tmp_path)

    monkeypatch.setattr("aiwiki.autonomy_policy.os.replace", probe)
    with pytest.raises(RuntimeError, match="short-circuit after lock probe"):
        set_flag(tmp_path, "disable_lane_apply", True)


def test_auto_process_once_acquires_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.runner.automation import auto_process_once

    def probe(*_args: object, **_kwargs: object) -> None:
        _short_circuit_after_lock_probe(tmp_path)

    monkeypatch.setattr("aiwiki.runner.automation.compile_wiki", probe)
    with pytest.raises(RuntimeError, match="short-circuit after lock probe"):
        auto_process_once(tmp_path, deterministic_only=True, semantic_lint=False)


def test_write_shell_summary_acquires_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aiwiki.app_shell.meta import write_shell_summary

    def probe(*_args: object, **_kwargs: object) -> None:
        _short_circuit_after_lock_probe(tmp_path)

    monkeypatch.setattr("aiwiki.app_shell.meta.write_json_document_if_changed_ignoring_generated_timestamps", probe)
    with pytest.raises(RuntimeError, match="short-circuit after lock probe"):
        write_shell_summary(tmp_path, {"generated_at": "2026-05-06T00:00:00Z"})


def test_backfill_universal_audit_stream_apply_true_locks_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiwiki.execution.audit_preview import AuditAppendResult, backfill_universal_audit_stream

    record = {
        "audit_event_id": "audit-test-1",
        "source_stream": "runtime_history",
        "source_ref": ".aiwiki/state/runtime-history.jsonl#L1",
    }
    monkeypatch.setattr(
        "aiwiki.execution.audit_preview.preview_universal_audit_stream",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "mode": "dry_run",
            "side_effects_allowed": False,
            "audit_stream_path": ".aiwiki/state/audit.jsonl",
            "audit_stream_exists": False,
            "scanned_count": 1,
            "returned_count": 1,
            "limit": 10,
            "source_counts": {},
            "records": [record],
        },
    )
    monkeypatch.setattr("aiwiki.execution.audit_preview._existing_audit_event_ids", lambda *_args, **_kwargs: set())

    def append_probe(*_args: object, **_kwargs: object) -> AuditAppendResult:
        _assert_lock_held(tmp_path)
        return AuditAppendResult(written=True, reason="appended", record=record)

    monkeypatch.setattr("aiwiki.execution.audit_preview.append_audit", append_probe)
    result = backfill_universal_audit_stream(tmp_path, limit=10, apply=True)
    assert result["appended_count"] == 1


def test_backfill_universal_audit_stream_apply_false_does_not_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiwiki.execution.audit_preview import backfill_universal_audit_stream

    monkeypatch.setattr(
        "aiwiki.execution.audit_preview.preview_universal_audit_stream",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "mode": "dry_run",
            "side_effects_allowed": False,
            "audit_stream_path": ".aiwiki/state/audit.jsonl",
            "audit_stream_exists": False,
            "scanned_count": 0,
            "returned_count": 0,
            "limit": 10,
            "source_counts": {},
            "records": [],
        },
    )

    def existing_probe(*_args: object, **_kwargs: object) -> set[str]:
        _assert_lock_not_held(tmp_path)
        return set()

    monkeypatch.setattr("aiwiki.execution.audit_preview._existing_audit_event_ids", existing_probe)
    result = backfill_universal_audit_stream(tmp_path, limit=10, apply=False)
    assert result["appended_count"] == 0


def test_apply_planner_log_rollback_marker_apply_true_locks_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiwiki.planner.rollback import apply_planner_log_rollback_marker

    preview_record = {
        "source_ref": ".aiwiki/state/planner-log.jsonl#L1",
        "signal_id": "sig-1",
        "trace_id": "trace-1",
        "decision": "accept",
        "mode": "test",
        "dedupe_key": "dedupe-1",
        "decided_at": "2026-05-06T00:00:00Z",
    }
    monkeypatch.setattr(
        "aiwiki.planner.rollback.preview_planner_log_rollback",
        lambda *_args, **_kwargs: {"status": "ok", "records": [preview_record]},
    )
    monkeypatch.setattr("aiwiki.planner.rollback._existing_marker_ids", lambda *_args, **_kwargs: set())

    def append_probe(*_args: object, **_kwargs: object) -> None:
        _assert_lock_held(tmp_path)

    monkeypatch.setattr("aiwiki.planner.rollback.atomic_append_jsonl", append_probe)
    result = apply_planner_log_rollback_marker(tmp_path, limit=10, apply=True)
    assert result["appended_count"] == 1


def test_apply_planner_log_rollback_marker_apply_false_does_not_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aiwiki.planner.rollback import apply_planner_log_rollback_marker

    preview_record = {
        "source_ref": ".aiwiki/state/planner-log.jsonl#L1",
        "signal_id": "sig-1",
        "trace_id": "trace-1",
        "decision": "accept",
        "mode": "test",
        "dedupe_key": "dedupe-1",
        "decided_at": "2026-05-06T00:00:00Z",
    }
    monkeypatch.setattr(
        "aiwiki.planner.rollback.preview_planner_log_rollback",
        lambda *_args, **_kwargs: {"status": "ok", "records": [preview_record]},
    )

    def existing_probe(*_args: object, **_kwargs: object) -> set[str]:
        _assert_lock_not_held(tmp_path)
        return set()

    monkeypatch.setattr("aiwiki.planner.rollback._existing_marker_ids", existing_probe)
    result = apply_planner_log_rollback_marker(tmp_path, limit=10, apply=False)
    assert result["appended_count"] == 0


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    test_functions = [
        test_set_active_protocol_acquires_lock,
        test_append_snapshot_acquires_lock,
        test_set_flag_acquires_lock,
        test_auto_process_once_acquires_lock,
        test_write_shell_summary_acquires_lock,
        test_backfill_universal_audit_stream_apply_true_locks_write,
        test_backfill_universal_audit_stream_apply_false_does_not_lock,
        test_apply_planner_log_rollback_marker_apply_true_locks_write,
        test_apply_planner_log_rollback_marker_apply_false_does_not_lock,
    ]

    def make_case(fn):
        def run() -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                monkeypatch = pytest.MonkeyPatch()
                try:
                    fn(Path(tempdir), monkeypatch)
                finally:
                    monkeypatch.undo()

        run.__name__ = fn.__name__
        return unittest.FunctionTestCase(run)

    for test_fn in test_functions:
        suite.addTest(make_case(test_fn))
    return suite
