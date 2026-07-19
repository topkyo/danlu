"""Contract tests for operator-facing command hint strings."""

from __future__ import annotations

from aiwiki.app_shell.helpers import _build_llm_rerun_command
from aiwiki.render.views import furnace_quick_commands


def test_furnace_quick_commands_use_advanced_surface_without_protocol() -> None:
    cmds = furnace_quick_commands("general", [], [])
    assert cmds
    assert all("--protocol" not in cmd for cmd in cmds)
    assert all("advanced" in cmd for cmd in cmds)


def test_build_llm_rerun_command_uses_advanced_surface_without_protocol() -> None:
    cmd = _build_llm_rerun_command(
        {"event": "run-ask", "question": "hi", "format": "report", "protocol": "general"}
    )
    assert cmd
    assert "--protocol" not in cmd
    assert "advanced" in cmd
    assert "advanced run-ask" in cmd
