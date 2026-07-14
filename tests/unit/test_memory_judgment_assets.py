from __future__ import annotations

import json

from aiwiki import app_memory
from aiwiki.app_state import manifest_path
from aiwiki.memory.judgment_assets import attach_judgment_assets_to_machine_memory


def test_app_memory_judgment_assets_facade_matches_owner_and_links_edges(tmp_path):
    (tmp_path / ".aiwiki" / "state").mkdir(parents=True)
    (tmp_path / "wiki" / "sources").mkdir(parents=True)
    (tmp_path / "wiki" / "decisions").mkdir(parents=True)
    (tmp_path / "wiki" / "judgments").mkdir(parents=True)
    manifest_path(tmp_path).write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "id": "source-a",
                        "stored_path": "raw/source-a.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "sources" / "source-a.md").write_text("# Source A\n", encoding="utf-8")
    (tmp_path / "wiki" / "decisions" / "decision-a.md").write_text(
        "\n".join(
            [
                "---",
                "id: decision-a",
                "kind: decision",
                "title: Decision A",
                "status: accepted",
                "citations:",
                "  - wiki/sources/source-a.md",
                "supports:",
                "  - ../judgments/judgment-a.md",
                "---",
                "# Decision A",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "judgments" / "judgment-a.md").write_text(
        "\n".join(
            [
                "---",
                "id: judgment-a",
                "kind: judgment",
                "title: Judgment A",
                "status: active",
                "citations:",
                "  - wiki/sources/source-a.md",
                "---",
                "# Judgment A",
            ]
        ),
        encoding="utf-8",
    )
    memory = {
        "version": 1,
        "compiled_at": "2026-05-25T00:00:00+00:00",
        "edges": {"source_to_concept": []},
    }
    decisions = [{"path": "wiki/decisions/decision-a.md"}]
    judgments = [{"path": "wiki/judgments/judgment-a.md"}]

    owner = attach_judgment_assets_to_machine_memory(tmp_path, memory, decisions, judgments)
    facade = app_memory.attach_judgment_assets_to_machine_memory(tmp_path, memory, decisions, judgments)

    assert facade == owner
    node_by_id = {node["page_id"]: node for node in facade["judgment_nodes"]}
    assert node_by_id["decision-a"]["source_ids"] == ["source-a"]
    assert node_by_id["judgment-a"]["source_ids"] == ["source-a"]
    assert node_by_id["decision-a"]["supports"] == ["judgment-a"]
    assert {"source_id": "source-a", "page_id": "decision-a"} in facade["edges"]["source_to_judgment"]
    assert {"source_id": "source-a", "page_id": "judgment-a"} in facade["edges"]["source_to_judgment"]
    assert facade["edges"]["judgment_to_decision"] == [
        {
            "from": "decision-a",
            "to": "judgment-a",
            "relation": "supports",
            "judgment_id": "judgment-a",
            "decision_id": "decision-a",
        }
    ]
