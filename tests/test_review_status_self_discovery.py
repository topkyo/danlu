from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from aiwiki.cli import dispatch
from aiwiki.execution.concept_rewrite import review_concept_rewrite
from aiwiki.execution.machine_memory_actions import review_machine_memory_action
from aiwiki.execution.review import review_page


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


def test_review_page_invalid_status_lists_valid_values(tmp_path: Path) -> None:
    page = tmp_path / "wiki" / "decisions" / "test-decision.md"
    _write_page(page, kind="decision")

    with pytest.raises(ValueError) as exc:
        review_page(tmp_path, str(page), "__bogus__")

    message = str(exc.value)
    assert "expected one of" in message
    assert "approved" in message


def test_concept_rewrite_invalid_status_lists_valid_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        review_concept_rewrite(tmp_path, "test-concept", "__bogus__")

    message = str(exc.value)
    assert "expected one of" in message
    assert "accepted" in message


def test_machine_memory_action_invalid_status_lists_valid_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        review_machine_memory_action(tmp_path, "test-action", "__bogus__")

    message = str(exc.value)
    assert "expected one of" in message
    assert "resolved" in message


def test_l3_proposal_review_invalid_status_lists_valid_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    args = argparse.Namespace(
        root=tmp_path,
        model_fallback=None,
        command="review",
        handler_command="review",
        review_command="proposal",
        status="__bogus__",
        proposal_id="test-proposal",
        note=None,
    )

    class _Parser:
        def parse_args(self, argv: list[str] | None) -> argparse.Namespace:
            return args

        def exit(self, status: int = 0, message: str | None = None) -> None:
            raise ValueError(message or "")

    monkeypatch.setattr(dispatch, "build_parser", lambda: _Parser())

    with pytest.raises(ValueError) as exc:
        dispatch.main([])

    message = str(exc.value)
    assert "expected one of" in message
    assert "rejected" in message
