from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiwiki.app_compile import compile_wiki, lint_wiki
from aiwiki.app_protocol import ensure_layout
from aiwiki.app_state import (
    load_concept_rewrite_state,
    load_machine_memory,
    load_machine_memory_action_state,
    load_runtime_history,
)
from aiwiki.app_utils import parse_frontmatter
from aiwiki.content.io import (
    ingest_source,
    sync_manifest_with_raw,
)
from aiwiki.drop import drop_url
from aiwiki.execution.ask import (
    ask_question,
    file_back,
)
from aiwiki.execution.concept_rewrite import (
    apply_concept_rewrite,
    revert_concept_rewrite,
    review_concept_rewrite,
    verify_concept_rewrite,
)
from aiwiki.execution.machine_memory_actions import (
    apply_machine_memory_action,
    revert_machine_memory_action,
    review_machine_memory_action,
)
from aiwiki.execution.review import review_page
from aiwiki.execution.runtime_surfaces import nightly_health
from aiwiki.llm import CompletionResult
from aiwiki.runner import run_compile


class StubClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.config = type("Config", (), {"model": "stub-model"})()

    def complete(self, system_prompt: str, user_prompt: str) -> CompletionResult:
        del system_prompt
        del user_prompt
        if not self.responses:
            raise AssertionError("No stubbed response left.")
        return CompletionResult(text=self.responses.pop(0), response_id="stub-response", usage={})


class PipelineTests(unittest.TestCase):
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

    def _prepare_citation_snapshot_refresh_action(self) -> tuple[dict[str, str], dict[str, object], dict[str, object]]:
        entry = ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        report = ask_question(self.root, "Will transformer inference cost keep rising?", "report")
        judgment = file_back(self.root, report["path"], title="Scaling Judgment", kind="judgment")
        review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Confirmed before evidence changed.",
            confidence="high",
        )
        stored_source = self.root / entry["stored_path"]
        stored_source.write_text(
            "# Transformer Scaling\n\nTransformers still benefit from scale.\nNew serving optimizations changed inference cost assumptions.\n",
            encoding="utf-8",
        )
        compile_wiki(self.root)
        memory = load_machine_memory(self.root)
        action = next(
            item for item in memory["health"]["actions"] if item.get("kind") == "refresh-citation-snapshots"
        )
        return entry, judgment, action

    def test_compile_prunes_deleted_raw_note_manifest_entries(self) -> None:
        orphan = self.root / "raw" / "inbox" / "orphan.md"
        orphan.write_text("# Orphan\n\nTemporary note.\n", encoding="utf-8")
        manifest = sync_manifest_with_raw(self.root)
        self.assertIn("raw/inbox/orphan.md", [entry["stored_path"] for entry in manifest["entries"]])

        orphan.unlink()
        compiled = compile_wiki(self.root)
        refreshed = sync_manifest_with_raw(self.root)

        self.assertGreaterEqual(compiled["sources"], 0)
        self.assertNotIn("raw/inbox/orphan.md", [entry["stored_path"] for entry in refreshed["entries"]])

    def test_drop_url_compile_ask_file_back_review_and_lint_pipeline(self) -> None:
        fetched = {
            "title": "LLM Agent Architecture",
            "final_url": "https://example.com/agents",
            "content_type": "text/html",
            "status": "200",
            "browser_backend": "",
            "extraction_mode": "readability",
            "description": "Multi-agent runtime overview.",
            "image_urls": [],
            "text": "Agents coordinate planning, tools, and memory layers.",
        }
        with patch("aiwiki.drop._fetch_url", return_value=fetched):
            dropped = drop_url(self.root, "https://example.com/agents")

        compiled = compile_wiki(self.root)
        report = ask_question(self.root, "What are the core layers of an agent runtime?", "report")
        judgment = file_back(self.root, report["path"], title="Agent Runtime Judgment", kind="judgment")
        reviewed = review_page(
            self.root,
            judgment["path"],
            "confirmed",
            note="Grounded in the dropped source.",
            confidence="high",
        )
        lint_result = lint_wiki(self.root)

        self.assertEqual(dropped["material"], "url")
        self.assertGreater(compiled["sources"], 0)
        self.assertTrue((self.root / report["path"]).exists())
        self.assertEqual(reviewed["status"], "confirmed")
        self.assertTrue((self.root / lint_result["path"]).exists())

    def test_compile_rewrite_apply_verify_and_revert_pipeline(self) -> None:
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
        original = proposal_target.read_text(encoding="utf-8")
        rewritten = original.replace("Existing synthesis", "Rewritten synthesis")

        run_result = run_compile(self.root, client=StubClient([rewritten]), limit=1)
        proposal_path = self.root / run_result["updated_rewrite_proposal_pages"][0]
        slug = proposal_path.stem

        review = review_concept_rewrite(self.root, slug, "accepted", note="Looks grounded.")
        applied = apply_concept_rewrite(self.root, slug, note="Apply accepted rewrite.")
        verified = verify_concept_rewrite(self.root, slug, note="Verify rewrite after apply.")
        reverted = revert_concept_rewrite(self.root, slug, note="Restore previous synthesis.")

        self.assertEqual(review["status"], "accepted")
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(verified["status"], "passed")
        self.assertEqual(reverted["status"], "accepted")
        self.assertIn("Existing synthesis", proposal_target.read_text(encoding="utf-8"))

    def test_compile_prunes_stale_inactive_rewrite_proposals(self) -> None:
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
        concept_page = self.root / candidate["path"]
        rewritten = concept_page.read_text(encoding="utf-8").replace("Existing synthesis", "Rewritten synthesis")
        run_result = run_compile(self.root, client=StubClient([rewritten]), limit=1)
        proposal_path = self.root / run_result["updated_rewrite_proposal_pages"][0]
        slug = proposal_path.stem

        (self.root / entry["stored_path"]).unlink()
        concept_page.unlink()
        proposal_path.unlink()
        compile_wiki(self.root)

        proposals = load_concept_rewrite_state(self.root)["proposals"]
        self.assertNotIn(slug, [str(item.get("slug") or "") for item in proposals if isinstance(item, dict)])

    def test_counter_evidence_scan_persists_across_clean_compile(self) -> None:
        entry = ingest_source(self.root, str(self.sample), title="Agent Governance Runtime")
        compile_wiki(self.root)
        judgment_path = self.root / "wiki" / "judgments" / "judgment-runtime-governance.md"
        judgment_path.parent.mkdir(parents=True, exist_ok=True)
        judgment_path.write_text(
            "\n".join(
                [
                    "---",
                    'id: "judgment-runtime-governance"',
                    'kind: "judgment"',
                    'status: "confirmed"',
                    'title: "Runtime Governance Judgment"',
                    'protocol: "general"',
                    "citations:",
                    f'  - "wiki/sources/{entry["id"]}.md"',
                    "---",
                    "",
                    "# Runtime Governance Judgment",
                    "",
                    "## Judgment",
                    "- Agent governance helps when runtimes coordinate tools and policy.",
                    "",
                    "## Counter Evidence",
                    "- Small local runtimes may stay simpler in-process.",
                    "",
                    "## Next Signals",
                    "- Watch for policy and agent overhead.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        counterpoint = self.root / "counterpoint.md"
        counterpoint.write_text(
            (
                "# Governance Counterpoint\n\n"
                "Small local agent runtimes can keep tools, policy, and review in-process before"
                " governance overhead pays for itself.\n"
            ),
            encoding="utf-8",
        )
        ingest_source(self.root, str(counterpoint), title="Governance Overhead Counterpoint")

        compile_wiki(self.root)
        first_scan = load_machine_memory(self.root)["health"]["counter_evidence_scan"]
        self.assertGreater(first_scan["candidate_count"], 0)
        counter_events = [
            event
            for event in load_runtime_history(self.root)
            if event.get("event_type") == "counter-evidence"
        ]
        self.assertTrue(counter_events)
        self.assertEqual(counter_events[0]["candidate_id"], first_scan["candidates"][0]["candidate_id"])
        self.assertEqual(counter_events[0]["source_ids"], [first_scan["candidates"][0]["source_id"]])
        self.assertEqual(counter_events[0]["page_path"], first_scan["candidates"][0]["page_path"])

        compile_wiki(self.root)
        second_scan = load_machine_memory(self.root)["health"]["counter_evidence_scan"]
        self.assertGreater(second_scan["candidate_count"], 0)
        self.assertEqual(
            {candidate["candidate_id"] for candidate in first_scan["candidates"]},
            {candidate["candidate_id"] for candidate in second_scan["candidates"]},
        )

    def test_compile_nightly_review_apply_and_revert_action_pipeline(self) -> None:
        _, judgment, action = self._prepare_citation_snapshot_refresh_action()
        nightly = nightly_health(self.root)
        state = json.loads((self.root / nightly["state_path"]).read_text(encoding="utf-8"))

        review = review_machine_memory_action(self.root, action["id"], "accepted", note="Queue safe apply.")
        dry_run = apply_machine_memory_action(self.root, action["id"], dry_run=True)
        applied = apply_machine_memory_action(
            self.root,
            action["id"],
            note="Refresh citation snapshots.",
            bundle_path=dry_run["bundle_path"],
        )
        reverted = revert_machine_memory_action(self.root, action["id"], note="Rollback citation snapshot refresh.")

        judgment_path = self.root / judgment["path"]
        frontmatter = parse_frontmatter(judgment_path.read_text(encoding="utf-8"))
        action_state = load_machine_memory_action_state(self.root)
        refreshed = next(item for item in action_state["actions"] if item["id"] == action["id"])

        self.assertTrue((self.root / nightly["repair_backlog"]).exists())
        self.assertTrue(state["repair_backlog"])
        self.assertEqual(review["status"], "accepted")
        self.assertEqual(dry_run["apply_mode"], "citation-snapshot-refresh")
        self.assertTrue((self.root / dry_run["bundle_path"]).exists())
        self.assertTrue((self.root / dry_run["dry_run_path"]).exists())
        self.assertEqual(applied["status"], "resolved")
        self.assertEqual(reverted["status"], "proposed")
        self.assertEqual(refreshed["status"], "proposed")
        self.assertTrue(frontmatter["citation_snapshots"])


if __name__ == "__main__":
    unittest.main()
