from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.cli import main
from aiwiki.cli.llm_check_render import render_llm_check_human


class LLMCheckRenderTests(unittest.TestCase):
    def test_render_human_not_configured(self) -> None:
        out = render_llm_check_human({"configured": False})
        self.assertIn("not configured", out)
        self.assertIn("AIWIKI_LLM_BACKEND", out)

    def test_render_human_configured_no_probe(self) -> None:
        out = render_llm_check_human({"configured": True, "backend": "codex-cli", "model": "gpt-5.5"})
        self.assertIn("codex-cli", out)
        self.assertIn("gpt-5.5", out)
        self.assertIn("--probe", out)

    def test_render_human_compatible(self) -> None:
        result = {
            "configured": True,
            "backend": "codex-cli",
            "model": "gpt-5.5",
            "probe": {
                "backend": "codex-cli",
                "model": "gpt-5.5",
                "compatibility": "compatible",
                "compatibility_hint": "",
                "raw_response_path": "/tmp/abc.txt",
                "duration_ms": 10800,
            },
            "probes": [],
        }
        out = render_llm_check_human(result)
        self.assertIn("Effective backend: codex-cli/gpt-5.5", out)
        self.assertIn("[OK] compatible", out)
        self.assertIn("10.8s", out)
        self.assertIn("raw_response[codex-cli]: /tmp/abc.txt", out)

    def test_render_human_four_states(self) -> None:
        result = _four_state_result()
        out = render_llm_check_human(result)
        self.assertIn("[OK] compatible", out)
        self.assertIn("[!]  degraded", out)
        self.assertIn("[X]  unavailable", out)
        self.assertIn("[?]  requires_credential", out)
        self.assertIn("raw_response[copilot-cli]: /tmp/c.txt", out)
        self.assertIn("raw_response[claude-cli]: /tmp/d.txt", out)
        self.assertNotIn("raw_response[nvidia-nim-api]", out)

    def test_render_human_truncates_long_hint(self) -> None:
        long_hint = "x" * 100
        result = {
            "configured": True,
            "backend": "codex-cli",
            "model": "gpt-5.5",
            "probe": {
                "backend": "codex-cli",
                "model": "gpt-5.5",
                "compatibility": "degraded",
                "compatibility_hint": long_hint,
                "raw_response_path": "",
                "duration_ms": 1000,
            },
            "probes": [],
        }
        out = render_llm_check_human(result)
        self.assertIn("…", out)
        self.assertNotIn(long_hint, out)

    def test_render_human_empty_hint_renders_dash(self) -> None:
        result = {
            "configured": True,
            "backend": "codex-cli",
            "model": "gpt-5.5",
            "probe": {
                "backend": "codex-cli",
                "model": "gpt-5.5",
                "compatibility": "compatible",
                "compatibility_hint": "",
                "raw_response_path": "",
                "duration_ms": None,
            },
            "probes": [],
        }
        out = render_llm_check_human(result)
        self.assertTrue(" - " in out or out.count("-") >= 5)

    def test_render_human_unknown_effective_backend(self) -> None:
        result = {
            "configured": True,
            "backend": "missing-cli",
            "model": "gpt-5.5",
            "probe": None,
            "probes": [
                {
                    "backend": "codex-cli",
                    "model": "gpt-5.5",
                    "compatibility": "compatible",
                    "compatibility_hint": "",
                    "raw_response_path": "",
                    "duration_ms": 10,
                }
            ],
        }
        out = render_llm_check_human(result)
        self.assertIn("Effective backend: missing-cli/gpt-5.5 (unknown)", out)

    def test_render_human_unknown_status_and_non_int_duration(self) -> None:
        result = {
            "configured": True,
            "backend": "codex-cli",
            "model": "gpt-5.5",
            "probe": {
                "backend": "codex-cli",
                "model": "gpt-5.5",
                "compatibility": "mystery",
                "compatibility_hint": "short hint",
                "raw_response_path": "",
                "duration_ms": "12",
            },
            "probes": [],
        }
        out = render_llm_check_human(result)
        self.assertIn("[??] unknown", out)
        self.assertIn("short hint", out)

    def test_dispatch_json_format_matches_default_bytes(self) -> None:
        payload = {
            "backend": "codex-cli",
            "configured": True,
            "model": "gpt-5.5",
            "probe": {"backend": "codex-cli", "compatibility": "compatible", "duration_ms": 1},
        }

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir).resolve()
            with patch("aiwiki.cli.llm_probe", return_value=payload) as mocked_default:
                code_default, stdout_default, stderr_default = _run_main_raw(root, ["llm-check", "--probe"])
            with patch("aiwiki.cli.llm_probe", return_value=payload) as mocked_json:
                code_json, stdout_json, stderr_json = _run_main_raw(
                    root, ["llm-check", "--probe", "--format", "json"]
                )

        self.assertEqual(code_default, 0)
        self.assertEqual(code_json, 0)
        self.assertEqual(stderr_default, "")
        self.assertEqual(stderr_json, "")
        self.assertEqual(stdout_default, stdout_json)
        mocked_default.assert_called_once_with(root, probe_all=False, timeout_seconds=20)
        mocked_json.assert_called_once_with(root, probe_all=False, timeout_seconds=20)


def _four_state_result() -> dict[str, object]:
    return {
        "configured": True,
        "backend": "codex-cli",
        "model": "gpt-5.5",
        "probe": {
            "backend": "codex-cli",
            "model": "gpt-5.5",
            "compatibility": "compatible",
            "compatibility_hint": "",
            "raw_response_path": "",
            "duration_ms": 1000,
        },
        "probes": [
            {
                "backend": "codex-cli",
                "model": "gpt-5.5",
                "compatibility": "compatible",
                "compatibility_hint": "",
                "raw_response_path": "",
                "duration_ms": 1000,
            },
            {
                "backend": "copilot-cli",
                "model": "gpt-5.5",
                "compatibility": "degraded",
                "compatibility_hint": "decoration prefix detected: ●",
                "raw_response_path": "/tmp/c.txt",
                "duration_ms": 14900,
            },
            {
                "backend": "claude-cli",
                "model": "gpt-5.5",
                "compatibility": "requires_credential",
                "compatibility_hint": "Your organization does not have access",
                "raw_response_path": "/tmp/d.txt",
                "duration_ms": 6300,
            },
            {
                "backend": "nvidia-nim-api",
                "model": "gpt-5.5",
                "compatibility": "unavailable",
                "compatibility_hint": "no API key configured",
                "raw_response_path": "",
                "duration_ms": None,
            },
        ],
    }


def _run_main_raw(root: Path, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
        code = main(["--root", str(root), *argv])
    return code, stdout.getvalue(), stderr.getvalue()
