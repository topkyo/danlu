"""Round 43 / Stage B + D — batch-review alias and review-next interactive surface."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import save_machine_memory_action_state
from aiwiki.cli import main


class _CliCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tempdir.name).resolve()

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _run_main(self, argv: list[str], *, stdin_text: str | None = None) -> tuple[int, dict, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        ctx = []
        ctx.append(patch("sys.stdout", new=stdout))
        ctx.append(patch("sys.stderr", new=stderr))
        if stdin_text is not None:
            ctx.append(patch("sys.stdin", new=io.StringIO(stdin_text)))
            ctx.append(patch("builtins.input", side_effect=stdin_text.splitlines()))
        for c in ctx:
            c.start()
        try:
            code = main(["--root", str(self.root), *argv])
        finally:
            for c in reversed(ctx):
                c.stop()
        text = stdout.getvalue()
        try:
            payload = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError:
            tail = text.rfind("{")
            payload = {}
            if tail >= 0:
                try:
                    payload = json.loads(text[tail:])
                except json.JSONDecodeError:
                    payload = {}
        return code, payload, stderr.getvalue()


class BatchReviewAliasTests(_CliCase):
    def test_batch_review_requires_note(self) -> None:
        with self.assertRaises(SystemExit):
            self._run_main(["batch-review", "pages"])

    def test_batch_review_pages_routes_to_pages_batch(self) -> None:
        with patch(
            "aiwiki.cli._resolve_review_pages",
            return_value=["wiki/judgments/a.md", "wiki/judgments/b.md"],
        ), patch(
            "aiwiki.cli.review_pages_batch",
            return_value={"operation": "review-page-batch", "count": 2},
        ) as mocked:
            code, payload, stderr = self._run_main(
                ["batch-review", "pages", "--note", "round 43 batch"]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["triggered_by"], "batch-alias")
        self.assertEqual(payload["alias_target"], "pages")
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], self.root)
        self.assertEqual(args[1], ["wiki/judgments/a.md", "wiki/judgments/b.md"])
        self.assertEqual(args[2], "tracking")
        self.assertEqual(kwargs["note"], "[batch-alias] round 43 batch")

    def test_batch_review_action_requires_kind(self) -> None:
        ensure_layout(self.root)
        with self.assertRaises(SystemExit) as ctx:
            self._run_main(["batch-review", "action", "--note", "n"])
        self.assertEqual(ctx.exception.code, 1)

    def test_batch_review_action_filters_kind_and_review_first(self) -> None:
        ensure_layout(self.root)
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "link-a",
                        "kind": "add-source-concept-link",
                        "active": True,
                        "status": "proposed",
                        "policy_decision": "review",
                        "execution_band": "review-first",
                    },
                    {
                        "id": "link-b",
                        "kind": "add-source-concept-link",
                        "active": True,
                        "status": "proposed",
                        "policy_decision": "review",
                        "execution_band": "review-first",
                    },
                    {
                        "id": "bridge-a",
                        "kind": "monitor-bridge-concept",
                        "active": True,
                        "status": "proposed",
                        "policy_decision": "review",
                        "execution_band": "review-first",
                    },
                ],
            },
        )
        with patch(
            "aiwiki.cli.review_machine_memory_actions_batch",
            return_value={"operation": "action-review-batch", "count": 2},
        ) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "batch-review",
                    "action",
                    "--kind",
                    "add-source-concept-link",
                    "--note",
                    "ack the link batch",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["triggered_by"], "batch-alias")
        self.assertEqual(payload["alias_target"], "action")
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertEqual(set(args[1]), {"link-a", "link-b"})
        self.assertEqual(args[2], "accepted")
        self.assertEqual(kwargs["note"], "[batch-alias] ack the link batch")

    def test_batch_review_apply_low_risk_routes_to_apply_batch(self) -> None:
        with patch(
            "aiwiki.cli._resolve_action_ids",
            return_value=["a-1", "a-2"],
        ), patch(
            "aiwiki.cli.apply_machine_memory_actions_batch",
            return_value={"operation": "apply-action-batch", "count": 2, "dry_run": True},
        ) as mocked:
            code, payload, stderr = self._run_main(
                [
                    "batch-review",
                    "apply-low-risk",
                    "--note",
                    "preview",
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertTrue(payload.get("dry_run"))
        self.assertEqual(payload["triggered_by"], "batch-alias")
        self.assertEqual(payload["alias_target"], "apply-low-risk")
        mocked.assert_called_once()
        _args, kwargs = mocked.call_args
        self.assertEqual(kwargs["note"], "[batch-alias] preview")
        self.assertTrue(kwargs["dry_run"])


class ReviewNextTests(_CliCase):
    def _shell_summary_with(self, pages: list[dict]) -> dict:
        return {
            "review_controls": {"pages": pages},
        }

    def test_review_next_non_interactive_surfaces_without_writing(self) -> None:
        pages = [
            {
                "path": "wiki/judgments/a.md",
                "kind": "judgment",
                "title": "Judgment A",
                "default_transition": "tracking",
                "allowed_transitions": ["tracking", "rejected"],
                "reasons": ["missing-invalidation"],
                "can_review": True,
            },
            {
                "path": "wiki/judgments/b.md",
                "kind": "judgment",
                "title": "Judgment B",
                "default_transition": "tracking",
                "allowed_transitions": ["tracking", "rejected"],
                "reasons": ["counter-evidence-candidate"],
                "can_review": True,
            },
        ]
        with patch(
            "aiwiki.cli.build_shell_summary",
            return_value=self._shell_summary_with(pages),
        ), patch(
            "aiwiki.cli.review_page",
            side_effect=AssertionError("review_page must not be called in --non-interactive"),
        ):
            code, payload, stderr = self._run_main(
                ["review-next", "--limit", "2", "--non-interactive"]
            )
        self.assertEqual(code, 0, msg=stderr)
        self.assertEqual(payload["operation"], "review-next")
        self.assertTrue(payload["non_interactive"])
        self.assertEqual(payload["surfaced_count"], 2)
        self.assertEqual(payload["decisions"], [])

    def test_review_next_interactive_writes_decisions(self) -> None:
        pages = [
            {
                "path": "wiki/judgments/a.md",
                "kind": "judgment",
                "title": "Judgment A",
                "default_transition": "tracking",
                "allowed_transitions": ["tracking", "rejected"],
                "reasons": ["missing-invalidation"],
                "can_review": True,
            }
        ]

        captured = {}

        def fake_review_page(root, path, status, *, note=None, confidence=None):
            captured["call"] = {"root": root, "path": path, "status": status, "note": note}
            return {"path": path, "status": status, "note": note}

        with patch(
            "aiwiki.cli.build_shell_summary",
            return_value=self._shell_summary_with(pages),
        ), patch("aiwiki.cli.review_page", side_effect=fake_review_page):
            code, payload, stderr = self._run_main(
                ["review-next", "--limit", "1", "--note", "ack"],
                stdin_text="a\n",
            )
        self.assertEqual(code, 0, msg=stderr)
        self.assertEqual(payload["surfaced_count"], 1)
        self.assertEqual(len(payload["decisions"]), 1)
        decision = payload["decisions"][0]
        self.assertEqual(decision["status"], "accepted")
        self.assertEqual(decision["receipt"]["status"], "accepted")
        self.assertEqual(decision["receipt"]["triggered_by"], "review-next")
        self.assertEqual(captured["call"]["status"], "accepted")
        self.assertEqual(captured["call"]["note"], "[review-next] ack")

    def test_review_next_quit_choice_stops_loop(self) -> None:
        pages = [
            {
                "path": f"wiki/judgments/p{i}.md",
                "kind": "judgment",
                "title": f"P{i}",
                "default_transition": "tracking",
                "allowed_transitions": ["tracking"],
                "reasons": [],
                "can_review": True,
            }
            for i in range(3)
        ]

        with patch(
            "aiwiki.cli.build_shell_summary",
            return_value=self._shell_summary_with(pages),
        ), patch(
            "aiwiki.cli.review_page",
            side_effect=AssertionError("review_page must not be called when quitting on first prompt"),
        ):
            code, payload, stderr = self._run_main(
                ["review-next", "--limit", "3"],
                stdin_text="q\n",
            )
        self.assertEqual(code, 0, msg=stderr)
        self.assertEqual(payload["surfaced_count"], 1, "quit on first prompt: only first item should be surfaced")
        self.assertEqual(payload["decisions"], [])


if __name__ == "__main__":
    unittest.main()
