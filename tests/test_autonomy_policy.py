from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aiwiki import autonomy_policy
from aiwiki.autonomy_policy import (
    GLOBAL_OVERRIDE_ENV,
    AutonomyPolicy,
    disabled_reason,
    is_disabled,
    load_policy,
)


class AutonomyPolicyTests(unittest.TestCase):
    def test_missing_file_returns_default_all_false(self) -> None:
        with TemporaryDirectory() as tempdir:
            policy = load_policy(Path(tempdir))
            self.assertEqual(policy, AutonomyPolicy())
            self.assertFalse(policy.disable_external_llm)

    def test_file_with_explicit_flag_is_respected(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"schema_version": 1, "disable_external_llm": True}),
                encoding="utf-8",
            )
            policy = load_policy(root)
            self.assertTrue(policy.disable_external_llm)
            self.assertFalse(policy.disable_lane_apply)

    def test_malformed_file_falls_back_to_default(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not-json{", encoding="utf-8")
            policy = load_policy(root)
            self.assertEqual(policy, AutonomyPolicy())

    def test_non_dict_top_level_falls_back_to_default(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
            self.assertEqual(load_policy(root), AutonomyPolicy())

    def test_is_disabled_returns_false_for_unknown_flag(self) -> None:
        with TemporaryDirectory() as tempdir:
            self.assertFalse(is_disabled(Path(tempdir), "no_such_flag"))

    def test_global_env_override_disables_all_known_flags(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            env = {GLOBAL_OVERRIDE_ENV: "1"}
            for flag in autonomy_policy.KNOWN_FLAGS:
                self.assertTrue(is_disabled(root, flag, env=env))

    def test_global_env_override_only_active_when_value_is_one(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            for value in ("", "0", "true", "yes"):
                env = {GLOBAL_OVERRIDE_ENV: value}
                self.assertFalse(is_disabled(root, "disable_external_llm", env=env))

    def test_disabled_reason_distinguishes_env_vs_file(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            # via env
            reason = disabled_reason(root, "disable_external_llm", env={GLOBAL_OVERRIDE_ENV: "1"})
            self.assertIsNotNone(reason)
            assert reason is not None
            self.assertIn(GLOBAL_OVERRIDE_ENV, reason)
            # via file
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"disable_external_llm": True}), encoding="utf-8")
            reason_file = disabled_reason(root, "disable_external_llm", env={})
            self.assertIsNotNone(reason_file)
            assert reason_file is not None
            self.assertIn("disable_external_llm", reason_file)
            # not disabled
            self.assertIsNone(disabled_reason(root, "disable_lane_apply", env={}))

    def test_create_backend_client_raises_autonomy_disabled_when_set(self) -> None:
        # Hook integration: M7.4a wires only external LLM. When policy disables
        # it, create_backend_client must raise AutonomyDisabled (subclass of
        # LLMError) BEFORE constructing any backend client.
        from aiwiki.config import LLMConfig
        from aiwiki.llm import AutonomyDisabled, LLMError, create_backend_client

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"disable_external_llm": True}), encoding="utf-8")
            cfg = LLMConfig(backend="openai-api", model="gpt-test", base_url="http://x", api_key="k")
            with self.assertRaises(AutonomyDisabled) as ctx:
                create_backend_client(cfg, root)
            # AutonomyDisabled IS an LLMError so existing catch-LLMError caller
            # paths handle it cleanly.
            self.assertIsInstance(ctx.exception, LLMError)
            self.assertIn("disable_external_llm", str(ctx.exception))

    def test_create_backend_client_default_path_unchanged_when_policy_missing(self) -> None:
        from aiwiki.config import LLMConfig
        from aiwiki.llm import create_backend_client

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            # No policy file. Must NOT raise. Constructs an OpenAI compat client.
            cfg = LLMConfig(backend="openai-api", model="gpt-test", base_url="http://x", api_key="k")
            client = create_backend_client(cfg, root)
            self.assertIsNotNone(client)

    def test_run_alchemy_lane_apply_returns_skipped_when_disabled(self) -> None:
        # M7.4b1: lane apply hook. disabled policy → skipped dict, no side effects.
        from aiwiki.runner.alchemy import run_alchemy_lane_apply

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"disable_lane_apply": True}), encoding="utf-8")

            result = run_alchemy_lane_apply(
                root,
                lane="general",
                scope="raw",
                action_ids=["dummy-id"],
            )
            self.assertEqual(result.get("status"), "skipped")
            self.assertEqual(result.get("flag"), "disable_lane_apply")
            self.assertIn("disable_lane_apply", result.get("reason", ""))
            # No side effects: no .aiwiki/state lane history written.
            history_files = list(root.rglob("*lane*history*"))
            self.assertEqual(history_files, [])

    def test_run_alchemy_lane_apply_normal_path_unchanged_without_policy(self) -> None:
        # Without policy file, hook must be transparent: existing ValueError
        # for missing action-id / primitive still raised.
        from aiwiki.runner.alchemy import run_alchemy_lane_apply

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            with self.assertRaises(ValueError):
                run_alchemy_lane_apply(root, lane="general", scope="raw")

    def test_run_alchemy_propose_apply_returns_skipped_when_disabled(self) -> None:
        # M7.4b2: alchemy auto (propose+apply) hook. disabled → skipped dict,
        # no propose preview / apply / receipts.
        from aiwiki.runner.alchemy import run_alchemy_propose_apply

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"disable_alchemy_auto": True}), encoding="utf-8")

            result = run_alchemy_propose_apply(root, scope="raw")
            self.assertEqual(result.get("status"), "skipped")
            self.assertEqual(result.get("flag"), "disable_alchemy_auto")
            self.assertIn("disable_alchemy_auto", result.get("reason", ""))
            self.assertEqual(result.get("scope"), "raw")

    def test_create_l3_proposal_returns_skipped_when_disabled(self) -> None:
        # M7.4b3: l3 generate hook. disabled → skipped dict, no proposal write
        # and no FileNotFoundError despite missing target (hook fires first).
        from aiwiki.execution.l3_proposals import create_l3_proposal

        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            path = autonomy_policy.policy_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"disable_l3_generate": True}), encoding="utf-8")

            # Even with bogus target_file, hook short-circuits before any
            # validation / write. This is a feature: kill switch wins.
            result = create_l3_proposal(
                root,
                kind="rewrite",
                target_file="does-not-exist.md",
                content="ignored",
            )
            self.assertEqual(result.get("status"), "skipped")
            self.assertEqual(result.get("flag"), "disable_l3_generate")
            self.assertIn("disable_l3_generate", result.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
