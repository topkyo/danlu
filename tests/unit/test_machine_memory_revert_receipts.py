from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import save_machine_memory_action_state
from aiwiki.compile.pipeline import compile_wiki
from aiwiki.execution.machine_memory_actions import apply_machine_memory_action, revert_machine_memory_action


def test_machine_memory_revert_keeps_apply_receipt_and_writes_revert_receipt(tmp_path):
    ensure_layout(tmp_path)
    sample = tmp_path / "sample.md"
    sample.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
    entry = ingest_source(tmp_path, str(sample), title="Transformer Scaling")
    compile_wiki(tmp_path)
    concept_slug = next(path.stem for path in sorted((tmp_path / "wiki" / "concepts").glob("*.md")))
    save_machine_memory_action_state(
        tmp_path,
        {
            "version": 1,
            "actions": [
                {
                    "id": "manual-link-action",
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
    dry_run = apply_machine_memory_action(tmp_path, "manual-link-action", dry_run=True)
    bundle_path = tmp_path / dry_run["bundle_path"]
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(dry_run["bundle"], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    apply_result = apply_machine_memory_action(
        tmp_path,
        "manual-link-action",
        note="Apply before revert test.",
        bundle_path=dry_run["bundle_path"],
    )
    apply_receipt_path = tmp_path / apply_result["receipt_path"]
    apply_receipt = json.loads(apply_receipt_path.read_text(encoding="utf-8"))
    assert apply_receipt["operation"] == "apply"

    revert_result = revert_machine_memory_action(tmp_path, "manual-link-action", note="Rollback this safe apply.")

    revert_receipt_path = tmp_path / revert_result["receipt_path"]
    assert apply_receipt_path.exists()
    assert revert_receipt_path.exists()
    assert apply_receipt_path.name == "manual-link-action.json"
    assert revert_receipt_path.relative_to(apply_receipt_path.parent).as_posix() == "reverts/manual-link-action.json"
    assert json.loads(apply_receipt_path.read_text(encoding="utf-8"))["operation"] == "apply"
    revert_receipt = json.loads(revert_receipt_path.read_text(encoding="utf-8"))
    assert revert_receipt["operation"] == "revert"
    assert revert_receipt["receipt_path"] == revert_result["receipt_path"]
    history = [
        json.loads(line)
        for line in (tmp_path / ".aiwiki/state/execution-receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [entry["operation"] for entry in history] == ["apply", "revert"]
