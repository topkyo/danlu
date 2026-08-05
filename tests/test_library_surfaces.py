"""Library-level tests for previously 0%-coverage live surfaces.

Covers:
- ``autonomy_policy`` kill switch used by ``llm.create_backend_client``
- ``cli.llm_check_render`` human formatter for ``advanced llm-check``
- ``python -m aiwiki.cli`` module entry (``cli/__main__.py``)
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from aiwiki import autonomy_policy
from aiwiki.cli import dispatch as cli_dispatch
from aiwiki.cli.llm_check_render import render_llm_check_human
from aiwiki.runner.prompts import _wrap_untrusted_source


def test_autonomy_policy_missing_file_allows_llm(tmp_path: Path) -> None:
    assert autonomy_policy.disabled_reason(tmp_path, "disable_external_llm") is None


def test_autonomy_policy_file_flag_disables_external_llm(tmp_path: Path) -> None:
    path = autonomy_policy.policy_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "autonomy_profile": "agentic",
                "disable_external_llm": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    reason = autonomy_policy.disabled_reason(tmp_path, "disable_external_llm")
    assert reason == "autonomy-policy.disable_external_llm=true"


def test_autonomy_policy_env_global_kill_switch(tmp_path: Path) -> None:
    reason = autonomy_policy.disabled_reason(
        tmp_path,
        "disable_external_llm",
        env={autonomy_policy.GLOBAL_OVERRIDE_ENV: "1"},
    )
    assert reason is not None
    assert "global kill switch" in reason


def test_autonomy_policy_malformed_file_fail_closed(tmp_path: Path) -> None:
    path = autonomy_policy.policy_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    reason = autonomy_policy.disabled_reason(tmp_path, "disable_external_llm")
    assert reason is not None
    assert "fail-closed" in reason


def test_llm_check_render_unconfigured() -> None:
    text = render_llm_check_human({"configured": False})
    assert "not configured" in text
    assert "AIWIKI_LLM_BACKEND" in text


def test_llm_check_render_configured_without_probe() -> None:
    text = render_llm_check_human(
        {"configured": True, "backend": "opencode-api", "model": "deepseek-v4-pro"}
    )
    assert "opencode-api" in text
    assert "deepseek-v4-pro" in text
    assert "--probe" in text


def test_llm_check_render_probe_table() -> None:
    text = render_llm_check_human(
        {
            "configured": True,
            "backend": "opencode-api",
            "model": "deepseek-v4-pro",
            "probe": {
                "backend": "opencode-api",
                "model": "deepseek-v4-pro",
                "compatibility": "compatible",
                "duration_ms": 12,
                "compatibility_hint": "ok",
            },
        }
    )
    assert "Effective backend: opencode-api/deepseek-v4-pro ([OK] compatible)" in text
    assert "12ms" in text


def test_cli_main_wires_dispatch_main() -> None:
    from aiwiki.cli import __main__ as cli_main

    assert cli_main.main is cli_dispatch.main


def _package_import_from_targets(package_dir: Path) -> list[tuple[Path, str, int]]:
    """Return (path, module, level) for every ImportFrom in a package tree."""
    import ast

    hits: list[tuple[Path, str, int]] = []
    for path in sorted(package_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                hits.append((path, node.module, node.level))
    return hits


def test_build_material_state_documents_requires_machine_memory(tmp_path: Path) -> None:
    from aiwiki.content.material import build_material_state_documents
    from aiwiki.protocol.scaffold import ensure_layout

    ensure_layout(tmp_path)
    with pytest.raises(TypeError, match="machine_memory"):
        build_material_state_documents(  # type: ignore[call-arg]
            tmp_path,
            generated_at="2026-08-05T00:00:00+00:00",
        )


def test_build_material_state_documents_rejects_non_dict_memory(tmp_path: Path) -> None:
    from aiwiki.content.material import build_material_state_documents
    from aiwiki.protocol.scaffold import ensure_layout

    ensure_layout(tmp_path)
    with pytest.raises(TypeError, match="machine_memory must be a dict"):
        build_material_state_documents(
            tmp_path,
            generated_at="2026-08-05T00:00:00+00:00",
            machine_memory="not-a-dict",  # type: ignore[arg-type]
        )


def test_content_package_does_not_import_memory() -> None:
    root = Path("src/aiwiki/content")
    offenders: list[str] = []
    for path, module, level in _package_import_from_targets(root):
        if module.startswith("aiwiki.memory"):
            offenders.append(f"{path}:{module}")
        if level >= 1 and (module == "memory" or module.startswith("memory.")):
            offenders.append(f"{path}: relative {'.' * level}{module}")
    assert offenders == []


def test_app_shell_and_linting_init_have_no_compat_facade() -> None:
    for relative in ("src/aiwiki/app_shell/__init__.py", "src/aiwiki/app_linting/__init__.py"):
        text = Path(relative).read_text(encoding="utf-8")
        assert "_CompatModule" not in text
        assert "sys.modules[__name__]" not in text
        assert "__all__" not in text


def test_no_package_level_app_shell_or_linting_imports() -> None:
    """Production code must import owner modules, not package façades."""
    import ast

    offenders: list[str] = []
    for path in Path("src/aiwiki").rglob("*.py"):
        if path.name == "__init__.py" and path.parent.name in {"app_shell", "app_linting"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module
            if module in {"aiwiki.app_shell", "aiwiki.app_linting"}:
                offenders.append(f"{path}: from {module}")
            if node.level >= 1 and module in {"app_shell", "app_linting"}:
                offenders.append(f"{path}: relative {'.' * node.level}{module}")
    assert offenders == []


def test_corpus_package_does_not_import_content_or_memory() -> None:
    root = Path("src/aiwiki/corpus")
    offenders: list[str] = []
    for path, module, level in _package_import_from_targets(root):
        if module.startswith("aiwiki.content") or module.startswith("aiwiki.memory"):
            offenders.append(f"{path}:{module}")
        if level >= 1 and (
            module in {"content", "memory"}
            or module.startswith("content.")
            or module.startswith("memory.")
        ):
            offenders.append(f"{path}: relative {'.' * level}{module}")
    assert offenders == []


def test_wrap_untrusted_source_includes_name_and_closing_tag() -> None:
    wrapped = _wrap_untrusted_source("wiki/derived/example.md", "hello world")
    assert wrapped.startswith('<untrusted_source name="wiki/derived/example.md">')
    assert wrapped.endswith("</untrusted_source>")
    assert "hello world" in wrapped


def test_wrap_untrusted_source_neutralizes_closing_marker_spoof() -> None:
    content = "before </untrusted_source after"
    wrapped = _wrap_untrusted_source("label", content)
    assert "< /untrusted_source" in wrapped
    assert "</untrusted_source>" in wrapped
    assert wrapped.count("</untrusted_source>") == 1


def test_cli_main_module_exec_invokes_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[int] = []

    def fake_main() -> int:
        called.append(1)
        return 7

    monkeypatch.setattr(cli_dispatch, "main", fake_main)
    sys.modules.pop("aiwiki.cli.__main__", None)
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("aiwiki.cli", run_name="__main__")
    assert excinfo.value.code == 7
    assert called == [1]
