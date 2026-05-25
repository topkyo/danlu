from __future__ import annotations

from pathlib import Path

from aiwiki import app_state, app_state_paths


def test_app_state_reexports_path_helpers_from_state_paths(tmp_path):
    checks = [
        ("manifest_path", ()),
        ("machine_memory_state_path", ()),
        ("execution_receipt_history_path", ()),
        ("run_log_path", ()),
        ("runtime_history_path", ()),
        ("machine_memory_action_state_path", ()),
        ("concept_rewrite_state_path", ()),
        ("material_archive_state_path", ()),
        ("agent_pack_path", ("Ops Reviewer",)),
        ("execution_batch_receipt_path", ("batch 42",)),
        ("execution_dry_run_path", ("apply action",)),
        ("run_notes_path", ("run 42",)),
        ("archive_dry_run_path", ("entry 42",)),
        ("rewrite_dry_run_path", ("Concept Alpha",)),
    ]

    for name, extra_args in checks:
        facade = getattr(app_state, name)
        owner = getattr(app_state_paths, name)
        assert facade(tmp_path, *extra_args) == owner(tmp_path, *extra_args)


def test_state_path_helpers_keep_expected_paths(tmp_path):
    root = Path(tmp_path)

    assert app_state_paths.manifest_path(root) == root / ".aiwiki" / "state" / "manifest.json"
    assert app_state_paths.agent_pack_path(root, "Ops Reviewer") == root / "output" / "agents" / "ops-reviewer.md"
    assert app_state_paths.run_notes_path(root, "run 42") == root / "output" / "control" / "runs" / "run-42" / "thinking.md"
    assert (
        app_state_paths.archive_dry_run_path(root, "entry 42")
        == root / "output" / "control" / "execution-bundles" / "archive-entry-42-dry-run.json"
    )
    assert app_state_paths.material_archive_action_id("entry 42") == "archive-entry 42"
