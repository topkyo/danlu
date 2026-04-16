from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import (
    _load_latest_action_apply_batch_receipt,
    apply_concept_rewrite,
    apply_machine_memory_actions_batch,
    apply_material_archive,
    ask_question,
    compile_wiki,
    file_back,
    revert_machine_memory_action_batch,
    review_concept_rewrite,
    review_pages_batch,
    set_active_protocol,
)
from aiwiki.app_content import ingest_source
from aiwiki.app_protocol import ensure_layout, load_protocol_runtime_schema, save_manifest
from aiwiki.app_shell import shell_search, shell_status_dashboard
from aiwiki.app_state import (
    load_machine_memory,
    load_manifest,
    load_material_archive_state,
    save_machine_memory_action_state,
)
from aiwiki.cli import main as cli_main
from aiwiki.llm import CompletionResult
from aiwiki.runner import run_compile


class _StubClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.config = type("Config", (), {"model": "stub-model"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        if not self.responses:
            raise AssertionError("No stubbed response left.")
        return CompletionResult(text=self.responses.pop(0), response_id="stub-response", usage={})


class ExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "lint.md").write_text("Lint prompt fixture.\n", encoding="utf-8")
        self.sample = self.root / "sample.md"
        self.sample.write_text(
            "# Transformer Scaling\n\nTransformers benefit from scale.\nInference costs also rise.\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            code = cli_main(["--root", str(self.root), *argv])
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def _prepare_ready_archive_candidate(self) -> dict[str, str]:
        archive_source = self.root / "archive-candidate.md"
        archive_source.write_text("# Obscure Legacy Note\n\nMisc.\n", encoding="utf-8")
        entry = ingest_source(self.root, str(archive_source), title="Obscure Legacy Note")
        compile_wiki(self.root)
        manifest = load_manifest(self.root)
        for manifest_entry in manifest["entries"]:
            if manifest_entry["id"] == entry["id"]:
                manifest_entry["imported_at"] = "2025-01-01T00:00:00+00:00"
                manifest_entry["updated_at"] = "2025-01-01T00:00:00+00:00"
                break
        save_manifest(self.root, manifest)
        set_active_protocol(self.root, "investing")
        compile_wiki(self.root)
        compile_wiki(self.root)
        return entry

    def _prepare_accepted_rewrite(self) -> tuple[str, Path]:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        source_page = self.root / "wiki" / "sources" / f"{entry['id']}.md"
        source_page.write_text(
            source_page.read_text(encoding="utf-8").replace(
                "- Pending LLM summary.",
                "- Transformer scale improves capability and raises compute demand.",
            ),
            encoding="utf-8",
        )
        compile_wiki(self.root)
        for concept_page in sorted((self.root / "wiki" / "concepts").glob("*.md")):
            text = concept_page.read_text(encoding="utf-8")
            before, marker, after = text.partition("## Summary\n")
            _, related_marker, remainder = after.partition("\n## Related Sources\n")
            concept_page.write_text(
                before
                + marker
                + f"- Existing synthesis for {concept_page.stem} appears\n"
                + "- Keep the current synthesis grounded in the linked sources.\n"
                + related_marker
                + remainder,
                encoding="utf-8",
            )
        compile_wiki(self.root)
        memory = load_machine_memory(self.root)
        candidate = memory["health"]["concept_quality"]["rewrite_candidates"][0]
        proposal_target = self.root / candidate["path"]
        rewritten = proposal_target.read_text(encoding="utf-8").replace("Existing synthesis", "Rewritten synthesis")
        run_result = run_compile(self.root, client=_StubClient([rewritten]), limit=1)
        proposal_path = self.root / run_result["updated_rewrite_proposal_pages"][0]
        slug = proposal_path.stem
        review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        return slug, proposal_target

    def _prepare_manual_link_batch_actions(self) -> list[str]:
        first = self.root / "alpha.md"
        first.write_text("# Alpha Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
        second = self.root / "beta.md"
        second.write_text("# Beta Scaling\n\nInference cost changes with deployment shape.\n", encoding="utf-8")
        first_entry = ingest_source(self.root, str(first), title="Alpha Scaling")
        second_entry = ingest_source(self.root, str(second), title="Beta Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-alpha",
                        "kind": "add-source-concept-link",
                        "title": "Alpha Scaling link repair",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{first_entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [first_entry["id"]],
                        "concept_slugs": [concept_slug],
                    },
                    {
                        "id": "manual-link-beta",
                        "kind": "add-source-concept-link",
                        "title": "Beta Scaling link repair",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{second_entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "accepted",
                        "priority": "low",
                        "active": True,
                        "source_ids": [second_entry["id"]],
                        "concept_slugs": [concept_slug],
                    },
                ],
            },
        )
        return ["manual-link-alpha", "manual-link-beta"]

    def test_apply_material_archive_dry_run_writes_bundle_without_mutating_state(self) -> None:
        entry = self._prepare_ready_archive_candidate()

        result = apply_material_archive(self.root, entry["id"], note="Preview archive.", dry_run=True)

        archive_state = load_material_archive_state(self.root)
        self.assertTrue(result["dry_run"])
        self.assertTrue((self.root / result["bundle_path"]).exists())
        self.assertTrue((self.root / result["dry_run_path"]).exists())
        self.assertEqual(archive_state["entries"], [])

    def test_apply_concept_rewrite_dry_run_writes_preview_without_mutating_page(self) -> None:
        slug, concept_path = self._prepare_accepted_rewrite()
        before = concept_path.read_text(encoding="utf-8")

        result = apply_concept_rewrite(self.root, slug, note="Preview rewrite.", dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertTrue((self.root / result["dry_run_path"]).exists())
        self.assertEqual(concept_path.read_text(encoding="utf-8"), before)

    def test_load_protocol_runtime_schema_rejects_invalid_query_route_payload(self) -> None:
        runtime_path = self.root / "schema" / "protocols" / "research" / "runtime.yaml"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text('{"query_routes": {"strategy_order": "source-first"}}\n', encoding="utf-8")

        with self.assertRaises(RuntimeError) as ctx:
            load_protocol_runtime_schema(self.root, "research")

        self.assertIn("schema/protocols/research/runtime.yaml", str(ctx.exception))
        self.assertIn("query_routes.strategy_order", str(ctx.exception))

    def test_shell_dashboard_and_search_return_structured_results(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)

        dashboard = shell_status_dashboard(self.root)
        search = shell_search(self.root, "transformer", limit=5)

        self.assertIn("dashboard", dashboard)
        self.assertIn("suggested_next_actions", dashboard)
        self.assertGreaterEqual(len(dashboard["dashboard"]["cards"]), 1)
        self.assertEqual(search["query"], "transformer")
        self.assertGreaterEqual(search["result_count"], 1)
        self.assertEqual(search["results"][0]["kind"], "source")

    def test_review_page_next_selects_ready_page(self) -> None:
        report = ask_question(self.root, "Should we increase transformer training spend?", "report")
        file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment", protocol="investing")
        compile_wiki(self.root)

        code, payload, stderr = self._run_cli(
            ["review-page", "--next", "--status", "confirmed", "--note", "Auto-selected."]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["status"], "confirmed")
        self.assertIn("wiki/judgments/", payload["path"])

    def test_review_page_all_pending_writes_batch_receipt(self) -> None:
        first = ask_question(self.root, "Should we revise scaling assumptions?", "report")
        second = ask_question(self.root, "Should we revise serving assumptions?", "report")
        file_back(self.root, first["path"], title="Scaling Judgment A", kind="judgment", protocol="investing")
        file_back(self.root, second["path"], title="Scaling Judgment B", kind="judgment", protocol="investing")
        compile_wiki(self.root)

        code, payload, stderr = self._run_cli(["review-page", "--all-pending", "--status", "confirmed"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["operation"], "review-page-batch")
        self.assertEqual(payload["count"], 2)
        self.assertTrue((self.root / payload["receipt_path"]).exists())

    def test_cli_action_commands_allow_title_fragment_matching(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-action",
                        "kind": "add-source-concept-link",
                        "title": "Transformer Scaling link repair",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "proposed",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )
        action = {"id": "manual-link-action"}
        title_fragment = "Transformer Scaling"

        code, review_payload, review_stderr = self._run_cli(
            ["review-action", title_fragment, "--status", "accepted", "--note", "Auto-match."]
        )
        self.assertEqual(code, 0)
        self.assertEqual(review_stderr, "")
        self.assertEqual(review_payload["status"], "accepted")
        self.assertEqual(review_payload["id"], action["id"])

        code, apply_payload, apply_stderr = self._run_cli(["apply-action", title_fragment, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(apply_stderr, "")
        self.assertTrue(apply_payload["dry_run"])
        self.assertEqual(apply_payload["id"], action["id"])
        self.assertTrue((self.root / apply_payload["bundle_path"]).exists())

    def test_apply_and_revert_action_batch_round_trip(self) -> None:
        self._prepare_manual_link_batch_actions()

        code, payload, stderr = self._run_cli(["apply-action", "--all-accepted-low-risk", "--note", "Batch apply."])

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["operation"], "action-apply-batch")
        self.assertEqual(payload["count"], 2)
        self.assertTrue((self.root / payload["receipt_path"]).exists())
        manual_links = json.loads((self.root / ".aiwiki" / "state" / "manual-links.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manual_links["source_to_concept"]), 2)
        self.assertTrue(all(link["active"] for link in manual_links["source_to_concept"]))

        code, revert_payload, revert_stderr = self._run_cli(
            ["revert-action", "--last-batch", "--note", "Batch rollback."]
        )

        self.assertEqual(code, 0)
        self.assertEqual(revert_stderr, "")
        self.assertEqual(revert_payload["operation"], "action-revert-batch")
        self.assertEqual(revert_payload["count"], 2)
        self.assertEqual(revert_payload["reverted_batch_id"], payload["batch_id"])
        reverted_links = json.loads((self.root / ".aiwiki" / "state" / "manual-links.json").read_text(encoding="utf-8"))
        self.assertTrue(all(not link["active"] for link in reverted_links["source_to_concept"]))

    def test_batch_execution_helpers_reject_empty_missing_and_unsupported_inputs(self) -> None:
        with self.assertRaises(ValueError):
            review_pages_batch(self.root, [], "confirmed")
        with self.assertRaises(ValueError):
            apply_machine_memory_actions_batch(self.root, [])
        with self.assertRaises(FileNotFoundError):
            apply_machine_memory_actions_batch(self.root, ["missing-action"])

        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        concept_slug = next(path.stem for path in sorted((self.root / "wiki" / "concepts").glob("*.md")))
        save_machine_memory_action_state(
            self.root,
            {
                "version": 1,
                "actions": [
                    {
                        "id": "manual-link-proposed",
                        "kind": "add-source-concept-link",
                        "title": "Manual proposed repair",
                        "reason": "Backfill source/concept link.",
                        "primary_path": f"wiki/sources/{entry['id']}.md",
                        "secondary_path": f"wiki/concepts/{concept_slug}.md",
                        "status": "proposed",
                        "priority": "low",
                        "active": True,
                        "source_ids": [entry["id"]],
                        "concept_slugs": [concept_slug],
                    }
                ],
            },
        )

        with self.assertRaises(RuntimeError):
            apply_machine_memory_actions_batch(self.root, ["manual-link-proposed"])
        with self.assertRaises(RuntimeError):
            revert_machine_memory_action_batch(self.root)

    def test_batch_receipt_loader_and_revert_validate_receipt_shape(self) -> None:
        with self.assertRaises(FileNotFoundError):
            _load_latest_action_apply_batch_receipt(self.root, "missing-batch")

        receipt_path = self.root / "output" / "control" / "execution-batches" / "review-page-batch.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps({"kind": "execution-batch-receipt", "operation": "review-page-batch"}), encoding="utf-8")

        with self.assertRaises(RuntimeError):
            revert_machine_memory_action_batch(self.root, batch_id="review-page-batch")


if __name__ == "__main__":
    unittest.main()
