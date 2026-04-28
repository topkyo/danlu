from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiwiki.app_protocol import ensure_layout
from aiwiki.execution.ask import file_back
from aiwiki.execution.l3_proposals import revert_l3_proposal
from aiwiki.render.paths import execution_receipt_path
from aiwiki.runner.alchemy import run_alchemy_propose_apply, run_alchemy_propose_preview


def _write_artifact(path: Path) -> None:
    path.write_text(
        "# Test artifact\n\n"
        "Provenance: wiki/sources/test-source.md\n\n"
        "Body.\n",
        encoding="utf-8",
    )


def test_file_back_derived_hint_mentions_promote(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact)

    result = file_back(tmp_path, str(artifact), kind="derived")

    assert "promote" in result["next_step_hint"]


def test_revert_invalid_receipt_error_is_actionable(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    receipt_id = "l3-proposal-apply-garbage-id-xyz"
    receipt_path = execution_receipt_path(tmp_path, receipt_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "kind": "execution-receipt",
                "generated_by": "wrong",
                "operation": "apply",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError) as exc:
        revert_l3_proposal(tmp_path, receipt_id)

    assert "l3-proposal-apply-<proposal_id>" in str(exc.value)


def test_alchemy_propose_apply_cold_start_raises(tmp_path: Path) -> None:
    ensure_layout(tmp_path)

    with pytest.raises(ValueError) as exc:
        run_alchemy_propose_apply(tmp_path, scope="all")

    message = str(exc.value)
    assert "nightly" in message
    assert "auto-once" in message


def test_alchemy_propose_dry_run_cold_start_marker(tmp_path: Path) -> None:
    ensure_layout(tmp_path)

    preview = run_alchemy_propose_preview(tmp_path, scope="all")
    assert preview["cold_start"] is True

    planner_log = tmp_path / ".aiwiki" / "state" / "planner-log.jsonl"
    planner_log.parent.mkdir(parents=True, exist_ok=True)
    planner_log.write_text("", encoding="utf-8")

    preview = run_alchemy_propose_preview(tmp_path, scope="all")
    assert preview["cold_start"] is False
