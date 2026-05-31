from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    execution_receipt_history_path,
    load_machine_memory_action_state,
    load_manual_link_state,
    save_machine_memory_action_state,
)
from aiwiki.app_utils import parse_frontmatter, render_frontmatter
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.execution.machine_memory_actions import (
    MachineMemoryActionHalfWriteError,
    MachineMemoryActionReceiptError,
    apply_machine_memory_action,
    revert_machine_memory_action,
)
from aiwiki.render.paths import execution_receipt_path

ACTION_ID = "manual-link-action"
CITATION_ACTION_ID = "citation-refresh-action"
RESOLVE_MONITOR_ACTION_ID = "resolve-monitor-action"


def _setup_manual_link_action(root: Path) -> tuple[dict[str, str], str]:
    ensure_layout(root)
    sample = root / "sample.md"
    sample.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(root, str(sample), title="Transformer Scaling")
    compile_wiki(root)
    concept_slug = next(path.stem for path in sorted((root / "wiki" / "concepts").glob("*.md")))
    save_machine_memory_action_state(
        root,
        {
            "version": 1,
            "actions": [
                {
                    "id": ACTION_ID,
                    "kind": "add-source-concept-link",
                    "title": "Manual safe apply link",
                    "reason": "Backfill source/concept link.",
                    "primary_path": f"wiki/sources/{entry['id']}.md",
                    "secondary_path": f"wiki/concepts/{concept_slug}.md",
                    "status": "accepted",
                    "priority": "low",
                    "active": True,
                    "source_ids": [entry["id"]],
                    "concept_slugs": [concept_slug],
                }
            ],
        },
    )
    return entry, concept_slug


def _write_apply_bundle(root: Path, action_id: str = ACTION_ID) -> dict[str, object]:
    dry_run = apply_machine_memory_action(root, action_id, dry_run=True)
    bundle_path = root / str(dry_run["bundle_path"])
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(
        json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dry_run


def _apply_manual_link(root: Path, *, note: str = "Apply manual link.") -> dict[str, object]:
    dry_run = _write_apply_bundle(root)
    return apply_machine_memory_action(root, ACTION_ID, note=note, bundle_path=str(dry_run["bundle_path"]))


def _setup_citation_action(root: Path) -> Path:
    ensure_layout(root)
    source = root / "wiki" / "sources" / "source-a.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("---\ntitle: \"Source A\"\nkind: \"source\"\n---\n\n# Source A\n\nOld evidence.\n", encoding="utf-8")
    judgment = root / "wiki" / "judgments" / "scaling-judgment.md"
    judgment.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "title": "Scaling Judgment",
        "kind": "judgment",
        "citations": ["wiki/sources/source-a.md"],
        "citation_snapshots": ["wiki/sources/source-a.md#old-digest"],
    }
    judgment.write_text(f"{render_frontmatter(frontmatter)}\n\n# Scaling Judgment\n\nInitial judgment.\n", encoding="utf-8")
    save_machine_memory_action_state(
        root,
        {
            "version": 1,
            "actions": [
                {
                    "id": CITATION_ACTION_ID,
                    "kind": "refresh-citation-snapshots",
                    "title": "Refresh citation snapshots",
                    "reason": "Citation digest changed.",
                    "primary_path": "wiki/judgments/scaling-judgment.md",
                    "status": "accepted",
                    "priority": "low",
                    "active": True,
                }
            ],
        },
    )
    return judgment


def _setup_resolve_monitor_action(root: Path) -> None:
    ensure_layout(root)
    save_machine_memory_action_state(
        root,
        {
            "version": 1,
            "actions": [
                {
                    "id": RESOLVE_MONITOR_ACTION_ID,
                    "kind": "monitor-bridge-concept",
                    "title": "Resolve monitor",
                    "reason": "Monitor is resolved.",
                    "primary_path": "wiki/indexes/repair-backlog.md",
                    "status": "accepted",
                    "priority": "low",
                    "active": True,
                }
            ],
        },
    )


def _manual_link_for_action(root: Path, action_id: str = ACTION_ID) -> dict[str, object] | None:
    manual_state = load_manual_link_state(root)
    return next(
        (
            item
            for item in manual_state["source_to_concept"]
            if str(item.get("origin_action_id") or "") == action_id
        ),
        None,
    )


def _action_status(root: Path, action_id: str = ACTION_ID) -> str:
    state = load_machine_memory_action_state(root)
    action = next(item for item in state["actions"] if item["id"] == action_id)
    return str(action["status"])


def _history_lines(root: Path) -> list[str]:
    path = execution_receipt_history_path(root)
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _audit_lines(root: Path) -> list[str]:
    path = root / ".aiwiki" / "state" / "audit.jsonl"
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_apply_manual_link_happy_path_atomic_writes(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    result = _apply_manual_link(tmp_path)

    receipt_path = tmp_path / str(result["receipt_path"])
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["operation"] == "apply"
    manual_link = _manual_link_for_action(tmp_path)
    assert manual_link is not None
    assert manual_link["active"] is True
    assert manual_link["origin_action_id"] == ACTION_ID
    assert _action_status(tmp_path) == "resolved"
    assert len(_history_lines(tmp_path)) == 1


def test_apply_manual_link_receipt_uses_root_agentic_policy(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    policy_path = tmp_path / ".aiwiki" / "state" / "autonomy-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps({"schema_version": 3, "autonomy_profile": "agentic"}) + "\n", encoding="utf-8")

    result = _apply_manual_link(tmp_path)

    receipt = json.loads((tmp_path / str(result["receipt_path"])).read_text(encoding="utf-8"))
    assert receipt["autonomy_domain"] == "non_core_semantic"
    assert receipt["llm_governed"] is True


def test_apply_manual_link_auto_reverts_on_verify_failure(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path)

    with patch("aiwiki.execution.machine_memory_actions.compile_wiki", side_effect=RuntimeError("verify failed")):
        with pytest.raises(RuntimeError, match="auto-revert completed"):
            apply_machine_memory_action(tmp_path, ACTION_ID, bundle_path=str(dry_run["bundle_path"]))

    manual_link = _manual_link_for_action(tmp_path)
    assert manual_link is not None
    assert manual_link["active"] is False
    assert _action_status(tmp_path) == "proposed"
    receipts = [json.loads(line) for line in _history_lines(tmp_path)]
    assert [receipt["operation"] for receipt in receipts] == ["apply", "revert"]


def test_apply_manual_link_receipt_history_failure_rolls_back(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path)

    with patch(
        "aiwiki.execution.machine_memory_actions.append_execution_receipt_history",
        side_effect=RuntimeError("forced"),
    ):
        with pytest.raises(MachineMemoryActionReceiptError) as exc_info:
            apply_machine_memory_action(tmp_path, ACTION_ID, bundle_path=str(dry_run["bundle_path"]))

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "forced"
    assert not execution_receipt_path(tmp_path, ACTION_ID).exists()
    manual_link = _manual_link_for_action(tmp_path)
    assert manual_link is None or manual_link.get("active") is not True
    assert _action_status(tmp_path) == "accepted"


def test_apply_citation_happy_path_atomic_writes(tmp_path: Path) -> None:
    judgment = _setup_citation_action(tmp_path)
    before_frontmatter = parse_frontmatter(judgment.read_text(encoding="utf-8"))
    dry_run = _write_apply_bundle(tmp_path, CITATION_ACTION_ID)

    result = apply_machine_memory_action(
        tmp_path,
        CITATION_ACTION_ID,
        note="Refresh citation snapshots.",
        bundle_path=str(dry_run["bundle_path"]),
    )

    assert result["apply_mode"] == "citation-snapshot-refresh"
    assert (tmp_path / str(result["receipt_path"])).exists()
    after_frontmatter = parse_frontmatter(judgment.read_text(encoding="utf-8"))
    assert after_frontmatter["citation_snapshots"] == dry_run["preview"]["updated_citation_snapshots"]
    assert after_frontmatter["citation_snapshots"] != before_frontmatter["citation_snapshots"]
    assert _action_status(tmp_path, CITATION_ACTION_ID) == "resolved"
    assert len(_history_lines(tmp_path)) == 1


def test_apply_citation_action_state_failure_rolls_back_page_and_receipt(tmp_path: Path) -> None:
    judgment = _setup_citation_action(tmp_path)
    before_bytes = judgment.read_bytes()
    dry_run = _write_apply_bundle(tmp_path, CITATION_ACTION_ID)

    with patch(
        "aiwiki.execution.machine_memory_actions._save_machine_memory_action_records",
        side_effect=RuntimeError("forced save failure"),
    ):
        with pytest.raises(MachineMemoryActionReceiptError):
            apply_machine_memory_action(tmp_path, CITATION_ACTION_ID, bundle_path=str(dry_run["bundle_path"]))

    assert judgment.read_bytes() == before_bytes
    assert not execution_receipt_path(tmp_path, CITATION_ACTION_ID).exists()
    assert _action_status(tmp_path, CITATION_ACTION_ID) == "accepted"
    assert _history_lines(tmp_path) == []


def test_revert_citation_receipt_history_failure_rolls_back_page_to_applied_state(tmp_path: Path) -> None:
    judgment = _setup_citation_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path, CITATION_ACTION_ID)
    apply_result = apply_machine_memory_action(tmp_path, CITATION_ACTION_ID, bundle_path=str(dry_run["bundle_path"]))
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    applied_bytes = judgment.read_bytes()
    revert_receipt_path = apply_receipt_path.parent / "reverts" / apply_receipt_path.name

    with patch(
        "aiwiki.execution.machine_memory_actions.append_execution_receipt_history",
        side_effect=RuntimeError("forced revert history failure"),
    ):
        with pytest.raises(MachineMemoryActionReceiptError):
            revert_machine_memory_action(tmp_path, CITATION_ACTION_ID, note="Revert should roll back.")

    assert judgment.read_bytes() == applied_bytes
    assert apply_receipt_path.exists()
    assert not revert_receipt_path.exists()
    assert _action_status(tmp_path, CITATION_ACTION_ID) == "resolved"
    assert len(_history_lines(tmp_path)) == 1


def test_revert_manual_link_happy_path(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    apply_result = _apply_manual_link(tmp_path)
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])

    revert_result = revert_machine_memory_action(tmp_path, ACTION_ID, note="Rollback manual link.")

    revert_receipt_path = tmp_path / str(revert_result["receipt_path"])
    assert apply_receipt_path.exists()
    assert revert_receipt_path.exists()
    assert revert_receipt_path.relative_to(apply_receipt_path.parent).as_posix() == "reverts/manual-link-action.json"
    assert json.loads(revert_receipt_path.read_text(encoding="utf-8"))["operation"] == "revert"
    manual_link = _manual_link_for_action(tmp_path)
    assert manual_link is not None
    assert manual_link["active"] is False
    assert manual_link.get("reverted_at")


def test_revert_manual_link_receipt_history_failure_rolls_back(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    apply_result = _apply_manual_link(tmp_path)
    apply_receipt_path = tmp_path / str(apply_result["receipt_path"])
    revert_receipt_path = apply_receipt_path.parent / "reverts" / apply_receipt_path.name

    with patch(
        "aiwiki.execution.machine_memory_actions.append_execution_receipt_history",
        side_effect=RuntimeError("forced"),
    ):
        with pytest.raises(MachineMemoryActionReceiptError):
            revert_machine_memory_action(tmp_path, ACTION_ID, note="Rollback should fail.")

    manual_link = _manual_link_for_action(tmp_path)
    assert manual_link is not None
    assert manual_link["active"] is True
    assert apply_receipt_path.exists()
    assert not revert_receipt_path.exists()
    assert _action_status(tmp_path) == "resolved"
    assert len(_history_lines(tmp_path)) == 1


def test_apply_manual_link_receipt_write_failure_rolls_back(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path)
    receipt_path = execution_receipt_path(tmp_path, ACTION_ID)

    from aiwiki.execution import machine_memory_actions as mma

    original_atomic_write_text = mma.atomic_write_text


    def fail_receipt_write(path: Path, text: str) -> None:
        if Path(path) == receipt_path:
            raise RuntimeError("forced receipt write failure")
        original_atomic_write_text(path, text)

    with patch("aiwiki.execution.machine_memory_actions.atomic_write_text", side_effect=fail_receipt_write):
        with pytest.raises(MachineMemoryActionReceiptError):
            apply_machine_memory_action(tmp_path, ACTION_ID, bundle_path=str(dry_run["bundle_path"]))

    assert not receipt_path.exists()
    assert _manual_link_for_action(tmp_path) is None
    assert _action_status(tmp_path) == "accepted"
    assert _history_lines(tmp_path) == []


def test_apply_resolve_monitor_happy_path_writes_receipt_without_mode_specific_mutation(tmp_path: Path) -> None:
    _setup_resolve_monitor_action(tmp_path)

    dry_run = _write_apply_bundle(tmp_path, RESOLVE_MONITOR_ACTION_ID)
    result = apply_machine_memory_action(
        tmp_path,
        RESOLVE_MONITOR_ACTION_ID,
        note="Resolve monitor.",
        bundle_path=str(dry_run["bundle_path"]),
    )

    assert result["apply_mode"] == "resolve-monitor"
    assert result["status"] == "resolved"
    receipt_path = tmp_path / str(result["receipt_path"])
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["operation"] == "apply"
    assert _action_status(tmp_path, RESOLVE_MONITOR_ACTION_ID) == "resolved"
    assert _manual_link_for_action(tmp_path, RESOLVE_MONITOR_ACTION_ID) is None
    assert len(_history_lines(tmp_path)) == 1


def test_apply_resolve_monitor_action_state_failure_rolls_back_receipt_history_and_audit(tmp_path: Path) -> None:
    _setup_resolve_monitor_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path, RESOLVE_MONITOR_ACTION_ID)
    audit_before_apply = _audit_lines(tmp_path)

    with patch(
        "aiwiki.execution.machine_memory_actions._save_machine_memory_action_records",
        side_effect=RuntimeError("forced resolve-monitor save failure"),
    ):
        with pytest.raises(MachineMemoryActionReceiptError):
            apply_machine_memory_action(
                tmp_path,
                RESOLVE_MONITOR_ACTION_ID,
                bundle_path=str(dry_run["bundle_path"]),
            )

    assert not execution_receipt_path(tmp_path, RESOLVE_MONITOR_ACTION_ID).exists()
    assert _history_lines(tmp_path) == []
    assert _audit_lines(tmp_path) == audit_before_apply
    assert _action_status(tmp_path, RESOLVE_MONITOR_ACTION_ID) == "accepted"


def test_apply_rollback_failure_raises_half_write_error(tmp_path: Path) -> None:
    _setup_manual_link_action(tmp_path)
    dry_run = _write_apply_bundle(tmp_path)

    def fail_restore(path: Path, original: bytes | None) -> None:
        raise RuntimeError(f"forced restore failure for {path.name}")

    with patch(
        "aiwiki.execution.machine_memory_actions.append_execution_receipt_history",
        side_effect=RuntimeError("forced"),
    ), patch(
        "aiwiki.execution.machine_memory_actions._restore_file_bytes",
        side_effect=fail_restore,
    ):
        with pytest.raises(MachineMemoryActionHalfWriteError) as exc_info:
            apply_machine_memory_action(tmp_path, ACTION_ID, bundle_path=str(dry_run["bundle_path"]))

    message = str(exc_info.value)
    assert "rollback also failed" in message
    assert "forced restore failure" in message


def test_apply_uses_atomic_write_text_for_receipt() -> None:
    source = (Path(__file__).resolve().parents[1] / "src/aiwiki/execution/machine_memory_actions.py").read_text(
        encoding="utf-8"
    )
    assert re.search(r"\b\w*receipt\w*\.write_text\(\s*json\.dumps\(", source) is None
    assert re.search(r"\bpage\.write_text\(\s*f[\"']\{render_frontmatter", source) is None
    assert "atomic_write_text(\n                page," in source


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    # scripts/verify.sh uses unittest discover, which does not collect pytest-style
    # tmp_path tests. Keep the public pytest surface while executing the
    # same cases under unittest coverage.
    del loader, tests, pattern
    suite = unittest.TestSuite()
    tmp_path_tests = [
        test_apply_manual_link_happy_path_atomic_writes,
        test_apply_manual_link_receipt_uses_root_agentic_policy,
        test_apply_manual_link_auto_reverts_on_verify_failure,
        test_apply_manual_link_receipt_history_failure_rolls_back,
        test_apply_citation_happy_path_atomic_writes,
        test_apply_citation_action_state_failure_rolls_back_page_and_receipt,
        test_revert_citation_receipt_history_failure_rolls_back_page_to_applied_state,
        test_revert_manual_link_happy_path,
        test_revert_manual_link_receipt_history_failure_rolls_back,
        test_apply_manual_link_receipt_write_failure_rolls_back,
        test_apply_resolve_monitor_happy_path_writes_receipt_without_mode_specific_mutation,
        test_apply_resolve_monitor_action_state_failure_rolls_back_receipt_history_and_audit,
        test_apply_rollback_failure_raises_half_write_error,
    ]

    def make_case(fn):
        def run() -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                fn(Path(tempdir))

        run.__name__ = fn.__name__
        return unittest.FunctionTestCase(run)

    for test_fn in tmp_path_tests:
        suite.addTest(make_case(test_fn))
    suite.addTest(unittest.FunctionTestCase(test_apply_uses_atomic_write_text_for_receipt))
    return suite
