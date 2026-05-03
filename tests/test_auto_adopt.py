"""Focused tests for nightly auto-adopt (L1 / L2 governance backlog)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.runner.auto_adopt import _env_flag


class AutoAdoptEnvFlagTests(unittest.TestCase):
    def test_env_flag_true_values(self) -> None:
        for value in ("1", "true", "yes", "on", "TRUE", "Yes"):
            with patch.dict(os.environ, {"AIWIKI_TEST_FLAG": value}):
                self.assertTrue(_env_flag("AIWIKI_TEST_FLAG"), f"env_flag returned False for {value!r}")

    def test_env_flag_false_values(self) -> None:
        for value in ("0", "false", "no", "", "off"):
            with patch.dict(os.environ, {"AIWIKI_TEST_FLAG": value}):
                self.assertFalse(_env_flag("AIWIKI_TEST_FLAG"), f"env_flag returned True for {value!r}")

    def test_env_flag_missing_defaults_to_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_env_flag("AIWIKI_NONEXISTENT_KEY"))
