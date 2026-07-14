from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.runner.automation import auto_process_once


class _AutomationClient:
    config = type("Config", (), {"model": "stub-model", "backend": "opencode-api"})()


def _automation_state_path(root: Path) -> Path:
    return root / ".aiwiki" / "state" / "automation.json"


def test_auto_process_once_llm_compile_failure_is_fail_closed(tmp_path: Path) -> None:
    with patch("aiwiki.runner.automation.run_compile", side_effect=RuntimeError("compile boom")):
        with patch("aiwiki.runner.automation.compile_wiki") as deterministic_compile:
            with pytest.raises(RuntimeError, match="LLM compile failed during automation"):
                auto_process_once(tmp_path, client=_AutomationClient(), deterministic_only=False)

    deterministic_compile.assert_not_called()
    assert not _automation_state_path(tmp_path).exists()


def test_auto_process_once_llm_lint_failure_is_fail_closed(tmp_path: Path) -> None:
    with patch("aiwiki.runner.automation.run_compile", return_value={"compile": {}, "updated_pages": []}):
        with patch("aiwiki.runner.automation.run_lint", side_effect=RuntimeError("lint boom")):
            with patch("aiwiki.runner.automation.lint_wiki") as deterministic_lint:
                with pytest.raises(RuntimeError, match="LLM lint failed during automation"):
                    auto_process_once(tmp_path, client=_AutomationClient(), deterministic_only=False)

    deterministic_lint.assert_not_called()
    assert not _automation_state_path(tmp_path).exists()
