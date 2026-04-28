from __future__ import annotations

from pathlib import Path

import pytest

from aiwiki.app_protocol import ensure_layout
from aiwiki.execution.ask import file_back
from aiwiki.execution.review import review_page


def _write_artifact(path: Path) -> None:
    path.write_text(
        "# Test artifact\n\n"
        "Provenance: wiki/sources/test-source.md\n\n"
        "Body.\n",
        encoding="utf-8",
    )


def _write_page(path: Path, *, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"kind: {kind}\n"
        "title: Test page\n"
        "---\n\n"
        "# Test page\n",
        encoding="utf-8",
    )


def test_file_back_derived_returns_hint(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact)

    result = file_back(tmp_path, str(artifact), kind="derived")

    assert "机器记忆终态层" in result["next_step_hint"]
    assert "file-back --kind judgment" in result["next_step_hint"]


def test_file_back_judgment_returns_review_hint(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact)

    result = file_back(tmp_path, str(artifact), kind="judgment")

    hint = result["next_step_hint"]
    assert hint.startswith("next: aiwiki review-page")
    assert "tentative" in hint
    assert result["path"] in hint


def test_file_back_decision_returns_review_hint(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    artifact = tmp_path / "artifact.md"
    _write_artifact(artifact)

    result = file_back(tmp_path, str(artifact), kind="decision")

    hint = result["next_step_hint"]
    assert "proposed" in hint
    assert "approved" in hint
    assert result["path"] in hint


def test_review_page_rejects_derived_with_actionable_error(tmp_path: Path) -> None:
    ensure_layout(tmp_path)
    page = tmp_path / "wiki" / "derived" / "test-derived.md"
    _write_page(page, kind="derived")

    with pytest.raises(ValueError) as exc:
        review_page(tmp_path, str(page), "tentative")

    message = str(exc.value)
    assert "machine-memory terminal layer" in message
    assert "file-back --kind judgment" in message
