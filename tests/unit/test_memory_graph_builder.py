from __future__ import annotations

from aiwiki import app_memory
from aiwiki.memory.graph_builder import build_machine_memory_graph


def test_app_memory_graph_builder_facade_matches_owner(tmp_path):
    (tmp_path / "wiki" / "sources").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "judgments").mkdir(parents=True)
    (tmp_path / "wiki" / "sources" / "source-a.md").write_text(
        "---\ntitle: 原始材料\n---\n正文包含中文。",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "concepts" / "alpha.md").write_text(
        "# 概念标题\n中文概念内容。",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "judgments" / "judgment-a.md").write_text(
        "---\ntitle: 判断标题\n---\n判断正文。",
        encoding="utf-8",
    )

    memory = {
        "compiled_at": "2026-05-25T00:00:00+00:00",
        "source_nodes": [
            {
                "id": "source-a",
                "title": "Source A",
                "source_type": "note",
                "source_page": "wiki/sources/source-a.md",
                "stored_path": "raw/source-a.md",
            },
        ],
        "concept_nodes": [
            {
                "slug": "alpha",
                "title": "Alpha",
                "source_pages": ["wiki/sources/source-a.md"],
            },
        ],
        "judgment_nodes": [
            {
                "page_id": "judgment-a",
                "title": "Judgment A",
                "path": "wiki/judgments/judgment-a.md",
                "kind": "decision",
                "status": "accepted",
                "source_ids": ["source-a"],
            },
        ],
        "edges": {
            "source_to_concept": [{"source_id": "source-a", "concept_slug": "alpha"}],
            "source_to_judgment": [{"source_id": "source-a", "page_id": "judgment-a"}],
            "judgment_to_judgment": [],
            "judgment_to_decision": [],
            "concept_to_concept": [],
            "concept_causal": [],
        },
    }

    owner = build_machine_memory_graph(memory, root=tmp_path)
    facade = app_memory.build_machine_memory_graph(memory, root=tmp_path)

    assert facade == owner
    assert [node["id"] for node in facade["nodes"]] == [
        "concept:alpha",
        "judgment:judgment-a",
        "source:source-a",
    ]
    assert {edge["type"] for edge in facade["edges"]} == {"HAS_CONCEPT", "SUPPORTS_JUDGMENT"}
    assert all(node["chinese_related"] for node in facade["nodes"])
