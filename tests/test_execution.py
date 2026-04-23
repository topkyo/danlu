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
    load_active_corpora_state,
    load_machine_memory,
    load_manifest,
    load_material_archive_state,
    load_output_candidates_state,
    save_active_corpora_state,
    save_machine_memory_action_state,
    save_output_candidates_state,
)
from aiwiki.app_utils import parse_frontmatter
from aiwiki.cli import main as cli_main
from aiwiki.execution.alchemy import _validate_source_outputs
from aiwiki.execution.candidates import demote_candidate, promote_candidate
from aiwiki.llm import CompletionResult
from aiwiki.runner import run_ask, run_compile


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

    def _make_sample(self) -> Path:
        return self.sample

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

    def test_ask_with_corpus_flag_reuses_corpus_id(self) -> None:
        first = run_ask(self.root, "First question?", "report", client=_StubClient(["---\nfront: yes\n---\n# Title\n\nBody.\n"]))
        second = run_ask(
            self.root,
            "Second question?",
            "report",
            client=_StubClient(["---\nfront: yes\n---\n# Title\n\nBody.\n"]),
            corpus_id_override=first["active_corpus_id"],
        )

        self.assertEqual(first["active_corpus_id"], second["active_corpus_id"])
        first_frontmatter = parse_frontmatter((self.root / first["path"]).read_text(encoding="utf-8"))
        second_frontmatter = parse_frontmatter((self.root / second["path"]).read_text(encoding="utf-8"))
        self.assertEqual(first_frontmatter.get("candidate_state"), "pending")
        self.assertEqual(second_frontmatter.get("candidate_state"), "pending")

    def test_ask_second_round_injects_previous_output_summary(self) -> None:
        first = run_ask(self.root, "First question?", "report", client=_StubClient(["---\nfront: yes\n---\n# Title\n\nBody.\n"]))
        captured: dict[str, str] = {}

        from aiwiki import runner as runner_module

        original = runner_module._build_ask_prompt

        def spy(*args, **kwargs):
            captured["prompt"] = original(*args, **kwargs)
            return captured["prompt"]

        with patch.object(runner_module, "_build_ask_prompt", side_effect=spy):
            run_ask(
                self.root,
                "Second question?",
                "report",
                client=_StubClient([
                    "---\nfront: yes\n---\n# Title\n\nBody.\n",
                    "---\nfront: yes\n---\n# Title\n\nBody.\n",
                ]),
                corpus_id_override=first["active_corpus_id"],
            )

        self.assertIn("## Previous Output In Corpus", captured["prompt"])
        self.assertIn(first["path"], captured["prompt"])

    def test_ask_first_round_no_previous_output_section(self) -> None:
        captured: dict[str, str] = {}

        from aiwiki import runner as runner_module

        original = runner_module._build_ask_prompt

        def spy(*args, **kwargs):
            captured["prompt"] = original(*args, **kwargs)
            return captured["prompt"]

        with patch.object(runner_module, "_build_ask_prompt", side_effect=spy):
            run_ask(self.root, "First question?", "report", client=_StubClient(["---\nfront: yes\n---\n# Title\n\nBody.\n"]))

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
            code = cli_main(["--root", str(self.root), *argv])
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
            code = cli_main(["--root", str(self.root), *argv])
        payload = json.loads(stdout.getvalue()) if stdout.getvalue().strip() else {}
        return code, payload, stderr.getvalue()

    def test_alchemy_start_creates_elixir_from_promoted_outputs(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])

        from aiwiki.runner import run_alchemy_start

        result = run_alchemy_start(self.root, corpus_id, "VLA robotics")

        path = self.root / result["path"]
        self.assertTrue(path.exists())
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "forming")
        self.assertEqual(frontmatter["iteration"], "0")
        self.assertTrue(frontmatter["source_outputs"])
        self.assertTrue(all(str(item).startswith("wiki/derived/") for item in frontmatter["source_outputs"]))

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
        self.assertGreaterEqual(len(frontmatter["source_outputs"]), 2)
        self.assertEqual(len(json.loads(frontmatter.get("distill_history_json", "[]"))), 1)

    def test_alchemy_distill_rejects_sealed_elixir(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_seal, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        run_alchemy_seal(self.root, start["elixir_id"])

        from aiwiki.runner import run_alchemy_distill

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")
        frontmatter = parse_frontmatter((self.root / start["path"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "sealed")

    def test_alchemy_seal_marks_sealed(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_seal, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        result = run_alchemy_seal(self.root, start["elixir_id"])

        self.assertEqual(result["elixir_state"], "sealed")
        frontmatter = parse_frontmatter((self.root / start["path"]).read_text(encoding="utf-8"))
        self.assertEqual(frontmatter["elixir_state"], "sealed")
        self.assertTrue(frontmatter.get("sealed_at"))

    def test_alchemy_seal_is_not_idempotent_on_already_sealed(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_seal, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        run_alchemy_seal(self.root, start["elixir_id"])

        with self.assertRaises(ValueError):
            run_alchemy_seal(self.root, start["elixir_id"])

    def test_alchemy_validates_source_output_must_be_wiki_derived(self) -> None:
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["output/reports/foo.md"], allowed=set())
        with self.assertRaises(ValueError):
            _validate_source_outputs(self.root, ["wiki/derived/missing.md"], allowed={"wiki/derived/missing.md"})

    def test_alchemy_start_rejects_tampered_source_outputs_not_in_corpus_output_refs(self) -> None:
        corpus_id = self._make_promoted_corpus(["Question A?"])
        result = ask_question(self.root, "Question B?", "report", corpus_id_override=corpus_id)
        promote_candidate(self.root, result["path"])
        corpora = load_active_corpora_state(self.root)
        for corpus in corpora["corpora"]:
            if str(corpus.get("corpus_id") or "") == corpus_id:
                corpus["output_refs"] = []
        save_active_corpora_state(self.root, corpora)

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

    def test_alchemy_seal_rejects_empty_source_outputs_tampering(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.execution.alchemy import _write_elixir_markdown
        from aiwiki.runner import run_alchemy_seal, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / start["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        frontmatter["source_outputs"] = []
        _write_elixir_markdown(path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError):
            run_alchemy_seal(self.root, start["elixir_id"])

    def test_alchemy_distill_rejects_empty_source_outputs_tampering(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.execution.alchemy import _write_elixir_markdown
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / start["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        frontmatter["source_outputs"] = []
        _write_elixir_markdown(path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError):
            run_alchemy_distill(self.root, start["elixir_id"], "What about latency?")

    def test_alchemy_seal_rejects_tampered_frontmatter_source_outputs(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_seal, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        path = self.root / start["path"]
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        frontmatter["source_outputs"] = [*frontmatter["source_outputs"], "wiki/derived/tampered.md"]
        (self.root / "wiki" / "derived" / "tampered.md").write_text("tampered", encoding="utf-8")
        from aiwiki.execution.alchemy import _write_elixir_markdown
        _write_elixir_markdown(path, frontmatter=frontmatter, body=text.split("---", 2)[-1].lstrip("\n"))

        with self.assertRaises(ValueError):
            run_alchemy_seal(self.root, start["elixir_id"])

    def test_alchemy_distill_rejects_stale_source_output_removed_from_output_refs(self) -> None:
        corpus_id = self._make_promoted_corpus(["Should we increase transformer training spend?"])
        from aiwiki.runner import run_alchemy_distill, run_alchemy_start

        start = run_alchemy_start(self.root, corpus_id, "VLA robotics")
        corpora = load_active_corpora_state(self.root)
        for corpus in corpora["corpora"]:
            if str(corpus.get("corpus_id") or "") == corpus_id:
                corpus["output_refs"] = []
        save_active_corpora_state(self.root, corpora)

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


if __name__ == "__main__":
    unittest.main()
