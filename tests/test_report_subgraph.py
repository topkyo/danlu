"""Tests for build_report_subgraph + render_report_subgraph_markdown (EP-004)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiwiki.memory.graph import (
    ReportSubgraphError,
    build_report_subgraph,
    render_report_subgraph_markdown,
)


def _fixture_memory() -> dict:
    """Minimal machine-memory dict consumed by build_machine_memory_graph."""
    return {
        "compiled_at": "2026-05-11T00:00:00Z",
        "source_nodes": [
            {
                "id": "alpha",
                "title": "Source Alpha",
                "source_type": "url",
                "source_page": "wiki/sources/alpha.md",
                "stored_path": "raw/alpha.html",
            },
            {
                "id": "beta",
                "title": "Source Beta",
                "source_type": "pdf",
                "source_page": "wiki/sources/beta.md",
                "stored_path": "raw/beta.pdf",
            },
        ],
        "concept_nodes": [
            {"slug": "concept-x", "title": "Concept X", "source_pages": ["wiki/sources/alpha.md"]},
            {"slug": "concept-y", "title": "Concept Y", "source_pages": []},
        ],
        "judgment_nodes": [
            {
                "page_id": "j1",
                "title": "Judgment One",
                "path": "wiki/judgments/j1.md",
                "kind": "judgment",
                "status": "accepted",
                "source_ids": ["alpha"],
            },
        ],
        "edges": {
            "source_to_concept": [
                {"source_id": "alpha", "concept_slug": "concept-x"},
            ],
            "source_to_judgment": [
                {"source_id": "alpha", "page_id": "j1"},
            ],
            "judgment_to_judgment": [],
            "judgment_to_decision": [],
            "concept_to_concept": [
                {"from": "concept-x", "to": "concept-y"},
            ],
            "concept_causal": [],
        },
    }


def _write_report(root: Path, rel: str, anchors: list[str] | None) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", "title: Demo Report", "kind: output/report"]
    if anchors is None:
        pass
    else:
        lines.append("graph_anchor_node_ids:")
        for anchor in anchors:
            lines.append(f"  - {anchor}")
    lines.append("---")
    lines.append("")
    lines.append("# Demo")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_fixture_graph_pages(root: Path) -> None:
    """Materialize the markdown pages referenced by _fixture_memory()."""
    for rel in (
        "wiki/sources/alpha.md",
        "wiki/sources/beta.md",
        "wiki/concepts/concept-x.md",
        "wiki/concepts/concept-y.md",
        "wiki/judgments/j1.md",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {path.stem}\n", encoding="utf-8")


class BuildReportSubgraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patcher = mock.patch(
            "aiwiki.app_state.load_machine_memory",
            return_value=_fixture_memory(),
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        self._tmp.cleanup()

    def test_happy_path_collects_anchors_and_one_hop_neighbors(self) -> None:
        _write_fixture_graph_pages(self.root)
        _write_report(self.root, "output/reports/demo.md", ["concept:concept-x"])
        result = build_report_subgraph(self.root, "output/reports/demo.md")

        self.assertEqual(result["report"], "output/reports/demo.md")
        self.assertEqual(result["anchor_node_ids"], ["concept:concept-x"])
        node_ids = {str(node["id"]) for node in result["nodes"]}
        # anchor + 1-hop neighbors: source alpha (HAS_CONCEPT) and concept-y (RELATED_CONCEPT)
        self.assertEqual(
            node_ids,
            {"concept:concept-x", "source:alpha", "concept:concept-y"},
        )
        edge_pairs = {(edge["source"], edge["target"], edge["type"]) for edge in result["edges"]}
        self.assertIn(("source:alpha", "concept:concept-x", "HAS_CONCEPT"), edge_pairs)
        self.assertIn(("concept:concept-x", "concept:concept-y", "RELATED_CONCEPT"), edge_pairs)
        # 邻居不包含锚点自身
        self.assertNotIn("concept:concept-x", result["neighbors"])
        self.assertIn("source:alpha", result["neighbors"])
        self.assertIn("concept:concept-y", result["neighbors"])
        # 每条 edge 都带中文 label
        for edge in result["edges"]:
            self.assertTrue(edge["label"])

    def test_missing_report_raises_fail_loud(self) -> None:
        with self.assertRaises(ReportSubgraphError) as ctx:
            build_report_subgraph(self.root, "output/reports/missing.md")
        self.assertIn("not found", str(ctx.exception))

    def test_report_without_anchors_raises(self) -> None:
        _write_report(self.root, "output/reports/no-anchors.md", anchors=None)
        with self.assertRaises(ReportSubgraphError) as ctx:
            build_report_subgraph(self.root, "output/reports/no-anchors.md")
        self.assertIn("graph_anchor_node_ids", str(ctx.exception))

    def test_anchor_pointing_to_unknown_node_raises(self) -> None:
        _write_report(self.root, "output/reports/bad.md", ["concept:does-not-exist"])
        with self.assertRaises(ReportSubgraphError) as ctx:
            build_report_subgraph(self.root, "output/reports/bad.md")
        self.assertIn("unknown graph nodes", str(ctx.exception))
        self.assertIn("concept:does-not-exist", str(ctx.exception))


class BuildReportSubgraphUncompiledMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_machine_memory_raises_fail_loud(self) -> None:
        _write_report(self.root, "output/reports/demo.md", ["concept:concept-x"])
        with mock.patch("aiwiki.app_state.load_machine_memory", return_value={}):
            with self.assertRaises(ReportSubgraphError) as ctx:
                build_report_subgraph(self.root, "output/reports/demo.md")
        self.assertIn("not compiled", str(ctx.exception))

    def test_non_dict_machine_memory_raises_fail_loud(self) -> None:
        _write_report(self.root, "output/reports/demo.md", ["concept:concept-x"])
        with mock.patch("aiwiki.app_state.load_machine_memory", return_value=None):
            with self.assertRaises(ReportSubgraphError) as ctx:
                build_report_subgraph(self.root, "output/reports/demo.md")
        self.assertIn("not compiled", str(ctx.exception))

    def test_corrupt_machine_memory_raises_fail_loud(self) -> None:
        _write_report(self.root, "output/reports/demo.md", ["concept:concept-x"])
        # Compiled-shaped but malformed (nodes missing required keys → KeyError inside
        # build_machine_memory_graph). Must be wrapped into ReportSubgraphError, not leak
        # as generic exit-1.
        corrupt_memory = {
            "compiled_at": "2026-05-11T00:00:00Z",
            "nodes": [{"oops": "no id no title"}],
            "edges": [],
        }
        with mock.patch(
            "aiwiki.app_state.load_machine_memory", return_value=corrupt_memory
        ):
            with self.assertRaises(ReportSubgraphError) as ctx:
                build_report_subgraph(self.root, "output/reports/demo.md")
        self.assertIn("corrupt", str(ctx.exception).lower())

    def test_report_path_outside_root_raises_fail_loud(self) -> None:
        # Absolute path pointing outside the vault root must be rejected fail-loud,
        # not propagate as generic ValueError from relative_path().
        with tempfile.TemporaryDirectory() as outside:
            outside_path = Path(outside) / "stray-report.md"
            outside_path.write_text(
                "---\ngraph_anchor_node_ids:\n  - concept:x\n---\nbody\n",
                encoding="utf-8",
            )
            with self.assertRaises(ReportSubgraphError) as ctx:
                build_report_subgraph(self.root, str(outside_path))
        self.assertIn("outside", str(ctx.exception).lower())

    def test_symlink_root_resolves_consistently(self) -> None:
        # Root accessed via symlink must still produce a vault-relative `report` field,
        # not crash via relative_path() mismatch between unresolved root and resolved abs.
        if not hasattr(os, "symlink"):
            self.skipTest("symlink not supported")
        link_root = Path(self._tmp.name) / "link-root"
        try:
            link_root.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlink in this environment")
        _write_report(self.root, "output/reports/demo.md", ["concept:concept-x"])
        concept_path = self.root / "wiki/concepts/concept-x.md"
        concept_path.parent.mkdir(parents=True, exist_ok=True)
        concept_path.write_text("# Concept X\n", encoding="utf-8")
        compiled_memory = {
            "compiled_at": "2026-05-11T00:00:00Z",
            "concept_nodes": [
                {"slug": "concept-x", "title": "X", "source_pages": []},
            ],
        }
        with mock.patch(
            "aiwiki.app_state.load_machine_memory", return_value=compiled_memory
        ):
            result = build_report_subgraph(link_root, "output/reports/demo.md")
        self.assertEqual(result["report"], "output/reports/demo.md")


class RenderReportSubgraphMarkdownTests(unittest.TestCase):
    def test_markdown_has_required_sections(self) -> None:
        subgraph = {
            "report": "output/reports/demo.md",
            "anchor_node_ids": ["concept:concept-x"],
            "nodes": [
                {"id": "concept:concept-x", "kind": "concept", "title": "Concept X"},
                {"id": "source:alpha", "kind": "source", "title": "Source Alpha"},
                {"id": "concept:concept-y", "kind": "concept", "title": "Concept Y"},
            ],
            "edges": [
                {
                    "source": "source:alpha",
                    "target": "concept:concept-x",
                    "type": "HAS_CONCEPT",
                    "label": "材料提到概念",
                },
                {
                    "source": "concept:concept-x",
                    "target": "concept:concept-y",
                    "type": "RELATED_CONCEPT",
                    "label": "概念相关",
                },
            ],
            "neighbors": ["concept:concept-y", "source:alpha"],
        }
        text = render_report_subgraph_markdown(subgraph)
        self.assertIn("kind: output/subgraph", text)
        self.assertIn("source_report: output/reports/demo.md", text)
        self.assertIn("graph_anchor_node_ids:", text)
        self.assertIn("  - concept:concept-x", text)
        self.assertIn("## 锚点", text)
        self.assertIn("## 一跳邻居（按类型分组）", text)
        self.assertIn("## 引用边", text)
        self.assertIn("`source:alpha`", text)
        self.assertIn("材料提到概念", text)
        self.assertIn("概念相关", text)


if __name__ == "__main__":
    unittest.main()
