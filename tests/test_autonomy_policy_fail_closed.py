from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki import autonomy_policy
from aiwiki.autonomy_policy import (
    GLOBAL_OVERRIDE_ENV,
    AutonomyPolicy,
    disabled_reason,
    is_disabled,
    load_policy,
    policy_status,
    set_flag,
)


class TestAutonomyPolicyFailClosed(unittest.TestCase):
    def _write_policy(self, root: Path, content: str) -> Path:
        path = autonomy_policy.policy_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_file_returns_all_false_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            policy = load_policy(root)

            self.assertEqual(policy, AutonomyPolicy())
            self.assertIsNone(policy.load_error)
            for flag in autonomy_policy.KNOWN_FLAGS:
                self.assertFalse(getattr(policy, flag))
                self.assertFalse(is_disabled(root, flag, env={}))

    def test_malformed_json_returns_all_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, "{not json")

            policy = load_policy(root)

            self.assertIsNotNone(policy.load_error)
            self.assertIn("malformed", policy.load_error or "")
            for flag in autonomy_policy.KNOWN_FLAGS:
                self.assertTrue(getattr(policy, flag))
                self.assertTrue(is_disabled(root, flag, env={}))
            reason = disabled_reason(root, "disable_external_llm", env={})
            self.assertIsNotNone(reason)
            self.assertIn("fail-closed", reason or "")
            self.assertIn("malformed", reason or "")

    def test_unreadable_file_returns_all_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, json.dumps({"disable_external_llm": False}))

            with patch.object(Path, "read_text", side_effect=OSError("blocked read")):
                policy = load_policy(root)
                for flag in autonomy_policy.KNOWN_FLAGS:
                    self.assertTrue(getattr(policy, flag))
                    self.assertTrue(is_disabled(root, flag, env={}))
                reason = disabled_reason(root, "disable_external_llm", env={})

            self.assertIsNotNone(policy.load_error)
            self.assertIn("unreadable", policy.load_error or "")
            self.assertIn("fail-closed", reason or "")
            self.assertIn("unreadable", reason or "")

    def test_exists_oserror_returns_all_disabled(self) -> None:
        """If Path.exists() itself raises OSError, fail-closed with unreadable reason."""

        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)

            with patch.object(Path, "exists", side_effect=OSError("permission denied")):
                policy = load_policy(root)

            self.assertTrue(policy.disable_external_llm)
            self.assertTrue(policy.disable_lane_apply)
            self.assertTrue(policy.disable_alchemy_auto)
            self.assertTrue(policy.disable_l3_generate)
            self.assertIsNotNone(policy.load_error)
            self.assertIn("unreadable", policy.load_error or "")

    def test_non_dict_root_returns_all_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, "[]")

            policy = load_policy(root)

            self.assertEqual(policy.load_error, "autonomy-policy file not a JSON object")
            for flag in autonomy_policy.KNOWN_FLAGS:
                self.assertTrue(getattr(policy, flag))
                self.assertTrue(is_disabled(root, flag, env={}))

    def test_well_formed_partial_flags_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, json.dumps({"schema_version": 1, "disable_external_llm": True}))

            policy = load_policy(root)

            self.assertIsNone(policy.load_error)
            self.assertTrue(policy.disable_external_llm)
            self.assertFalse(policy.disable_lane_apply)
            self.assertFalse(policy.disable_alchemy_auto)
            self.assertFalse(policy.disable_l3_generate)

    def test_set_flag_on_corrupt_file_starts_from_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, "{not json")

            result = set_flag(root, "disable_external_llm", True)
            policy = load_policy(root)

            self.assertEqual(result, policy)
            self.assertIsNone(policy.load_error)
            self.assertTrue(policy.disable_external_llm)
            self.assertFalse(policy.disable_lane_apply)
            self.assertFalse(policy.disable_alchemy_auto)
            self.assertFalse(policy.disable_l3_generate)

    def test_policy_status_exposes_load_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, "{not json")

            status = policy_status(root, env={})

            self.assertTrue(status["policy_file_exists"])
            self.assertIsInstance(status["policy_load_error"], str)
            self.assertIn("malformed", status["policy_load_error"])
            for info in status["flags"].values():
                self.assertTrue(info["file_value"])
                self.assertTrue(info["effective"])
                self.assertIn("fail-closed", info["reason"] or "")

    def test_env_override_takes_precedence_over_load_error(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            self._write_policy(root, "{not json")

            reason = disabled_reason(root, "disable_external_llm", env={GLOBAL_OVERRIDE_ENV: "1"})

            self.assertEqual(reason, f"{GLOBAL_OVERRIDE_ENV}=1 (global kill switch active)")


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestAutonomyPolicyFailClosed))
    return suite


if __name__ == "__main__":
    unittest.main()
