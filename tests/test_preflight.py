"""Tests for preflight backend check (P4-1c)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from aiwiki.runner.preflight import _is_truthy_env, preflight_check_backend


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


def test_truthy_env_recognizes_common_values() -> None:
    for v in ("1", "true", "True", "TRUE", "yes", "YES", "on", "  yes  "):
        assert _is_truthy_env(v) is True
    for v in ("", "0", "false", "no", "off", "maybe"):
        assert _is_truthy_env(v) is False


@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_compatible_silent(mock_probe, mock_config, root: Path, caplog: pytest.LogCaptureFixture) -> None:
    mock_probe.return_value = {
        "compatibility": "compatible",
        "backend": "codex-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "",
    }
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert caplog.text == ""


@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_degraded_warns(mock_probe, mock_config, root: Path, caplog: pytest.LogCaptureFixture) -> None:
    mock_probe.return_value = {
        "compatibility": "degraded",
        "backend": "copilot-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "decoration prefix detected: ●",
    }
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert "probe=degraded" in caplog.text
    assert "copilot-cli" in caplog.text
    assert "llm-check --probe-all --format human" in caplog.text


@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_unavailable_warns(mock_probe, mock_config, root: Path, caplog: pytest.LogCaptureFixture) -> None:
    mock_probe.return_value = {
        "compatibility": "unavailable",
        "backend": "claude-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "binary not found",
    }
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert "probe=unavailable" in caplog.text


@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_requires_credential_warns(mock_probe, mock_config, root: Path, caplog: pytest.LogCaptureFixture) -> None:
    mock_probe.return_value = {
        "compatibility": "requires_credential",
        "backend": "claude-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "no access",
    }
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert "probe=requires_credential" in caplog.text


@patch.dict("os.environ", {"AIWIKI_REQUIRE_COMPATIBLE_BACKEND": "1"})
@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_env_opt_in_blocks_degraded(mock_probe, mock_config, root: Path) -> None:
    mock_probe.return_value = {
        "compatibility": "degraded",
        "backend": "copilot-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "decoration",
    }
    with pytest.raises(RuntimeError, match="probe=degraded"):
        preflight_check_backend(root)


@patch.dict("os.environ", {"AIWIKI_REQUIRE_COMPATIBLE_BACKEND": "true"})
@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_env_opt_in_allows_compatible(
    mock_probe,
    mock_config,
    root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_probe.return_value = {
        "compatibility": "compatible",
        "backend": "codex-cli",
        "model": "gpt-5.5",
        "compatibility_hint": "",
    }
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert caplog.text == ""


@patch.dict("os.environ", {"AIWIKI_REQUIRE_COMPATIBLE_BACKEND": "1"})
@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_env_opt_in_blocks_unavailable(mock_probe, mock_config, root: Path) -> None:
    mock_probe.return_value = {
        "compatibility": "unavailable",
        "backend": "x",
        "model": "y",
        "compatibility_hint": "",
    }
    with pytest.raises(RuntimeError, match="probe=unavailable"):
        preflight_check_backend(root)


@patch("aiwiki.runner.preflight.LLMConfig")
@patch("aiwiki.runner.preflight.probe_backend", side_effect=RuntimeError("probe died"))
def test_preflight_fail_soft_on_probe_exception(
    mock_probe,
    mock_config,
    root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert "preflight probe failed" in caplog.text
    assert "probe died" in caplog.text


@patch("aiwiki.runner.preflight.LLMConfig.from_env", side_effect=RuntimeError("config died"))
@patch("aiwiki.runner.preflight.probe_backend")
def test_preflight_fail_soft_on_config_exception(
    mock_probe,
    mock_from_env,
    root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="aiwiki"):
        preflight_check_backend(root)
    assert "preflight probe failed" in caplog.text
