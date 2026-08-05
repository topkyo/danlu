"""Library-level tests for elixir promote → revert lifecycle.

Covers ``aiwiki.execution.alchemy.promote_elixir`` / ``revert_elixir`` and
receipt anchoring without running the full distill chain or touching acceptance
golden fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiwiki.content.material import save_active_corpora_state
from aiwiki.execution.alchemy import promote_elixir, revert_elixir
from aiwiki.execution.alchemy_helpers import (
    CANDIDATE_ELIXIR_DIR,
    ELIXIR_DIR,
    _candidate_path,
    _parse_elixir_frontmatter,
    _settled_path,
)
from aiwiki.execution.candidates import save_output_candidates_state
from aiwiki.execution.history import load_jsonl_documents_strict
from aiwiki.execution.paths import execution_receipt_history_path
from aiwiki.execution.receipts import find_latest_elixir_promotion_receipt
from aiwiki.protocol.scaffold import ensure_layout

ELIXIR_ID = "elixir-revert-test"
CORPUS_ID = "corpus-revert-test"
DERIVED_REF = "wiki/derived/derived-revert-test.md"
NOW = "2026-08-05T08:00:00+00:00"


def _write_page(root: Path, relative: str, frontmatter: dict[str, object], body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f'  - "{item}"' if isinstance(item, str) else f"  - {item}" for item in value)
        elif isinstance(value, str):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_body() -> str:
    return "\n".join(
        [
            "# Elixir",
            "",
            "## Thesis",
            "- Minimal candidate body for revert test.",
            "",
            "## Counter Evidence",
            "- Sample counter-evidence item for promote gate.",
            "",
            "## Evidence",
            "- Supporting evidence line.",
        ]
    )


def _candidate_frontmatter() -> dict[str, object]:
    return {
        "kind": "elixir",
        "elixir_id": ELIXIR_ID,
        "elixir_state": "candidate",
        "protocol": "general",
        "iteration": 1,
        "provenance_corpus": CORPUS_ID,
        "derived_from": [DERIVED_REF],
        "topic": "Revert test topic",
        "confidence_level": "medium",
        "created_at": NOW,
        "updated_at": NOW,
        "distill_history_json": "[]",
        "review_after": "2026-11-05",
    }


def _seed_promote_vault(root: Path) -> None:
    ensure_layout(root)
    _write_page(
        root,
        DERIVED_REF,
        {"id": "derived-revert-test", "kind": "derived"},
        "# Derived\n\nSeed derived page for revert test.",
    )
    save_active_corpora_state(
        root,
        {
            "version": 1,
            "corpora": [
                {
                    "corpus_id": CORPUS_ID,
                    "protocol": "general",
                    "output_refs": [DERIVED_REF],
                }
            ],
        },
    )
    save_output_candidates_state(
        root,
        {
            "version": 1,
            "candidates": [
                {
                    "artifact_ref": "output/reports/revert-test.md",
                    "corpus_id": CORPUS_ID,
                    "candidate_state": "promoted",
                    "promoted_to": DERIVED_REF,
                    "question": "Revert test?",
                    "created_at": NOW,
                    "updated_at": NOW,
                    "format": "markdown",
                    "protocol": "general",
                }
            ],
        },
    )
    _write_page(root, f"{CANDIDATE_ELIXIR_DIR}/{ELIXIR_ID}.md", _candidate_frontmatter(), _candidate_body())


def _latest_revert_receipt(root: Path) -> dict[str, object]:
    history = load_jsonl_documents_strict(execution_receipt_history_path(root))
    matches = [
        entry
        for entry in history
        if entry.get("operation") == "revert"
        and entry.get("subject_kind") == "elixir_revert"
        and entry.get("subject_id") == ELIXIR_ID
    ]
    assert matches, "expected revert receipt in execution-receipts.jsonl"
    return matches[-1]


class TestRevertElixir:
    def test_promote_then_revert_restores_candidate_and_writes_receipt(self, tmp_path: Path) -> None:
        _seed_promote_vault(tmp_path)

        promote_result = promote_elixir(tmp_path, elixir_id=ELIXIR_ID, note="unit promote")
        settled_path = _settled_path(tmp_path, ELIXIR_ID)
        candidate_path = _candidate_path(tmp_path, ELIXIR_ID)

        assert promote_result["elixir_state"] == "settled"
        assert settled_path.is_file()
        assert _parse_elixir_frontmatter(settled_path)["elixir_state"] == "settled"
        assert _parse_elixir_frontmatter(candidate_path)["elixir_state"] == "superseded"

        promotion_receipt = find_latest_elixir_promotion_receipt(tmp_path, elixir_id=ELIXIR_ID)
        assert promotion_receipt is not None
        assert promotion_receipt.get("action_id")

        reverted_path = revert_elixir(tmp_path, elixir_id=ELIXIR_ID, note="unit revert")

        assert reverted_path == candidate_path
        assert not settled_path.exists()
        assert candidate_path.is_file()
        assert _parse_elixir_frontmatter(candidate_path)["elixir_state"] == "candidate"
        assert "superseded_by" not in _parse_elixir_frontmatter(candidate_path)
        assert "promoted_at" not in _parse_elixir_frontmatter(candidate_path)

        revert_receipt = _latest_revert_receipt(tmp_path)
        receipt_file = tmp_path / str(revert_receipt["receipt_path"])
        assert receipt_file.is_file()
        bundle = revert_receipt.get("bundle")
        assert isinstance(bundle, dict)
        assert bundle.get("source_receipt_action_id") == promotion_receipt.get("action_id")
        assert bundle.get("source_receipt_applied_at") == promotion_receipt.get("applied_at")
        assert bundle.get("to_state") == "candidate"
        assert bundle.get("from_state") == "settled"

        on_disk = json.loads(receipt_file.read_text(encoding="utf-8"))
        on_disk_bundle = on_disk.get("bundle")
        assert isinstance(on_disk_bundle, dict)
        assert on_disk_bundle.get("source_receipt_action_id") == promotion_receipt.get("action_id")

    def test_revert_raises_when_promotion_receipt_missing(self, tmp_path: Path) -> None:
        ensure_layout(tmp_path)
        settled_frontmatter = dict(_candidate_frontmatter())
        settled_frontmatter["elixir_state"] = "settled"
        settled_frontmatter["promoted_at"] = NOW
        _write_page(tmp_path, f"{ELIXIR_DIR}/{ELIXIR_ID}.md", settled_frontmatter, _candidate_body())

        with pytest.raises(ValueError, match="promotion_receipt_missing"):
            revert_elixir(tmp_path, elixir_id=ELIXIR_ID)
