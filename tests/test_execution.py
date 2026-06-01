from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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
from aiwiki.app_execution import (
    load_execution_bundle,
    write_execution_batch_receipt_document,
    write_execution_bundle_document,
    write_execution_dry_run_document,
)
from aiwiki.app_protocol import ensure_layout, load_protocol_runtime_schema, save_manifest
from aiwiki.app_shell import shell_search, shell_status_dashboard
from aiwiki.app_state import (
    load_active_corpora_state,
    load_machine_memory,
    load_manifest,
    load_material_archive_state,
    load_output_candidates_state,
    load_runtime_history,
    machine_memory_state_path,
    save_active_corpora_state,
    save_machine_memory_action_state,
    save_output_candidates_state,
)
from aiwiki.app_utils import parse_frontmatter, utc_now
from aiwiki.cli import main as cli_main
from aiwiki.execution.alchemy import _validate_source_outputs, _write_elixir_markdown
from aiwiki.execution.candidates import demote_candidate, promote_candidate
from aiwiki.execution.l3_proposals import (
    L3PostApplyAuditError,
    L3RevertError,
    accept_l3_proposal,
    apply_l3_proposal,
    create_l3_proposal,
)
from aiwiki.execution.protocol_learnings import (
    AUDIT_STATE_PATH,
    LEARNINGS_DIR,
    _atomic_write_text,
    add_learning,
    age_learnings,
    archive_learning,
    demote_learning,
    list_learnings,
    load_learnings_for_protocol,
    revert_learning_activation,
    show_learning,
    supersede_learning,
    verify_learning,
)
from aiwiki.llm import CompletionResult
from aiwiki.runner import run_alchemy_distill, run_ask, run_compile

_VALID_REPORT_BODY = (
    "---\nid: query-stub\nkind: output\nformat: report\n---\n\n"
    "# Stub answer\n\n"
    "## 结论\nStubbed conclusion.\n\n"
    "## 关键证据\n"
    "- See wiki/sources/source-1.md\n"
    "- Secondary evidence point.\n"
    "- Tertiary evidence point.\n\n"
    "## 反证与不确定性\n- None observed in stub.\n\n"
    "## 行动建议\n- Stub follow-up.\n\n"
    "## 下次观察信号\n- Stub revisit signal.\n\n"
    "## 引用\n- wiki/sources/source-1.md\n"
)


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


def _settled_elixir_path(root: Path, elixir_id: str) -> Path:
    return root / "wiki" / "elixirs" / f"{elixir_id}.md"


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

    def _make_sample(self) -> Path:
        return self.sample

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            try:
                code = cli_main(["--root", str(self.root), *argv])
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_execution_documents_use_atomic_write_and_preserve_existing_target_on_failure(self) -> None:
        bundle_path = self.root / "output" / "control" / "execution-bundles" / "bundle.json"
        old_bundle = {"kind": "execution-bundle", "version": 1, "id": "old"}
        write_execution_bundle_document(bundle_path, old_bundle)

        with patch("aiwiki.app_execution.atomic_write_text", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_execution_bundle_document(bundle_path, {"kind": "execution-bundle", "version": 1, "id": "new"})

        self.assertEqual(load_execution_bundle(bundle_path)["id"], "old")

    def test_execution_document_write_failure_does_not_leave_target_file(self) -> None:
        dry_run_path = self.root / "output" / "control" / "execution-dry-runs" / "dry-run.json"
        receipt_path = self.root / "output" / "control" / "execution-batch-receipts" / "batch.json"

        with patch("aiwiki.app_execution.atomic_write_text", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                write_execution_dry_run_document(dry_run_path, {"kind": "execution-dry-run", "version": 1})
            with self.assertRaises(OSError):
                write_execution_batch_receipt_document(receipt_path, {"kind": "execution-batch-receipt", "version": 1})

        self.assertFalse(dry_run_path.exists())
        self.assertFalse(receipt_path.exists())

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
        entry = ingest_source(self.root, str(self._make_sample()), title="Transformer Scaling")
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

    def test_apply_l3_proposal_receipt_history_failure_reverts_target_and_degrades(self) -> None:
        target = self.root / "prompts" / "compile.md"
        before = target.read_text(encoding="utf-8")
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            target_file="prompts/compile.md",
            content="New compile prompt\n",
            proposal_id="compile-update",
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )
        accept_l3_proposal(self.root, "compile-update", note="test human accept")

        with patch("aiwiki.execution.l3_proposals.append_execution_receipt_history", side_effect=RuntimeError("receipt failed")):
            with self.assertRaises(L3PostApplyAuditError):
                apply_l3_proposal(self.root, "compile-update")

        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def _prepare_l3_apply_post_audit_failure(self, proposal_id: str = "compile-update") -> tuple[Path, str]:
        target = self.root / "prompts" / "compile.md"
        after = "New compile prompt\n"
        create_l3_proposal(
            self.root,
            kind="prompt_proposal",
            target_file="prompts/compile.md",
            content=after,
            proposal_id=proposal_id,
            evidence_refs=["e1", "e2", "e3", "e4", "e5"],
        )
        accept_l3_proposal(self.root, proposal_id, note="test human accept")
        return target, after

    def test_apply_l3_proposal_reports_audit_failure_after_receipt_history_failure(self) -> None:
        target, _after = self._prepare_l3_apply_post_audit_failure()
        before = target.read_text(encoding="utf-8")

        with patch("aiwiki.execution.l3_proposals.append_execution_receipt_history", side_effect=RuntimeError("history failed")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, "compile-update")

        self.assertEqual(ctx.exception.failed_step, "append_execution_receipt_history")
        self.assertTrue(ctx.exception.target_reverted)
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / f"{ctx.exception.action_id}.json").exists())

    def test_apply_l3_proposal_reports_audit_failure_after_state_failure(self) -> None:
        target, _after = self._prepare_l3_apply_post_audit_failure()
        before = target.read_text(encoding="utf-8")

        with patch("aiwiki.execution.l3_proposals.save_l3_proposal_state", side_effect=RuntimeError("state failed")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, "compile-update")

        self.assertEqual(ctx.exception.failed_step, "save_l3_proposal_state")
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / f"{ctx.exception.action_id}.json").exists())

    def test_apply_l3_proposal_reports_audit_failure_after_page_failure(self) -> None:
        target, _after = self._prepare_l3_apply_post_audit_failure()
        before = target.read_text(encoding="utf-8")
        from aiwiki.execution import l3_proposals

        original_persist = l3_proposals._persist_l3_proposal_page
        calls = 0

        def fail_once(root: Path, proposal: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("page failed")
            original_persist(root, proposal)

        with patch("aiwiki.execution.l3_proposals._persist_l3_proposal_page", side_effect=fail_once):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, "compile-update")

        self.assertEqual(ctx.exception.failed_step, "_persist_l3_proposal_page")
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / f"{ctx.exception.action_id}.json").exists())

    def test_apply_l3_proposal_reverts_target_on_runtime_history_failure(self) -> None:
        target, _after = self._prepare_l3_apply_post_audit_failure()
        before = target.read_text(encoding="utf-8")

        with patch("aiwiki.execution.l3_proposals.append_runtime_history", side_effect=RuntimeError("runtime failed")):
            with self.assertRaises(L3PostApplyAuditError) as ctx:
                apply_l3_proposal(self.root, "compile-update")

        self.assertEqual(ctx.exception.failed_step, "append_runtime_history")
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / "output" / "control" / "execution-receipts" / f"{ctx.exception.action_id}.json").exists())

    def test_apply_l3_proposal_revert_failure_raises_l3_revert_error(self) -> None:
        target, _after = self._prepare_l3_apply_post_audit_failure()
        # R94.5: rollback now goes through atomic_write_bytes; patch that.
        from aiwiki.execution import l3_proposals as l3_mod

        original_atomic = l3_mod.atomic_write_bytes

        def guarded_atomic_write_bytes(path: Path, data: bytes, **kwargs: object) -> None:
            if path == target and data == b"Compile prompt fixture.\n":
                raise OSError("revert also fails")
            original_atomic(path, data, **kwargs)

        with (
            patch("aiwiki.execution.l3_proposals.append_runtime_history", side_effect=RuntimeError("runtime failed")),
            patch("aiwiki.execution.l3_proposals.atomic_write_bytes", side_effect=guarded_atomic_write_bytes),
        ):
            with self.assertRaises(L3RevertError):
                apply_l3_proposal(self.root, "compile-update")

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
        self.assertTrue(any(result["kind"] == "source" for result in search["results"]))

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

    def test_load_output_candidates_state_returns_default(self) -> None:
        state = load_output_candidates_state(self.root)

        self.assertEqual(state, {"version": 1, "candidates": []})

    def test_ask_question_marks_candidate_pending(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        page = (self.root / result["path"]).read_text(encoding="utf-8")

        self.assertEqual(parse_frontmatter(page).get("candidate_state"), "pending")
        state = load_output_candidates_state(self.root)
        self.assertEqual(len(state["candidates"]), 1)
        self.assertEqual(state["candidates"][0]["artifact_ref"], result["path"])
        self.assertEqual(state["candidates"][0]["candidate_state"], "pending")

    def test_ask_question_merges_curated_judgment_provenance_into_source_files(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        judgment_path = self.root / "wiki" / "judgments" / "j-curated.md"
        judgment_path.parent.mkdir(parents=True, exist_ok=True)
        judgment_path.write_text("---\nid: j-curated\nkind: judgment\n---\n\n# Curated Judgment\n", encoding="utf-8")
        memory = load_machine_memory(self.root)
        memory["edges"] = dict(memory.get("edges") or {})
        memory["edges"]["source_to_judgment"] = [{"source_id": entry["id"], "page_id": "j-curated"}]
        machine_memory_state_path(self.root).write_text(json.dumps(memory, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = ask_question(self.root, "Compare transformer scale and inference cost", "report")

        frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))
        self.assertIn("wiki/judgments/j-curated.md", frontmatter.get("source_files", []))

    def test_ask_question_records_notify_dispatch_failure_without_raising(self) -> None:
        with patch("aiwiki.execution.ask.notify_report_generated", side_effect=RuntimeError("notify boom")):
            result = ask_question(self.root, "Should we increase transformer training spend?", "report")

        events = [
            json.loads(line)
            for line in (self.root / ".aiwiki/logs/runs.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertIn("path", result)
        self.assertEqual(events[-1]["event"], "notify_dispatch_failed")
        self.assertEqual(events[-1]["reason"], "notify boom")
        self.assertEqual(events[-1]["error_type"], "RuntimeError")
        self.assertEqual(events[-1]["artifact"], result["path"])

    def test_ask_question_uses_readable_report_filename_without_query_timestamp(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")

        self.assertEqual(result["path"], "output/reports/should-we-increase-transformer-training-spend.md")
        page = (self.root / result["path"]).read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(page)
        self.assertEqual(frontmatter["_id"], "should-we-increase-transformer-training-spend")
        self.assertTrue(frontmatter["created_at"])

    def test_ask_question_preserves_cjk_title_in_report_filename(self) -> None:
        result = ask_question(self.root, "评估炼丹炉最终形态？", "report")

        self.assertEqual(result["path"], "output/reports/评估炼丹炉最终形态.md")

    def test_ask_question_uses_collision_suffix_instead_of_timestamp(self) -> None:
        first = ask_question(self.root, "Should we increase transformer training spend?", "report")
        second = ask_question(self.root, "Should we increase transformer training spend?", "report")

        self.assertEqual(first["path"], "output/reports/should-we-increase-transformer-training-spend.md")
        self.assertEqual(second["path"], "output/reports/should-we-increase-transformer-training-spend-2.md")

    def test_ask_question_keeps_format_suffix_without_timestamp(self) -> None:
        result = ask_question(self.root, "What next?", "decision-memo")

        self.assertEqual(result["path"], "output/reports/what-next-decision-memo.md")

    def test_file_back_uses_readable_curated_filename_without_timestamp(self) -> None:
        artifact = self.root / "output" / "reports" / "semantic-navigation-assessment.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            "---\n"
            "id: semantic-navigation-assessment\n"
            "kind: output\n"
            "format: report\n"
            "created_at: 2026-04-29T00:00:00+00:00\n"
            "---\n"
            "\n"
            "# Semantic Navigation Assessment\n"
            "\n"
            "Body.\n",
            encoding="utf-8",
        )

        result = file_back(
            self.root,
            "output/reports/semantic-navigation-assessment.md",
            title="Eva Robot Batch E semantic navigation assessment",
            kind="judgment",
        )

        self.assertEqual(
            result["path"],
            "wiki/judgments/judgment-eva-robot-batch-e-semantic-navigation-assessment.md",
        )
        page = (self.root / result["path"]).read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(page)
        self.assertEqual(frontmatter["id"], "judgment-eva-robot-batch-e-semantic-navigation-assessment")
        self.assertTrue(frontmatter["formed_at"])

    def test_ask_with_corpus_flag_reuses_corpus_id(self) -> None:
        first = run_ask(self.root, "First question?", "report", client=_StubClient([_VALID_REPORT_BODY]))
        second = run_ask(
            self.root,
            "Second question?",
            "report",
            client=_StubClient([_VALID_REPORT_BODY]),
            corpus_id_override=first["active_corpus_id"],
        )

        self.assertEqual(first["active_corpus_id"], second["active_corpus_id"])
        first_frontmatter = parse_frontmatter((self.root / first["path"]).read_text(encoding="utf-8"))
        second_frontmatter = parse_frontmatter((self.root / second["path"]).read_text(encoding="utf-8"))
        self.assertEqual(first_frontmatter.get("candidate_state"), "pending")
        self.assertEqual(second_frontmatter.get("candidate_state"), "pending")

    def test_ask_second_round_injects_previous_output_summary(self) -> None:
        first = run_ask(self.root, "First question?", "report", client=_StubClient([_VALID_REPORT_BODY]))
        captured: dict[str, str] = {}

        from aiwiki.runner import workflows_ask as runner_module

        original = runner_module._build_ask_prompt

        def spy(*args, **kwargs):
            captured["prompt"] = original(*args, **kwargs)
            return captured["prompt"]

        with patch.object(runner_module, "_build_ask_prompt", side_effect=spy):
            run_ask(
                self.root,
                "Second question?",
                "report",
                client=_StubClient([_VALID_REPORT_BODY, _VALID_REPORT_BODY]),
                corpus_id_override=first["active_corpus_id"],
            )

        self.assertIn("## Previous Output In Corpus", captured["prompt"])
        self.assertIn(first["path"], captured["prompt"])

    def test_ask_first_round_no_previous_output_section(self) -> None:
        captured: dict[str, str] = {}

        from aiwiki.runner import workflows_ask as runner_module

        original = runner_module._build_ask_prompt

        def spy(*args, **kwargs):
            captured["prompt"] = original(*args, **kwargs)
            return captured["prompt"]

        with patch.object(runner_module, "_build_ask_prompt", side_effect=spy):
            run_ask(self.root, "First question?", "report", client=_StubClient([_VALID_REPORT_BODY]))

        self.assertNotIn("## Previous Output In Corpus", captured["prompt"])

    def test_file_back_marks_candidate_promoted(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        file_back(self.root, result["path"], title="Scaling Judgment", kind="judgment", protocol="investing")

        state = load_output_candidates_state(self.root)
        self.assertEqual(len(state["candidates"]), 1)
        candidate = state["candidates"][0]
        self.assertEqual(candidate["candidate_state"], "promoted")
        self.assertTrue(candidate["promoted_to"])
        self.assertTrue(candidate["promoted_at"])

    def test_promote_candidate_moves_to_wiki_derived(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")

        promoted = promote_candidate(self.root, result["path"])

        self.assertEqual(promoted["status"], "promoted")
        self.assertTrue((self.root / promoted["promoted_path"]).exists())
        self.assertTrue(promoted["promoted_path"].startswith("wiki/derived/"))
        page = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertEqual(parse_frontmatter(page).get("candidate_state"), "promoted")
        state = load_output_candidates_state(self.root)
        self.assertEqual(state["candidates"][0]["candidate_state"], "promoted")

    def test_promote_recurring_candidate_still_lands_in_wiki_derived(self) -> None:
        # contract SC4: 阶段 1 所有 promote 都去 wiki/derived/，
        # nightly 登记的 recurring_kind=decision/judgment 不应把 promote 目标改走
        result = ask_question(self.root, "Should we tune the scaling ladder?", "report")
        from aiwiki.app_state import upsert_output_candidate  # 局部 import 避免污染全局
        upsert_output_candidate(
            self.root,
            artifact_ref=result["path"],
            candidate_state="pending",
            created_at="2026-04-24T00:00:00Z",
            updated_at="2026-04-24T00:00:00Z",
            format="report",
            protocol="investing",
            corpus_id="",
            question="Should we tune the scaling ladder?",
            promotion_origin="nightly-recurring",
        )
        # 手工把 recurring_kind 注入到 state 里（模拟 nightly 入队后的记录）
        state = load_output_candidates_state(self.root)
        for candidate in state["candidates"]:
            if candidate["artifact_ref"] == result["path"]:
                candidate["recurring_kind"] = "decision"
        from aiwiki.app_state import save_output_candidates_state
        save_output_candidates_state(self.root, state)

        promoted = promote_candidate(self.root, result["path"])

        self.assertTrue(promoted["promoted_path"].startswith("wiki/derived/"))
        self.assertFalse((self.root / "wiki" / "decisions").exists())

    def test_promote_candidate_not_found_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            promote_candidate(self.root, "output/reports/missing.md")

    def test_demote_candidate_marks_frontmatter(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")

        demoted = demote_candidate(self.root, result["path"])

        self.assertEqual(demoted["status"], "demoted")
        page = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertEqual(parse_frontmatter(page).get("candidate_state"), "demoted")

    def test_demote_candidate_idempotent_via_state(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")

        demote_candidate(self.root, result["path"])
        state = load_output_candidates_state(self.root)

        # demote 从队列索引移除（contract line 20），frontmatter 仍保留 demoted 标记
        self.assertFalse(
            any(c.get("artifact_ref") == result["path"] for c in state["candidates"])
        )

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
        entry = ingest_source(self.root, str(self._make_sample()), title="Transformer Scaling")
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


class AlchemyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            try:
                code = cli_main(["--root", str(self.root), *argv])
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def _make_sample(self, name: str = "sample.md") -> Path:
        sample = self.root / name
        sample.write_text("# Transformer Scaling\n\nTransformers benefit from scale.\n", encoding="utf-8")
        return sample

    def _make_promoted_corpus(self, questions: list[str]) -> str:
        corpus_id = ""
        for question in questions:
            result = ask_question(self.root, question, "report", corpus_id_override=corpus_id or None)
            promote_candidate(self.root, result["path"])
            corpus_id = str(result.get("active_corpus_id") or corpus_id)
        return corpus_id

    def _run_cli(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", new=stdout), patch("sys.stderr", new=stderr):
            try:
                code = cli_main(["--root", str(self.root), *argv])
            except SystemExit as exc:
                code = int(exc.code or 0)
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_alchemy_start_creates_elixir_from_promoted_outputs(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])

        from aiwiki.runner import run_alchemy_start

        result = run_alchemy_start(self.root, corpus_id, "VLA robotics")

        path = self.root / result["path"]
        self.assertTrue(path.exists())
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "draft")
        self.assertEqual(frontmatter["iteration"], "0")
        self.assertTrue(frontmatter["derived_from"])
        self.assertTrue(all(str(item).startswith("wiki/derived/") for item in frontmatter["derived_from"]))
        self.assertNotIn("Pending refinement", path.read_text(encoding="utf-8"))

    def test_alchemy_promote_rejects_placeholder_body(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_finalize, run_alchemy_promote, run_alchemy_start

        started = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / started["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        _write_elixir_markdown(
            path,
            frontmatter=frontmatter,
            body="# Elixir\n\n## Thesis\n- pending refinement\n\n## Evidence\n- Pending refinement.\n\n## Open Questions\n- Pending refinement.\n",
        )
        run_alchemy_finalize(self.root, elixir_id=started["elixir_id"])

        with self.assertRaisesRegex(ValueError, "elixir_body_placeholder"):
            run_alchemy_promote(self.root, elixir_id=started["elixir_id"])

    def test_alchemy_distill_repairs_legacy_placeholder_body(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        started = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / started["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        _write_elixir_markdown(
            path,
            frontmatter=frontmatter,
            body="# Elixir\n\n## Thesis\n- Pending refinement.\n\n## Evidence\n- Pending refinement.\n\n## Open Questions\n- Pending refinement.\n",
        )

        distilled = run_alchemy_distill(self.root, started["elixir_id"], "Repair the elixir body from provenance.")

        body = (self.root / distilled["path"]).read_text(encoding="utf-8")
        self.assertNotIn("Pending refinement", body)
        self.assertIn("## Evidence", body)

    def test_alchemy_start_raises_when_corpus_has_no_promoted(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.app_state import save_output_candidates_state

        save_output_candidates_state(self.root, {"version": 1, "candidates": []})

        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(ValueError):
            run_alchemy_start(self.root, corpus_id, "VLA robotics")
        self.assertFalse((self.root / "wiki" / "elixirs").exists())

    def test_alchemy_start_raises_when_corpus_unknown(self) -> None:
        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(FileNotFoundError):
            run_alchemy_start(self.root, "missing-corpus", "VLA robotics")

    def test_alchemy_distill_increments_iteration_and_preserves_provenance(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        second = ask_question(self.root, "What about latency?", "report", corpus_id_override=corpus_id)
        promote_candidate(self.root, second["path"])

        result = run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")

        self.assertEqual(result["iteration"], 1)
        path = self.root / result["path"]
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["iteration"], "1")
        self.assertGreaterEqual(len(frontmatter["derived_from"]), 2)
        self.assertEqual(len(json.loads(frontmatter.get("distill_history_json", "[]"))), 1)

    def test_alchemy_distill_rejects_sealed_elixir(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_finalize, run_alchemy_promote, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        run_alchemy_finalize(self.root, elixir_id=start["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=start["elixir_id"])

        from aiwiki.runner import run_alchemy_distill

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")
        frontmatter = parse_frontmatter(_settled_elixir_path(self.root, start["elixir_id"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "settled")

    def test_alchemy_validates_source_output_must_be_wiki_derived(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["output/reports/foo.md"], allowed=set())
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["wiki/derived/missing.md"], allowed={"wiki/derived/missing.md"})

    def test_alchemy_start_rejects_when_all_candidates_demoted(self) -> None:
        """Allowlist 来源已从 output_refs ring buffer 迁到 candidate.candidate_state 权威。

        tamper surface 不再是 corpus.output_refs（那只是最近上下文 ring buffer，轮数一多
        合法旧 provenance 会被截断失效，见 EP-029 MUST-FIX #3）。真正的 allowlist =
        corpus_id 下 candidate_state == "promoted" 的候选。demote 所有候选后 allowlist 空。
        """
        corpus_id = self._make_promoted_corpus(["Question A?"])
        result = ask_question(self.root, "Question B?", "report", corpus_id_override=corpus_id)
        promote_candidate(self.root, result["path"])
        # demote 所有 promoted candidate，allowlist 应变空
        candidates_state = load_output_candidates_state(self.root)
        for cand in candidates_state.get("candidates", []):
            if str(cand.get("corpus_id") or "") == corpus_id and str(cand.get("candidate_state") or "") == "promoted":
                demote_candidate(self.root, str(cand["artifact_ref"]))

        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(ValueError):
            run_alchemy_start(self.root, corpus_id, "VLA robotics")

    def test_alchemy_start_raises_when_output_refs_has_no_promoted_intersection(self) -> None:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        corpus_id = str(result["active_corpus_id"])
        corpora = load_active_corpora_state(self.root)
        for corpus in corpora["corpora"]:
            if str(corpus.get("corpus_id") or "") == corpus_id:
                corpus["output_refs"] = ["wiki/derived/missing.md"]
        save_active_corpora_state(self.root, corpora)

        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(ValueError):
            run_alchemy_start(self.root, corpus_id, "VLA robotics")

    def test_alchemy_distill_rejects_empty_source_outputs_tampering(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.execution.alchemy import _write_elixir_markdown
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / start["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        frontmatter["derived_from"] = []
        _write_elixir_markdown(path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")

    def test_alchemy_distill_rejects_stale_source_output_when_candidate_demoted(self) -> None:
        """distill 应拒绝指向已被 demote 的 source_outputs。

        权威 allowlist = `candidate_state == "promoted"` 的候选。demote 后 candidate row
        被删除，allowlist 不再包含该 promoted_to → existing provenance 校验失败。
        替代旧版依赖 corpus.output_refs 清空的 tamper 模型（MUST-FIX #3 已解耦）。
        """
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        # demote 掉所有 promoted candidate，使 existing source_outputs 落到 allowlist 之外
        candidates_state = load_output_candidates_state(self.root)
        for cand in candidates_state.get("candidates", []):
            if str(cand.get("corpus_id") or "") == corpus_id and str(cand.get("candidate_state") or "") == "promoted":
                demote_candidate(self.root, str(cand["artifact_ref"]))

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")

    def test_alchemy_start_produces_unique_id_for_same_topic(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_start

        first = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        second = run_alchemy_start(self.root, corpus_id, "VLA robotics")

        self.assertNotEqual(first["elixir_id"], second["elixir_id"])
        self.assertTrue((self.root / first["path"]).exists())
        self.assertTrue((self.root / second["path"]).exists())

    def test_start_elixir_rejects_derived_from_without_wiki_derived_anchor(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        elixir_root = self.root / "wiki" / "elixirs"
        elixir_root.mkdir(parents=True, exist_ok=True)
        ref = elixir_root / "ref.md"
        ref.write_text("---\nelixir_id: \"ref\"\nelixir_state: \"settled\"\nderived_from:\n  - \"wiki/derived/base.md\"\n---\n# stub\n", encoding="utf-8")
        from aiwiki.app_state import load_output_candidates_state, save_output_candidates_state

        state = load_output_candidates_state(self.root)
        for cand in state["candidates"]:
            if str(cand.get("corpus_id") or "") == corpus_id and str(cand.get("candidate_state") or "") == "promoted":
                cand["promoted_to"] = "wiki/elixirs/ref.md"
        save_output_candidates_state(self.root, state)

        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "VLA robotics")
        self.assertIn("必须至少包含一个 wiki/derived/", str(ctx.exception))

    def test_start_elixir_accepts_settled_elixir_reference(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        settled = self.root / "wiki" / "elixirs" / "settled.md"
        settled.parent.mkdir(parents=True, exist_ok=True)
        settled.write_text("---\nelixir_id: \"settled\"\nelixir_state: \"settled\"\nderived_from:\n  - \"wiki/derived/base.md\"\n---\n# stub\n", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        with patch.object(alchemy_module, "list_promoted_outputs_for_corpus", return_value=[
            {"promoted_to": "wiki/derived/base.md"},
            {"promoted_to": f"wiki/elixirs/{settled.name}"},
        ]):
            result = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        self.assertTrue((self.root / result["path"]).exists())

    def test_start_elixir_with_include_elixir_cli_reference_settled(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        first = run_alchemy_start(self.root, corpus_id, "A")
        self._run_cli(["alchemy-finalize", "--elixir-id", first["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", first["elixir_id"]])

        code, payload, stderr = self._run_cli(
            ["alchemy-start", corpus_id, "--topic", "B", "--protocol", "general", "--include-elixir", first["elixir_id"]]
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        new_path = self.root / payload["path"]
        fm = parse_frontmatter(new_path.read_text(encoding="utf-8"))
        self.assertIn(f"wiki/elixirs/{first['elixir_id']}.md", fm["derived_from"])

    def test_start_elixir_rejects_non_settled_elixir_reference(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        draft = self.root / "wiki" / "elixirs" / "draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("---\nelixir_id: \"draft\"\nelixir_state: \"draft\"\nderived_from:\n  - \"wiki/derived/base.md\"\n---\n# stub\n", encoding="utf-8")
        from aiwiki.app_state import load_output_candidates_state, save_output_candidates_state

        state = load_output_candidates_state(self.root)
        for cand in state["candidates"]:
            if str(cand.get("corpus_id") or "") == corpus_id and str(cand.get("candidate_state") or "") == "promoted":
                cand["promoted_to"] = f"wiki/elixirs/{draft.name}"
        save_output_candidates_state(self.root, state)

        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "VLA robotics")
        self.assertIn("只能引用 settled 金丹", str(ctx.exception))

    def test_start_elixir_rejects_self_reference(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        (self.root / "wiki" / "elixirs").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "elixirs" / "self-ref.md").write_text("---\nelixir_id: \"self-ref\"\nelixir_state: \"settled\"\nderived_from:\n  - \"wiki/derived/base.md\"\n---\n# stub\n", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module

        with patch.object(alchemy_module, "next_available_stem", return_value="self-ref"):
            with patch.object(alchemy_module, "list_promoted_outputs_for_corpus", return_value=[
                {"promoted_to": "wiki/derived/base.md"},
                {"promoted_to": "wiki/elixirs/self-ref.md"},
            ]):
                with self.assertRaises(ValueError) as ctx:
                    alchemy_module.start_elixir(self.root, corpus_id, topic="VLA robotics")
        self.assertIn("cannot reference self", str(ctx.exception))

    def test_distill_elixir_rejects_cycle_two_nodes(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        # A 走真实 CLI seal 流程变为 settled；B 保持 draft，后续对 B distill。
        self._run_cli(["alchemy-finalize", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", a["elixir_id"]])
        # 外部篡改 A 的 derived_from 注入 A→B 边（脏数据模拟）。
        a_path = _settled_elixir_path(self.root, a["elixir_id"])
        a_text = a_path.read_text(encoding="utf-8")
        a_fm = parse_frontmatter(a_text)
        a_fm["derived_from"] = [a_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"]
        _write_elixir_markdown(a_path, frontmatter=a_fm, body=a_text.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_distill(self.root, b["elixir_id"], "cycle?", include_elixir_ids=[a["elixir_id"]])
        self.assertIn("金丹引用形成环路", str(ctx.exception))
        self.assertIn("→", str(ctx.exception))

    def test_distill_elixir_rejects_cycle_three_nodes(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.runner import run_alchemy_finalize, run_alchemy_promote, run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        c = run_alchemy_start(self.root, corpus_id, "C")
        run_alchemy_finalize(self.root, elixir_id=b["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=b["elixir_id"])
        run_alchemy_finalize(self.root, elixir_id=c["elixir_id"])
        run_alchemy_promote(self.root, elixir_id=c["elixir_id"])

        a_path = self.root / a["path"]
        a_text = a_path.read_text(encoding="utf-8")
        a_fm = parse_frontmatter(a_text)
        a_fm["derived_from"] = [a_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"]
        _write_elixir_markdown(a_path, frontmatter=a_fm, body=a_text.split("---", 2)[-1].lstrip("\n"))

        b_path = _settled_elixir_path(self.root, b["elixir_id"])
        b_text = b_path.read_text(encoding="utf-8")
        b_fm = parse_frontmatter(b_text)
        b_fm["derived_from"] = [b_fm["derived_from"][0], f"wiki/elixirs/{c['elixir_id']}.md"]
        _write_elixir_markdown(b_path, frontmatter=b_fm, body=b_text.split("---", 2)[-1].lstrip("\n"))

        c_path = _settled_elixir_path(self.root, c["elixir_id"])
        c_text = c_path.read_text(encoding="utf-8")
        c_fm = parse_frontmatter(c_text)
        c_fm["derived_from"] = [c_fm["derived_from"][0], f"wiki/elixirs/{a['elixir_id']}.md"]
        _write_elixir_markdown(c_path, frontmatter=c_fm, body=c_text.split("---", 2)[-1].lstrip("\n"))

        from aiwiki.execution import alchemy as alchemy_module

        with self.assertRaises(ValueError) as ctx:
            alchemy_module.distill_elixir(self.root, a["elixir_id"], question="cycle?")
        self.assertIn(a["elixir_id"], str(ctx.exception))

    def test_distill_elixir_error_includes_cycle_path(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        # B 走真实 CLI seal 变 settled；A 保持 draft，后续 distill A。
        self._run_cli(["alchemy-finalize", "--elixir-id", b["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", b["elixir_id"]])
        # 外部篡改 B 的 derived_from 注入 B→A 边；A 保持 draft 但磁盘上挂上 A→B 边。
        b_path = _settled_elixir_path(self.root, b["elixir_id"])
        a_path = self.root / a["path"]
        for path, nxt in [(a_path, b), (b_path, a)]:
            text = path.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            fm["derived_from"] = [fm["derived_from"][0], f"wiki/elixirs/{nxt['elixir_id']}.md"]
            _write_elixir_markdown(path, frontmatter=fm, body=text.split("---", 2)[-1].lstrip("\n"))

        from aiwiki.runner import run_alchemy_distill

        with self.assertRaises(ValueError) as ctx:
            run_alchemy_distill(self.root, a["elixir_id"], "cycle?")
        self.assertIn("金丹引用形成环路", str(ctx.exception))
        self.assertIn(f"wiki/elixirs/{a['elixir_id']}.md → wiki/elixirs/{b['elixir_id']}.md → wiki/elixirs/{a['elixir_id']}.md", str(ctx.exception))

    def test_detect_cycle_handles_update_elixir_overrides_old_edges(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        # 让 A 和 B 都走 CLI seal 到 settled，才能参与 DAG 图（contract 规定非 settled 不入图）。
        self._run_cli(["alchemy-finalize", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-finalize", "--elixir-id", b["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", b["elixir_id"]])
        # 磁盘上把 B 写成 B→A（脏边）。
        b_path = _settled_elixir_path(self.root, b["elixir_id"])
        b_text = b_path.read_text(encoding="utf-8")
        b_fm = parse_frontmatter(b_text)
        b_base = b_fm["derived_from"][0]
        b_fm["derived_from"] = [b_base, f"wiki/elixirs/{a['elixir_id']}.md"]
        _write_elixir_markdown(b_path, frontmatter=b_fm, body=b_text.split("---", 2)[-1].lstrip("\n"))

        # 否定：传入的新 derived_from 只含 base，覆盖磁盘上 B→A 旧边 → 无环。
        cycle = alchemy_module._detect_elixir_cycle(self.root, b_path, [b_base])
        self.assertIsNone(cycle)

        # 磁盘上再追加 A→B（脏边），形成 A↔B。
        a_path = _settled_elixir_path(self.root, a["elixir_id"])
        a_text = a_path.read_text(encoding="utf-8")
        a_fm = parse_frontmatter(a_text)
        a_fm["derived_from"] = [a_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"]
        _write_elixir_markdown(a_path, frontmatter=a_fm, body=a_text.split("---", 2)[-1].lstrip("\n"))

        # 肯定：传入新 derived_from 包含 B→A 时，A↔B 环成立。
        cycle = alchemy_module._detect_elixir_cycle(self.root, b_path, b_fm["derived_from"])
        self.assertIsNotNone(cycle)

    def test_include_elixir_rejects_path_traversal_id(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        run_alchemy_start(self.root, corpus_id, "seed")
        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "new", include_elixir_ids=["../derived/base"])
        self.assertIn("不允许包含路径分隔符", str(ctx.exception))

    def test_include_elixir_rejects_empty_id(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        run_alchemy_start(self.root, corpus_id, "seed")
        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "new", include_elixir_ids=["   "])
        self.assertIn("金丹 id 不能为空", str(ctx.exception))

    def test_include_elixir_rejects_dotdot_id(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        run_alchemy_start(self.root, corpus_id, "seed")
        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "new", include_elixir_ids=[".."])
        self.assertIn("金丹 id 非法", str(ctx.exception))

    def test_detect_cycle_normalizes_dot_slash_path(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        # 两边都 seal 到 settled 才能入图；本测试专门验证归一化（./ 前缀）。
        self._run_cli(["alchemy-finalize", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-finalize", "--elixir-id", b["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", b["elixir_id"]])
        a_path = _settled_elixir_path(self.root, a["elixir_id"])
        a_text = a_path.read_text(encoding="utf-8")
        a_fm = parse_frontmatter(a_text)
        a_fm["derived_from"] = [a_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"]
        _write_elixir_markdown(a_path, frontmatter=a_fm, body=a_text.split("---", 2)[-1].lstrip("\n"))
        b_path = _settled_elixir_path(self.root, b["elixir_id"])
        b_text = b_path.read_text(encoding="utf-8")
        b_fm = parse_frontmatter(b_text)
        b_fm["derived_from"] = [b_fm["derived_from"][0], "./wiki/elixirs/%s.md" % a["elixir_id"]]
        _write_elixir_markdown(b_path, frontmatter=b_fm, body=b_text.split("---", 2)[-1].lstrip("\n"))

        cycle = alchemy_module._detect_elixir_cycle(self.root, b_path, b_fm["derived_from"])
        self.assertIsNotNone(cycle)

    def test_detect_cycle_normalizes_backslash_path(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        self._run_cli(["alchemy-finalize", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-finalize", "--elixir-id", b["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", b["elixir_id"]])
        a_path = _settled_elixir_path(self.root, a["elixir_id"])
        a_text = a_path.read_text(encoding="utf-8")
        a_fm = parse_frontmatter(a_text)
        a_fm["derived_from"] = [a_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"]
        _write_elixir_markdown(a_path, frontmatter=a_fm, body=a_text.split("---", 2)[-1].lstrip("\n"))
        b_path = _settled_elixir_path(self.root, b["elixir_id"])
        b_text = b_path.read_text(encoding="utf-8")
        b_fm = parse_frontmatter(b_text)
        b_fm["derived_from"] = [b_fm["derived_from"][0], "wiki\\elixirs\\%s.md" % a["elixir_id"]]
        _write_elixir_markdown(b_path, frontmatter=b_fm, body=b_text.split("---", 2)[-1].lstrip("\n"))

        cycle = alchemy_module._detect_elixir_cycle(self.root, b_path, b_fm["derived_from"])
        self.assertIsNotNone(cycle)

    def test_detect_cycle_ignores_non_settled_elixir_edges(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "base.md").write_text("base", encoding="utf-8")
        from aiwiki.execution import alchemy as alchemy_module
        from aiwiki.runner import run_alchemy_start

        a = run_alchemy_start(self.root, corpus_id, "A")
        b = run_alchemy_start(self.root, corpus_id, "B")
        self._run_cli(["alchemy-finalize", "--elixir-id", a["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", a["elixir_id"]])
        b_path = self.root / b["path"]
        b_text = b_path.read_text(encoding="utf-8")
        b_fm = parse_frontmatter(b_text)
        b_fm["derived_from"] = [b_fm["derived_from"][0], f"wiki/elixirs/{a['elixir_id']}.md"]
        _write_elixir_markdown(b_path, frontmatter=b_fm, body=b_text.split("---", 2)[-1].lstrip("\n"))

        cycle = alchemy_module._detect_elixir_cycle(
            self.root,
            _settled_elixir_path(self.root, a["elixir_id"]),
            [b_fm["derived_from"][0], f"wiki/elixirs/{b['elixir_id']}.md"],
        )
        self.assertIsNone(cycle)

    def test_include_elixir_rejects_nonexistent_id(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        with self.assertRaises(FileNotFoundError) as ctx:
            run_alchemy_start(self.root, corpus_id, "VLA robotics", include_elixir_ids=["missing"])
        self.assertIn("指定的金丹 missing 不存在", str(ctx.exception))

    def test_include_elixir_cli_rejects_trailing_comma(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        first = run_alchemy_start(self.root, corpus_id, "seed")
        self._run_cli(["alchemy-finalize", "--elixir-id", first["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", first["elixir_id"]])

        code, _payload, stderr = self._run_cli(
            ["alchemy-start", corpus_id, "--topic", "new", "--protocol", "general", "--include-elixir", f"{first['elixir_id']},"]
        )

        self.assertNotEqual(code, 0)
        self.assertIn("金丹 id 不能为空", stderr)

    def test_include_elixir_cli_rejects_empty_middle(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        first = run_alchemy_start(self.root, corpus_id, "seed")
        second = run_alchemy_start(self.root, corpus_id, "seed-2")
        self._run_cli(["alchemy-finalize", "--elixir-id", first["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", first["elixir_id"]])
        self._run_cli(["alchemy-finalize", "--elixir-id", second["elixir_id"]])
        self._run_cli(["alchemy-promote", "--elixir-id", second["elixir_id"]])

        code, _payload, stderr = self._run_cli(
            [
                "alchemy-start",
                corpus_id,
                "--topic",
                "new",
                "--protocol",
                "general",
                "--include-elixir",
                f"{first['elixir_id']},,{second['elixir_id']}",
            ]
        )

        self.assertNotEqual(code, 0)
        self.assertIn("金丹 id 不能为空", stderr)

    def test_include_elixir_rejects_draft_elixir(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        from aiwiki.runner import run_alchemy_start

        draft = run_alchemy_start(self.root, corpus_id, "draft")
        with self.assertRaises(ValueError) as ctx:
            run_alchemy_start(self.root, corpus_id, "new", include_elixir_ids=[draft["elixir_id"]])
        self.assertIn("只能引用 settled 金丹", str(ctx.exception))

    def test_alchemy_parse_raises_on_corrupt_distill_history_json(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / start["path"]
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace('distill_history_json: "[]"', 'distill_history_json: "not json"', 1), encoding="utf-8")

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")

    def test_batch_execution_helpers_reject_empty_missing_and_unsupported_inputs(self) -> None:
        with self.assertRaises(ValueError):
            review_pages_batch(self.root, [], "confirmed")
        with self.assertRaises(ValueError):
            apply_machine_memory_actions_batch(self.root, [])
        with self.assertRaises(FileNotFoundError):
            apply_machine_memory_actions_batch(self.root, ["missing-action"])

        entry = ingest_source(self.root, str(self._make_sample()), title="Transformer Scaling")
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


class ProtocolLearningsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _make_promoted_derived(self) -> str:
        result = ask_question(self.root, "Should we increase transformer training spend?", "report")
        promoted = promote_candidate(self.root, result["path"])
        return promoted["promoted_path"]

    def test_protocol_learn_add_creates_learning(self) -> None:
        result = add_learning(self.root, "general", title="My lesson")
        path = self.root / result["path"]
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        self.assertTrue(path.exists())
        self.assertEqual(fm["learning_id"], result["learning_id"])
        self.assertEqual(fm["protocol"], "general")
        self.assertIn("# Protocol Learning", text)
        self.assertIn("## Lesson", text)
        self.assertIn("## When to apply", text)
        self.assertIn("## Evidence", text)

    def test_protocol_learn_add_with_source_refs_validates_and_writes(self) -> None:
        promoted_path = self._make_promoted_derived()
        result = add_learning(self.root, "general", title="Anchored lesson", source_refs=[promoted_path])
        self.assertTrue((self.root / result["path"]).exists())

    def test_protocol_learn_add_rejects_unknown_protocol(self) -> None:
        with self.assertRaises(ValueError):
            add_learning(self.root, "nonexistent", title="bad")

    def test_protocol_learn_add_rejects_source_ref_outside_allowed_prefixes(self) -> None:
        with self.assertRaises(ValueError):
            add_learning(self.root, "general", title="bad", source_refs=["raw/foo.md"])
        with self.assertRaises(ValueError):
            add_learning(self.root, "general", title="bad", source_refs=["wiki/sources/foo.md"])

    def test_protocol_learn_add_rejects_missing_source_ref(self) -> None:
        with self.assertRaises(ValueError):
            add_learning(self.root, "general", title="bad", source_refs=["wiki/derived/not-there.md"])

    def test_protocol_learn_add_rejects_source_ref_traversal_escape(self) -> None:
        # Attempt to escape wiki/derived/ via ".." segments; must be rejected
        # even though the prefix string technically matches.
        (self.root / "wiki" / "sources" / "sneaky.md").parent.mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "sources" / "sneaky.md").write_text("evil", encoding="utf-8")
        with self.assertRaises(ValueError):
            add_learning(self.root, "general", title="bad", source_refs=["wiki/derived/../sources/sneaky.md"])

    def test_protocol_learn_add_accepts_wiki_elixirs_source_ref(self) -> None:
        (self.root / "wiki" / "elixirs").mkdir(parents=True, exist_ok=True)
        elixir_path = self.root / "wiki" / "elixirs" / "elixir-sample.md"
        elixir_path.write_text("---\nelixir_id: \"elixir-sample\"\n---\n\n# stub\n", encoding="utf-8")
        result = add_learning(self.root, "general", title="cites elixir", source_refs=["wiki/elixirs/elixir-sample.md"])
        self.assertTrue((self.root / result["path"]).exists())

    def test_protocol_learn_list_rejects_unknown_protocol(self) -> None:
        with self.assertRaises(ValueError):
            list_learnings(self.root, "nonexistent")

    def test_protocol_learn_list_returns_empty_when_no_learnings(self) -> None:
        self.assertEqual(list_learnings(self.root), [])

    def test_protocol_learn_list_groups_across_protocols(self) -> None:
        add_learning(self.root, "general", title="g1")
        add_learning(self.root, "investing", title="i1")
        listed = list_learnings(self.root)
        self.assertEqual([item["protocol"] for item in listed], ["general", "investing"])

    def test_protocol_learn_list_filters_by_protocol(self) -> None:
        add_learning(self.root, "general", title="g1")
        add_learning(self.root, "investing", title="i1")
        listed = list_learnings(self.root, "general")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["protocol"], "general")

    def test_protocol_learn_show_returns_frontmatter_and_body(self) -> None:
        result = add_learning(self.root, "general", title="show me")
        shown = show_learning(self.root, result["learning_id"])
        self.assertIn("frontmatter", shown)
        self.assertIn("body", shown)
        self.assertEqual(shown["frontmatter"]["title"], "show me")

    def test_protocol_learn_show_raises_for_unknown_id(self) -> None:
        with self.assertRaises(FileNotFoundError):
            show_learning(self.root, "missing")

    def test_protocol_learn_add_produces_unique_id_for_same_title(self) -> None:
        first = add_learning(self.root, "general", title="same")
        second = add_learning(self.root, "general", title="same")
        self.assertNotEqual(first["learning_id"], second["learning_id"])

    def test_ask_injects_protocol_learnings_when_flag_on(self) -> None:
        add_learning(self.root, "general", title="foo-bar-unique")
        result = ask_question(self.root, "What changed?", "report", load_protocol_learnings=True)
        text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertIn("## Protocol Learnings", text)
        self.assertIn("foo-bar-unique", text)

    def test_ask_does_not_inject_protocol_learnings_by_default(self) -> None:
        add_learning(self.root, "general", title="foo-bar-unique")
        result = ask_question(self.root, "What changed?", "report")
        text = (self.root / result["path"]).read_text(encoding="utf-8")
        self.assertNotIn("## Protocol Learnings", text)


class ProtocolLearningsLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "source.md").write_text("# source\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _old_timestamp(self, *, days: int = 100) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()

    def _write_learning(
        self,
        learning_id: str,
        *,
        protocol: str = "general",
        title: str | None = None,
        source_refs: list[str] | None = None,
        state: str | None = "active",
        last_verified_at: str | None = None,
        updated_at: str | None = None,
        archived_at: str | None = None,
        superseded_by: str | None = None,
        superseded_at: str | None = None,
        supersedes: list[str] | None = None,
        lesson: str = "Pending.",
    ) -> Path:
        created_at = updated_at or utc_now()
        lines = [
            "---",
            f'learning_id: {json.dumps(learning_id)}',
            f'protocol: {json.dumps(protocol)}',
            f'title: {json.dumps(title or learning_id)}',
            "source_refs:",
        ]
        for ref in source_refs or ["wiki/derived/source.md"]:
            lines.append(f"  - {json.dumps(ref)}")
        if state is not None:
            lines.append(f'state: {json.dumps(state)}')
        lines.append(f'created_at: {json.dumps(created_at)}')
        lines.append(f'updated_at: {json.dumps(updated_at or created_at)}')
        if last_verified_at is not None:
            lines.append(f'last_verified_at: {json.dumps(last_verified_at)}')
        if archived_at is not None:
            lines.append(f'archived_at: {json.dumps(archived_at)}')
        if superseded_by is not None:
            lines.append(f'superseded_by: {json.dumps(superseded_by)}')
        if superseded_at is not None:
            lines.append(f'superseded_at: {json.dumps(superseded_at)}')
        if supersedes is not None:
            lines.append("supersedes:")
            for item in supersedes:
                lines.append(f"  - {json.dumps(item)}")
        lines.extend([
            "---",
            "# Protocol Learning",
            "",
            "## Lesson",
            f"- {lesson}",
            "",
            "## When to apply",
            "- Pending.",
            "",
            "## Evidence",
            "- Pending.",
            "",
        ])
        path = self.root / LEARNINGS_DIR / protocol / f"{learning_id}.md"
        _atomic_write_text(path, "\n".join(lines))
        return path

    def _write_elixir(self, elixir_id: str, *, state: str = "settled") -> str:
        path = self.root / "wiki" / "elixirs" / f"{elixir_id}.md"
        _atomic_write_text(
            path,
            "\n".join([
                "---",
                f'elixir_id: {json.dumps(elixir_id)}',
                f'elixir_state: {json.dumps(state)}',
                "derived_from:",
                '  - "wiki/derived/source.md"',
                "---",
                "# Elixir",
                "",
            ]),
        )
        return f"wiki/elixirs/{elixir_id}.md"

    def test_add_writes_state_and_last_verified_at(self) -> None:
        result = add_learning(self.root, "general", title="fresh", source_refs=["wiki/derived/source.md"])

        frontmatter = parse_frontmatter((self.root / result["path"]).read_text(encoding="utf-8"))

        self.assertEqual(frontmatter["state"], "active")
        self.assertTrue(frontmatter["last_verified_at"])

    def test_legacy_file_without_state_treated_as_active(self) -> None:
        self._write_learning("legacy-x", state=None, last_verified_at=utc_now(), lesson="legacy")

        listed = list_learnings(self.root, "general")
        shown = show_learning(self.root, "legacy-x")
        loaded = load_learnings_for_protocol(self.root, "general")

        self.assertEqual([item["learning_id"] for item in listed], ["legacy-x"])
        self.assertEqual(listed[0]["state"], "active")
        self.assertEqual(shown["state"], "active")
        self.assertNotIn("state", shown["frontmatter"])
        self.assertEqual([item["learning_id"] for item in loaded], ["legacy-x"])

    def test_list_filters_by_state(self) -> None:
        self._write_learning("active-one", state="active", last_verified_at=utc_now())
        self._write_learning("stale-one", state="stale", last_verified_at=self._old_timestamp())
        self._write_learning("demoted-one", state="demoted", last_verified_at=utc_now())

        listed = list_learnings(self.root, state_filter="stale")

        self.assertEqual([item["learning_id"] for item in listed], ["stale-one"])

    def test_list_hides_archived_by_default(self) -> None:
        self._write_learning("active-one", state="active", last_verified_at=utc_now())
        self._write_learning("archived-one", state="archived", last_verified_at=utc_now(), archived_at=utc_now())

        default_list = list_learnings(self.root)
        with_archived = list_learnings(self.root, include_archived=True)
        archived_only = list_learnings(self.root, state_filter="archived")

        self.assertEqual([item["learning_id"] for item in default_list], ["active-one"])
        self.assertEqual([item["learning_id"] for item in with_archived], ["active-one", "archived-one"])
        self.assertEqual([item["learning_id"] for item in archived_only], ["archived-one"])

    def test_list_rejects_unknown_state(self) -> None:
        with self.assertRaises(ValueError):
            list_learnings(self.root, state_filter="bogus")

    def test_age_dry_run_does_not_mutate(self) -> None:
        path = self._write_learning("old-active", state="active", last_verified_at=self._old_timestamp(), updated_at=self._old_timestamp())
        before = path.read_text(encoding="utf-8")

        result = age_learnings(self.root, apply=False)

        self.assertIn("old-active", [item["learning_id"] for item in result["aged"]])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_age_apply_transitions_active_to_stale(self) -> None:
        self._write_learning("old-active", state="active", last_verified_at=self._old_timestamp(), updated_at=self._old_timestamp())

        result = age_learnings(self.root, apply=True)

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "old-active.md").read_text(encoding="utf-8"))
        audit = json.loads((self.root / ".aiwiki" / "state" / "protocol_learnings_age.json").read_text(encoding="utf-8"))
        self.assertIn("old-active", [item["learning_id"] for item in result["aged"]])
        self.assertEqual(frontmatter["state"], "stale")
        self.assertIn("old-active", [item["learning_id"] for item in audit["aged"]])

    def test_age_apply_writes_learning_threshold_runtime_history(self) -> None:
        old = self._old_timestamp()
        self._write_learning("old-active", state="active", last_verified_at=old, updated_at=old)

        result = age_learnings(self.root, apply=True, threshold_days=30)

        events = [
            event
            for event in load_runtime_history(self.root)
            if event.get("event_type") == "learning-threshold"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["protocol"], "general")
        self.assertEqual(events[0]["threshold_days"], 30)
        self.assertEqual(events[0]["learning_ids"], ["old-active"])
        self.assertEqual(events[0]["aged_ids"], ["old-active"])
        self.assertEqual(events[0]["learning_paths"], [f"{LEARNINGS_DIR}/general/old-active.md"])
        self.assertEqual(events[0]["audit_path"], AUDIT_STATE_PATH)
        self.assertEqual(events[0]["emitted_by"], "user")
        self.assertEqual(events[0]["occurred_at"], result["run_at"])

    def test_age_dry_run_does_not_write_learning_threshold_runtime_history(self) -> None:
        old = self._old_timestamp()
        self._write_learning("old-active", state="active", last_verified_at=old, updated_at=old)

        age_learnings(self.root, apply=False, threshold_days=30)

        events = [
            event
            for event in load_runtime_history(self.root)
            if event.get("event_type") == "learning-threshold"
        ]
        self.assertEqual(events, [])

    def test_age_source_ref_missing_marks_stale(self) -> None:
        self._write_learning("missing-ref", state="active", last_verified_at=utc_now())
        (self.root / "wiki" / "derived" / "source.md").unlink()

        result = age_learnings(self.root, apply=True)

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "missing-ref.md").read_text(encoding="utf-8"))
        aged = next(item for item in result["aged"] if item["learning_id"] == "missing-ref")
        self.assertEqual(frontmatter["state"], "stale")
        self.assertTrue(any("source_ref 缺失" in reason for reason in aged["reasons"]))

    def test_age_source_ref_non_settled_elixir_marks_stale(self) -> None:
        draft_ref = self._write_elixir("draft-one", state="draft")
        self._write_learning("draft-ref", state="active", source_refs=[draft_ref], last_verified_at=utc_now())

        result = age_learnings(self.root, apply=True)

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "draft-ref.md").read_text(encoding="utf-8"))
        aged = next(item for item in result["aged"] if item["learning_id"] == "draft-ref")
        self.assertEqual(frontmatter["state"], "stale")
        self.assertTrue(any("elixir 非 settled" in reason for reason in aged["reasons"]))

    def test_age_illegal_ref_goes_to_errors_not_stale(self) -> None:
        self._write_learning("illegal-ref", state="active", source_refs=["../etc/passwd"], last_verified_at=self._old_timestamp())

        result = age_learnings(self.root, apply=True)

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "illegal-ref.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["state"], "active")
        self.assertNotIn("illegal-ref", [item["learning_id"] for item in result["aged"]])
        self.assertIn("illegal-ref", [item["learning_id"] for item in result["errors"]])

    def test_verify_transitions_to_active_and_refreshes_last_verified_at(self) -> None:
        old = self._old_timestamp()
        self._write_learning("needs-verify", state="stale", last_verified_at=old, updated_at=old)

        result = verify_learning(self.root, "needs-verify")

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "needs-verify.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["state"], "active")
        self.assertGreater(datetime.fromisoformat(frontmatter["last_verified_at"]), datetime.fromisoformat(old))
        self.assertEqual(frontmatter["last_verified_at"], result["last_verified_at"])
        self.assertEqual(frontmatter["activation_previous_state"], "stale")
        self.assertEqual(frontmatter["activation_previous_updated_at"], old)
        self.assertEqual(frontmatter["activation_previous_last_verified_at"], old)
        self.assertEqual(frontmatter["activation_verified_at"], result["last_verified_at"])

    def test_revert_learning_activation_restores_stale_and_writes_audit(self) -> None:
        old = self._old_timestamp()
        self._write_learning("needs-revert", state="stale", last_verified_at=old, updated_at=old)
        verify_learning(self.root, "needs-revert")

        result = revert_learning_activation(self.root, "needs-revert", note="Undo activation.")

        learning_path = self.root / LEARNINGS_DIR / "general" / "needs-revert.md"
        frontmatter = parse_frontmatter(learning_path.read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "stale")
        self.assertEqual(frontmatter["state"], "stale")
        self.assertEqual(frontmatter["last_verified_at"], old)
        self.assertNotIn("activation_previous_state", frontmatter)
        self.assertNotIn("activation_verified_at", frontmatter)

        events = [
            event
            for event in load_runtime_history(self.root)
            if event.get("event_type") == "protocol-learning-activation-reverted"
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["learning_id"], "needs-revert")
        self.assertEqual(events[0]["previous_state"], "active")
        self.assertEqual(events[0]["state"], "stale")
        self.assertEqual(events[0]["note"], "Undo activation.")

        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki" / "state" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        runtime_audit = [
            record
            for record in audit_records
            if record["source_stream"] == "runtime_history"
            and record["event_type"] == "protocol-learning-activation-reverted"
        ]
        self.assertEqual(len(runtime_audit), 1)
        self.assertEqual(runtime_audit[0]["subject"], {"kind": "protocol_learning", "id": "needs-revert"})

    def test_revert_learning_activation_rejects_without_stale_activation_metadata(self) -> None:
        self._write_learning("already-active", state="active", last_verified_at=utc_now())

        with self.assertRaises(ValueError):
            revert_learning_activation(self.root, "already-active")

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "already-active.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["state"], "active")

    def test_revert_learning_activation_rejects_after_later_verify(self) -> None:
        old = self._old_timestamp()
        self._write_learning("changed-after-verify", state="stale", last_verified_at=old, updated_at=old)
        verify_learning(self.root, "changed-after-verify")
        verify_learning(self.root, "changed-after-verify")

        with self.assertRaises(ValueError):
            revert_learning_activation(self.root, "changed-after-verify")

    def test_verify_rejects_when_source_ref_missing(self) -> None:
        self._write_learning("missing-verify", state="stale", last_verified_at=self._old_timestamp())
        (self.root / "wiki" / "derived" / "source.md").unlink()

        with self.assertRaises(ValueError):
            verify_learning(self.root, "missing-verify")

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "missing-verify.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["state"], "stale")

    def test_verify_rejects_when_elixir_non_settled(self) -> None:
        draft_ref = self._write_elixir("draft-verify", state="draft")
        self._write_learning("verify-draft", state="stale", source_refs=[draft_ref], last_verified_at=self._old_timestamp())

        with self.assertRaises(ValueError):
            verify_learning(self.root, "verify-draft")

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "verify-draft.md").read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["state"], "stale")

    def test_demote_from_active(self) -> None:
        self._write_learning("demote-me", state="active", last_verified_at=utc_now())

        demote_learning(self.root, "demote-me")

        frontmatter = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "demote-me.md").read_text(encoding="utf-8"))
        loaded = load_learnings_for_protocol(self.root, "general")
        self.assertEqual(frontmatter["state"], "demoted")
        self.assertEqual(loaded, [])

    def test_demote_from_archived_rejected(self) -> None:
        self._write_learning("archived-demote", state="archived", last_verified_at=utc_now(), archived_at=utc_now())

        with self.assertRaises(ValueError):
            demote_learning(self.root, "archived-demote")

    def test_archive_writes_archived_at(self) -> None:
        self._write_learning("archive-me", state="active", last_verified_at=utc_now())

        archive_learning(self.root, "archive-me")

        shown = show_learning(self.root, "archive-me")
        self.assertEqual(shown["state"], "archived")
        self.assertTrue(shown["frontmatter"]["archived_at"])

    def test_archive_already_archived_rejected(self) -> None:
        self._write_learning("already-archived", state="archived", last_verified_at=utc_now(), archived_at=utc_now())

        with self.assertRaises(ValueError):
            archive_learning(self.root, "already-archived")

    def test_supersede_marks_targets_and_replacement_graph(self) -> None:
        self._write_learning("replacement", state="active", last_verified_at=utc_now())
        self._write_learning("old-one", state="active", last_verified_at=utc_now())
        self._write_learning("old-two", state="stale", last_verified_at=self._old_timestamp())

        result = supersede_learning(self.root, "replacement", ["old-one", "old-two"])

        replacement_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "replacement.md").read_text(encoding="utf-8"))
        old_one_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "old-one.md").read_text(encoding="utf-8"))
        old_two_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "old-two.md").read_text(encoding="utf-8"))
        self.assertEqual(result["replacement_learning_id"], "replacement")
        self.assertEqual(result["superseded_ids"], ["old-one", "old-two"])
        self.assertEqual(replacement_fm["supersedes"], ["old-one", "old-two"])
        self.assertEqual(old_one_fm["state"], "superseded")
        self.assertEqual(old_one_fm["superseded_by"], "replacement")
        self.assertTrue(old_one_fm["superseded_at"])
        self.assertEqual(old_two_fm["state"], "superseded")
        self.assertEqual(old_two_fm["superseded_by"], "replacement")

    def test_list_filters_superseded_state(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="superseded", last_verified_at=now, superseded_by="replacement", superseded_at=now)

        listed = list_learnings(self.root, state_filter="superseded")

        self.assertEqual([item["learning_id"] for item in listed], ["old-one"])
        self.assertEqual(listed[0]["state"], "superseded")

    def test_load_learnings_for_protocol_skips_superseded(self) -> None:
        now = utc_now()
        self._write_learning(
            "replacement",
            state="active",
            last_verified_at=now,
            lesson="replacement lesson",
            supersedes=["old-one"],
        )
        self._write_learning("old-one", state="superseded", last_verified_at=now, superseded_by="replacement", superseded_at=now)

        loaded = load_learnings_for_protocol(self.root, "general")

        self.assertEqual([item["learning_id"] for item in loaded], ["replacement"])

    def test_supersede_rejects_non_active_replacement(self) -> None:
        self._write_learning("replacement", state="stale", last_verified_at=self._old_timestamp())
        self._write_learning("old-one", state="active", last_verified_at=utc_now())

        with self.assertRaises(ValueError) as ctx:
            supersede_learning(self.root, "replacement", ["old-one"])
        self.assertIn("必须是 active", str(ctx.exception))

    def test_supersede_rejects_archived_or_superseded_target(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now)
        self._write_learning("archived-target", state="archived", last_verified_at=now, archived_at=now)
        self._write_learning("superseded-target", state="superseded", last_verified_at=now, superseded_by="replacement-2", superseded_at=now)
        self._write_learning("replacement-2", state="active", last_verified_at=now, supersedes=["superseded-target"])

        with self.assertRaises(ValueError):
            supersede_learning(self.root, "replacement", ["archived-target"])
        with self.assertRaises(ValueError):
            supersede_learning(self.root, "replacement", ["superseded-target"])

    def test_supersede_rejects_cross_protocol(self) -> None:
        self._write_learning("replacement", protocol="general", state="active", last_verified_at=utc_now())
        self._write_learning("ops-old", protocol="ops", state="active", last_verified_at=utc_now())

        with self.assertRaises(ValueError) as ctx:
            supersede_learning(self.root, "replacement", ["ops-old"])
        self.assertIn("cross-protocol", str(ctx.exception))

    def test_supersede_rejects_self_loop_duplicate_ids_and_duplicate_edge(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="superseded", last_verified_at=now, superseded_by="replacement", superseded_at=now)
        self._write_learning("fresh-old", state="active", last_verified_at=now)

        with self.assertRaises(ValueError):
            supersede_learning(self.root, "replacement", ["replacement"])
        with self.assertRaises(ValueError):
            supersede_learning(self.root, "replacement", ["fresh-old", "fresh-old"])
        with self.assertRaises(ValueError) as ctx:
            supersede_learning(self.root, "replacement", ["old-one"])
        self.assertTrue(
            "duplicate edge" in str(ctx.exception) or "不能再次 supersede" in str(ctx.exception)
        )

    def test_supersede_rejects_dirty_graph_and_cycle(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="active", last_verified_at=now)
        self._write_learning("cycle-a", state="active", last_verified_at=now, supersedes=["cycle-b"])
        self._write_learning("cycle-b", state="active", last_verified_at=now, supersedes=["cycle-a"])

        with self.assertRaises(ValueError) as dirty_ctx:
            supersede_learning(self.root, "replacement", ["old-one"])
        self.assertIn("learning graph inconsistent", str(dirty_ctx.exception))

        # Reset to isolate cycle case.
        self.tempdir.cleanup()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        ensure_layout(self.root)
        (self.root / "prompts" / "compile.md").write_text("Compile prompt fixture.\n", encoding="utf-8")
        (self.root / "prompts" / "ask.md").write_text("Ask prompt fixture.\n", encoding="utf-8")
        (self.root / "wiki" / "derived").mkdir(parents=True, exist_ok=True)
        (self.root / "wiki" / "derived" / "source.md").write_text("# source\n", encoding="utf-8")
        self._write_learning("replacement", state="active", last_verified_at=now)
        self._write_learning("cycle-a", state="active", last_verified_at=now, supersedes=["cycle-b"])
        self._write_learning("cycle-b", state="active", last_verified_at=now, supersedes=["cycle-a"])

        with self.assertRaises(ValueError) as cycle_ctx:
            supersede_learning(self.root, "replacement", ["cycle-a"])
        self.assertIn("cycle", str(cycle_ctx.exception))

    def test_verify_demote_archive_reject_superseded(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="superseded", last_verified_at=now, superseded_by="replacement", superseded_at=now)

        with self.assertRaises(ValueError):
            verify_learning(self.root, "old-one")
        with self.assertRaises(ValueError):
            demote_learning(self.root, "old-one")
        with self.assertRaises(ValueError):
            archive_learning(self.root, "old-one")

    def test_load_learnings_rejects_dirty_supersede_graph(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="active", last_verified_at=now)

        with self.assertRaises(ValueError) as ctx:
            load_learnings_for_protocol(self.root, "general")
        self.assertIn("learning graph inconsistent", str(ctx.exception))

    def test_ask_with_load_learnings_rejects_dirty_supersede_graph(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="active", last_verified_at=now)

        with self.assertRaises(ValueError) as ctx:
            ask_question(self.root, "What changed?", "report", load_protocol_learnings=True)
        self.assertIn("learning graph inconsistent", str(ctx.exception))

    def test_verify_demote_archive_fail_fast_on_dirty_supersede_graph(self) -> None:
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["old-one"])
        self._write_learning("old-one", state="active", last_verified_at=now)

        with self.assertRaises(ValueError):
            verify_learning(self.root, "replacement")
        with self.assertRaises(ValueError):
            demote_learning(self.root, "replacement")
        with self.assertRaises(ValueError):
            archive_learning(self.root, "replacement")

    def test_load_learnings_for_protocol_only_returns_active(self) -> None:
        self._write_learning(
            "active-one",
            state="active",
            last_verified_at=utc_now(),
            lesson="active lesson",
            supersedes=["superseded-one"],
        )
        self._write_learning("stale-one", state="stale", last_verified_at=utc_now())
        self._write_learning("demoted-one", state="demoted", last_verified_at=utc_now())
        self._write_learning("archived-one", state="archived", last_verified_at=utc_now(), archived_at=utc_now())
        self._write_learning(
            "superseded-one",
            state="superseded",
            last_verified_at=utc_now(),
            superseded_by="active-one",
            superseded_at=utc_now(),
        )

        loaded = load_learnings_for_protocol(self.root, "general")

        self.assertEqual([item["learning_id"] for item in loaded], ["active-one"])
        self.assertEqual(loaded[0]["lesson"], "active lesson")

    def test_cross_protocol_age_scans_all(self) -> None:
        old = self._old_timestamp()
        self._write_learning("general-old", protocol="general", state="active", last_verified_at=old, updated_at=old)
        self._write_learning("investing-old", protocol="investing", state="active", last_verified_at=old, updated_at=old)

        result = age_learnings(self.root, protocol=None, apply=True)

        general_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "general-old.md").read_text(encoding="utf-8"))
        investing_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "investing" / "investing-old.md").read_text(encoding="utf-8"))
        self.assertEqual(general_fm["state"], "stale")
        self.assertEqual(investing_fm["state"], "stale")
        self.assertEqual(
            {item["learning_id"] for item in result["aged"]},
            {"general-old", "investing-old"},
        )

    def test_age_skips_non_active_states(self) -> None:
        old = self._old_timestamp()
        self._write_learning("demoted-old", state="demoted", last_verified_at=old, updated_at=old)
        now = utc_now()
        self._write_learning("replacement", state="active", last_verified_at=now, supersedes=["superseded-old"])
        self._write_learning("superseded-old", state="superseded", last_verified_at=old, updated_at=old, superseded_by="replacement", superseded_at=now)
        self._write_learning("archived-old", state="archived", last_verified_at=old, updated_at=old, archived_at=utc_now())

        result = age_learnings(self.root, apply=True)

        demoted_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "demoted-old.md").read_text(encoding="utf-8"))
        superseded_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "superseded-old.md").read_text(encoding="utf-8"))
        archived_fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "archived-old.md").read_text(encoding="utf-8"))
        skipped = {item["learning_id"]: item["state"] for item in result["skipped"]}
        self.assertEqual(demoted_fm["state"], "demoted")
        self.assertEqual(superseded_fm["state"], "superseded")
        self.assertEqual(archived_fm["state"], "archived")
        self.assertEqual(skipped["demoted-old"], "demoted")
        self.assertEqual(skipped["superseded-old"], "superseded")
        self.assertEqual(skipped["archived-old"], "archived")

    def test_age_dirty_supersede_graph_goes_to_errors_without_mutation(self) -> None:
        old = self._old_timestamp()
        self._write_learning("replacement", state="active", last_verified_at=old, updated_at=old, supersedes=["old-one"])
        target_path = self._write_learning("old-one", state="active", last_verified_at=old, updated_at=old)
        before = target_path.read_text(encoding="utf-8")

        result = age_learnings(self.root, apply=True)

        self.assertEqual(result["aged"], [])
        self.assertTrue(result["errors"])
        self.assertIn("learning graph inconsistent", result["errors"][0]["reason"])
        self.assertEqual(target_path.read_text(encoding="utf-8"), before)

    def test_verify_rejects_archived_learning(self) -> None:
        # contract Acceptance #8: archived 终态，verify 不能反向迁移。
        self._write_elixir("settled-fixture")
        self._write_learning(
            "archived-terminal",
            state="archived",
            source_refs=["wiki/elixirs/settled-fixture.md"],
            archived_at=utc_now(),
        )
        with self.assertRaises(ValueError) as ctx:
            verify_learning(self.root, "archived-terminal")
        self.assertIn("archived", str(ctx.exception))
        fm = parse_frontmatter((self.root / LEARNINGS_DIR / "general" / "archived-terminal.md").read_text(encoding="utf-8"))
        self.assertEqual(fm["state"], "archived")

    def test_age_corrupt_frontmatter_goes_to_errors(self) -> None:
        # contract Acceptance #11: 坏 frontmatter 必须显式进 errors，不静默降级。
        corrupt_path = self.root / LEARNINGS_DIR / "general" / "corrupt.md"
        corrupt_path.parent.mkdir(parents=True, exist_ok=True)
        # frontmatter 分隔符存在，但没有任何 key: value，parse 返回 {}
        corrupt_path.write_text("---\n(not valid yaml content at all)\n---\n# body\n", encoding="utf-8")

        result = age_learnings(self.root, apply=True)

        self.assertTrue(result["errors"])
        self.assertIn("learning graph inconsistent", result["errors"][0]["reason"])
        # 未被当 stale 处理
        aged_ids = [e["learning_id"] for e in result["aged"]]
        self.assertNotIn("corrupt", aged_ids)

    def test_age_audit_payload_includes_aged_ids(self) -> None:
        # contract Acceptance #13: audit 必须包含 aged_ids 字段。
        old = self._old_timestamp()
        self._write_elixir("settled-fixture")
        self._write_learning(
            "aging-candidate",
            state="active",
            source_refs=["wiki/elixirs/settled-fixture.md"],
            last_verified_at=old,
            updated_at=old,
        )

        result = age_learnings(self.root, apply=True)

        self.assertIn("aged_ids", result)
        self.assertIn("aging-candidate", result["aged_ids"])
        # audit 文件内容也要一致
        audit_path = self.root / AUDIT_STATE_PATH
        self.assertTrue(audit_path.is_file())
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        self.assertIn("aged_ids", audit)
        self.assertIn("aging-candidate", audit["aged_ids"])

    def test_age_apply_writes_universal_audit(self) -> None:
        old = self._old_timestamp()
        self._write_elixir("settled-fixture")
        self._write_learning(
            "aging-candidate",
            state="active",
            source_refs=["wiki/elixirs/settled-fixture.md"],
            last_verified_at=old,
            updated_at=old,
        )

        result = age_learnings(self.root, apply=True)

        age_audit = json.loads((self.root / AUDIT_STATE_PATH).read_text(encoding="utf-8"))
        audit_records = [
            json.loads(line)
            for line in (self.root / ".aiwiki/state/audit.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        age_records = [record for record in audit_records if record["source_stream"] == "protocol_learnings_age"]
        self.assertEqual(age_audit, result)
        self.assertEqual(len(age_records), 1)
        self.assertEqual(age_records[0]["source_ref"], f"{AUDIT_STATE_PATH}#run_at={result['run_at']}")
        self.assertEqual(age_records[0]["event_type"], "protocol_learnings_age")
        self.assertEqual(age_records[0]["occurred_at"], result["run_at"])
        self.assertEqual(age_records[0]["subject"], {"kind": "protocol_learnings_age", "id": ""})
        self.assertFalse(age_records[0]["revert_supported"])
        runtime_records = [record for record in audit_records if record["source_stream"] == "runtime_history"]
        self.assertEqual(len(runtime_records), 1)


if __name__ == "__main__":
    unittest.main()
