from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aiwiki.app_protocol import ensure_layout
from aiwiki.compile import compile_wiki
from aiwiki.content.io import ingest_source
from aiwiki.execution.ask import ask_question
from aiwiki.vault_obsidian_graph import (
    materialize_obsidian_native_graph_links,
    sync_obsidian_native_graph_config,
)


class VaultObsidianGraphTests(unittest.TestCase):
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

    def test_sync_obsidian_native_graph_config_includes_evidence_paths(self) -> None:
        graph_path = self.root / ".obsidian" / "graph.json"
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text('{"search": "", "colorGroups": []}\n', encoding="utf-8")
        sync_obsidian_native_graph_config(self.root)
        graph_config = json.loads(graph_path.read_text(encoding="utf-8"))
        self.assertIn('path:"wiki/sources"', graph_config["search"])
        self.assertIn('-path:"wiki/concepts"', graph_config["search"])
        self.assertTrue(graph_config["showOrphans"])
        self.assertTrue(graph_config["colorGroups"])

    def test_materialize_writes_report_and_source_wikilinks(self) -> None:
        ingest_source(self.root, str(self.sample), title="Transformer Scaling")
        compile_wiki(self.root)
        ask_question(self.root, "Compare transformer scale and inference cost", "report")

        source_page = next((self.root / "wiki" / "sources").glob("*.md"))

        counts = materialize_obsidian_native_graph_links(self.root)
        source_text = source_page.read_text(encoding="utf-8")
        self.assertIn("## 原料文件", source_text)
        self.assertIn("[[raw/", source_text)
        self.assertNotIn("[[wiki/concepts/", source_text)

        report_page = next((self.root / "output" / "reports").glob("*.md"))
        report_text = report_page.read_text(encoding="utf-8")
        self.assertIn("## 关系图谱锚点", report_text)
        self.assertIn("[[wiki/sources/", report_text)
        self.assertNotIn("[[wiki/concepts/", report_text)
        # compile/ask may have already materialized; this pass must stay idempotent
        self.assertIsInstance(counts, dict)

    def test_strip_concept_wikilinks(self) -> None:
        from aiwiki.vault_obsidian_graph import strip_concept_wikilinks

        text = "See [[wiki/concepts/agent|Agent]] for details."
        self.assertNotIn("[[wiki/concepts/", strip_concept_wikilinks(text))
        self.assertIn("wiki/concepts/agent.md", strip_concept_wikilinks(text))

    def test_materialize_strips_legacy_report_concept_wikilinks(self) -> None:
        report = self.root / "output" / "reports" / "legacy.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "---\n"
            "kind: report\n"
            "graph_anchor_node_ids:\n"
            "  - concept:open\n"
            "---\n\n"
            "# Legacy report\n\n"
            "See [[wiki/concepts/open|Open]] for details.\n\n"
            "## 关系图谱锚点\n"
            "- [[wiki/concepts/open|Open]]\n",
            encoding="utf-8",
        )
        memory = {
            "compiled_at": "2026-05-21T00:00:00Z",
            "edges": {"source_to_concept": [{"source_id": "source-readme-md", "concept_slug": "open"}]},
        }

        counts = materialize_obsidian_native_graph_links(self.root, memory)

        text = report.read_text(encoding="utf-8")
        self.assertNotIn("[[wiki/concepts/", text)
        self.assertIn("wiki/concepts/open.md", text)
        self.assertIn("source:source-readme-md", text)
        self.assertEqual(counts.get("reports"), 1)

    def test_expand_native_anchors_from_concepts(self) -> None:
        from aiwiki.vault_obsidian_graph import expand_native_anchors_from_concepts

        memory = {
            "edges": {
                "source_to_concept": [
                    {"source_id": "source-readme-md", "concept_slug": "open"},
                ]
            }
        }
        native = expand_native_anchors_from_concepts(["concept:open", "concept:repo"], memory)
        self.assertEqual(native, ["source:source-readme-md"])

    def test_plainify_concept_page_removes_source_wikilinks(self) -> None:
        from aiwiki.vault_obsidian_graph import plainify_concept_page_links

        text = "- [[wiki/sources/foo|Foo]]\n- [Bar](../sources/bar.md)\n"
        plain = plainify_concept_page_links(text)
        self.assertNotIn("[[wiki/sources/", plain)
        self.assertNotIn("](../sources/", plain)
        self.assertIn("wiki/sources/foo.md", plain)


if __name__ == "__main__":
    unittest.main()
